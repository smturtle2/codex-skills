"""Pure move and threat evaluation; no turn selection, storage, or UI.

Renju follows RIF definitions and rules 9.1–9.3:
https://www.renju.net/rifrules/
Coordinates in this module are zero-based. Hypothetical black extensions are
legality checks, not strategic search. Each recursive check adds a stone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

EMPTY, BLACK, WHITE = 0, 1, 2
DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))
Coord = tuple[int, int]
Board = tuple[tuple[int, ...], ...]


def freeze(board: Iterable[Iterable[int]]) -> Board:
    return tuple(tuple(row) for row in board)


def placed(board: Board, point: Coord, value: int) -> Board:
    row, col = point
    return board[:row] + (board[row][:col] + (value,) + board[row][col + 1:],) + board[row + 1:]


def line_at(board: Board, point: Coord, direction: Coord) -> tuple[Coord, ...]:
    size, (row, col), (dr, dc) = len(board), point, direction
    while 0 <= row - dr < size and 0 <= col - dc < size:
        row, col = row - dr, col - dc
    line = []
    while 0 <= row < size and 0 <= col < size:
        line.append((row, col))
        row, col = row + dr, col + dc
    return tuple(line)


def run_at(board: Board, point: Coord, direction: Coord) -> tuple[Coord, ...]:
    line = line_at(board, point, direction)
    index = line.index(point)
    value = board[point[0]][point[1]]
    start, end = index, index + 1
    while start and board[line[start - 1][0]][line[start - 1][1]] == value:
        start -= 1
    while end < len(line) and board[line[end][0]][line[end][1]] == value:
        end += 1
    return line[start:end]


@dataclass(frozen=True)
class Four:
    stones: tuple[Coord, ...]
    completions: tuple[Coord, ...]
    direction: Coord

    @property
    def straight(self) -> bool:
        dr, dc = self.direction
        return len(self.completions) == 2 and all(
            (b[0] - a[0], b[1] - a[1]) == (dr, dc)
            for a, b in zip(self.stones, self.stones[1:])
        )


@dataclass(frozen=True)
class Three:
    stones: tuple[Coord, ...]
    extensions: tuple[Coord, ...]
    direction: Coord


@dataclass(frozen=True)
class MoveAssessment:
    legal: bool
    board: Board
    winner: str | None = None
    violation: str | None = None
    winning_line: tuple[Coord, ...] = ()
    fours: tuple[Four, ...] = ()
    threes: tuple[Three, ...] = ()


class RuleEvaluator:
    """One authoritative evaluator shared by move validation and public facts."""

    def __init__(self, renju: bool = False):
        self.renju = renju
        self._memo: dict[tuple[Board, Coord], MoveAssessment] = {}

    def assess(self, board: Board, point: Coord, value: int) -> MoveAssessment:
        row, col = point
        if not (0 <= row < len(board) and 0 <= col < len(board)):
            return MoveAssessment(False, board, violation="outside_board")
        if board[row][col] != EMPTY:
            return MoveAssessment(False, board, violation="occupied")
        return self.assess_placed(placed(board, point, value), point, value)

    def assess_placed(self, board: Board, point: Coord, value: int) -> MoveAssessment:
        restricted = self.renju and value == BLACK
        key = (board, point)
        if restricted and key in self._memo:
            return self._memo[key]
        runs = tuple(run_at(board, point, direction) for direction in DIRECTIONS)
        winning = next((run for run in runs if len(run) == 5 or (not restricted and len(run) > 5)), ())
        # RIF 9.2: an attained five takes precedence even over a simultaneous overline.
        if winning:
            result = MoveAssessment(True, board, "black" if value == BLACK else "white", winning_line=winning)
        elif not restricted:
            result = MoveAssessment(True, board)
        elif any(len(run) > 5 for run in runs):
            result = MoveAssessment(False, board, violation="black_overline")
        else:
            fours = self.fours(board, point, value)
            if len(fours) >= 2:
                result = MoveAssessment(False, board, violation="black_double_four", fours=fours)
            else:
                threes = self.threes(board, point, value)
                result = MoveAssessment(len(threes) < 2, board,
                                        violation="black_double_three" if len(threes) >= 2 else None,
                                        fours=fours, threes=threes)
        if restricted:
            self._memo[key] = result
        return result

    def fours(self, board: Board, anchor: Coord, value: int) -> tuple[Four, ...]:
        """Distinct four-stone sets through anchor, with actual winning ends."""
        found = {}
        exact = self.renju and value == BLACK
        for direction in DIRECTIONS:
            line = line_at(board, anchor, direction)
            index = line.index(anchor)
            for start in range(max(0, index - 4), min(index + 1, len(line) - 4)):
                window = line[start:start + 5]
                stones = tuple(p for p in window if board[p[0]][p[1]] == value)
                empty = tuple(p for p in window if board[p[0]][p[1]] == EMPTY)
                if len(stones) != 4 or len(empty) != 1 or anchor not in stones:
                    continue
                completion = empty[0]
                length = len(run_at(placed(board, completion, value), completion, direction))
                if length != 5 and (exact or length < 5):
                    continue
                found.setdefault((direction, stones), set()).add(completion)
        return tuple(Four(stones, tuple(sorted(ends)), direction)
                     for (direction, stones), ends in sorted(found.items()))

    def threes(self, board: Board, anchor: Coord, value: int) -> tuple[Three, ...]:
        """A three must have a legal, non-winning extension to a straight four.

        Six-cell windows describe the required resulting straight four, rather
        than matching alleged threes. Recursive assessment handles RIF 9.3's
        forbidden extensions. Threat identity is its stones, not its direction.
        """
        found = {}
        for direction in DIRECTIONS:
            line = line_at(board, anchor, direction)
            index = line.index(anchor)
            for start in range(max(0, index - 4), min(index, len(line) - 5)):
                window = line[start:start + 6]
                if board[window[0][0]][window[0][1]] or board[window[-1][0]][window[-1][1]]:
                    continue
                interior = window[1:-1]
                stones = tuple(p for p in interior if board[p[0]][p[1]] == value)
                empty = tuple(p for p in interior if board[p[0]][p[1]] == EMPTY)
                if len(stones) != 3 or len(empty) != 1 or anchor not in stones:
                    continue
                extension = empty[0]
                extended = placed(board, extension, value)
                four_stones = tuple(sorted((*stones, extension), key=line.index))
                if not any(f.stones == four_stones and f.direction == direction and f.straight
                           for f in self.fours(extended, extension, value)):
                    continue
                assessment = self.assess_placed(extended, extension, value)
                if assessment.legal and assessment.winner is None:
                    found.setdefault((direction, stones), set()).add(extension)
        return tuple(Three(stones, tuple(sorted(extensions)), direction)
                     for (direction, stones), extensions in sorted(found.items()))

    def threats(self, board: Board, value: int) -> tuple[tuple[Four, ...], tuple[Three, ...]]:
        fours, threes = {}, {}
        for row, cells in enumerate(board):
            for col, cell in enumerate(cells):
                if cell != value:
                    continue
                for four in self.fours(board, (row, col), value):
                    fours[(four.direction, four.stones)] = four
                for three in self.threes(board, (row, col), value):
                    threes[(three.direction, three.stones)] = three
        return tuple(fours[k] for k in sorted(fours)), tuple(threes[k] for k in sorted(threes))

    def completions(self, board: Board, value: int) -> tuple[tuple[Coord, MoveAssessment], ...]:
        results = []
        restricted = self.renju and value == BLACK
        for row, cells in enumerate(board):
            for col, cell in enumerate(cells):
                if cell != EMPTY:
                    continue
                point = (row, col)
                candidate = placed(board, point, value)
                # Skip points incapable of a terminal line; legality remains
                # entirely in assess_placed, including simultaneous wins.
                runs = tuple(run_at(candidate, point, d) for d in DIRECTIONS)
                if any(len(run) >= 5 for run in runs):
                    assessment = self.assess_placed(candidate, point, value)
                    if assessment.winner or (restricted and assessment.violation == "black_overline"):
                        results.append((point, assessment))
        return tuple(results)


def existing_lines(board: Board, value: int, renju: bool = False):
    seen = set()
    for row, cells in enumerate(board):
        for col, cell in enumerate(cells):
            if cell != value:
                continue
            for direction in DIRECTIONS:
                run = run_at(board, (row, col), direction)
                if len(run) < 5 or (renju and value == BLACK and len(run) != 5):
                    continue
                key = direction, run
                if key not in seen:
                    seen.add(key)
                    yield direction, run
