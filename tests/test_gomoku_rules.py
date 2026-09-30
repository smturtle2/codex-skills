from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/gomoku/scripts"
sys.path.insert(0, str(SCRIPTS))
from gomoku_rules import BLACK, WHITE, RuleEvaluator, freeze
from gomoku_session import GomokuError, apply_move, new_state, start_game
from gomoku_gui import threat_view_payload


def position(black=(), white=(), *, renju=True, player="black"):
    state = start_game(new_state(renju_rules=renju))
    for value, points in ((BLACK, black), (WHITE, white)):
        for row, col in points:
            state["board"][row - 1][col - 1] = value
    state["next_player"] = player
    return state


class GomokuRulesTests(unittest.TestCase):
    def test_four_identity_and_move_membership(self):
        cases = [
            ("central gap", [(8, 7), (8, 10), (8, 11), (6, 8), (7, 8), (9, 8)], False, 2),
            ("same direction", [(8, 5), (8, 7), (8, 9), (8, 11)], False, 2),
            ("two ends of one four", [(8, 6), (8, 7), (8, 9)], True, 1),
            ("unrelated old fours", [(8, c) for c in (3, 4, 5, 6)] + [(r, 8) for r in (3, 4, 5, 6)], True, 0),
        ]
        for label, black, legal, count in cases:
            with self.subTest(label=label):
                state = position(black)
                before = deepcopy(state)
                assessment = RuleEvaluator(True).assess(freeze(state["board"]), (7, 7), BLACK)
                self.assertEqual(assessment.legal, legal)
                self.assertEqual(len(assessment.fours), count)
                self.assertTrue(all((7, 7) in four.stones for four in assessment.fours))
                if label == "two ends of one four":
                    self.assertTrue(assessment.fours[0].straight)
                    self.assertEqual(len(assessment.fours[0].completions), 2)
                if legal:
                    apply_move(state, 8, 8, "black")
                else:
                    self.assertEqual(assessment.violation, "black_double_four")
                    with self.assertRaises(GomokuError):
                        apply_move(state, 8, 8, "black")
                self.assertEqual(state, before)

    def test_threes_require_legal_extensions_including_recursive_double_three(self):
        base = [(8, 6), (8, 7), (6, 8), (7, 8)]
        extra_four = [(r, c) for c in (5, 9) for r in (5, 6, 7)]
        extra_overline = [(r, c) for c in (5, 9) for r in (5, 6, 7, 9, 10)]
        extra_three = [(6, 5), (7, 5), (6, 3), (7, 4), (6, 9), (7, 9), (6, 11), (7, 10)]
        cases = [
            ("true double-three", base, [], False, 2, None),
            ("blocked pseudo-three", [(8, 7), (8, 9), (6, 8), (7, 8)], [(8, 5), (8, 11)], True, 1, None),
            ("double-four extension", base + extra_four, [], True, 1, "black_double_four"),
            ("overline extension", base + extra_overline, [], True, 1, "black_overline"),
            ("recursive double-three extension", base + extra_three, [], True, 1, "black_double_three"),
        ]
        for label, black, white, legal, count, extension_violation in cases:
            with self.subTest(label=label):
                state = position(black, white)
                board = freeze(state["board"])
                evaluator = RuleEvaluator(True)
                assessment = evaluator.assess(board, (7, 7), BLACK)
                self.assertEqual(assessment.legal, legal)
                self.assertEqual(len(assessment.threes), count)
                if extension_violation:
                    for extension in ((7, 4), (7, 8)):
                        self.assertEqual(evaluator.assess(assessment.board, extension, BLACK).violation, extension_violation)
                if legal:
                    result = apply_move(state, 8, 8, "black")
                    facts = threat_view_payload(result)["tactical_facts"]["black"]["lines"]
                    represented = {tuple(map(tuple, fact["stones"])) for fact in facts if fact["kind"] == "open_three"}
                    self.assertTrue(all(tuple((r + 1, c + 1) for r, c in three.stones) in represented for three in assessment.threes))
                    if count == 1:
                        self.assertNotIn(((8, 6), (8, 7), (8, 8)), represented)
                else:
                    self.assertEqual(assessment.violation, "black_double_three")

    def test_wins_and_terminal_facts_use_the_same_assessment(self):
        horizontal = [(8, c) for c in (5, 6, 7, 9, 10)]
        for label, black, white, renju, player, winner in [
            ("black overline", horizontal, [], True, "black", None),
            ("simultaneous five", horizontal + [(r, 8) for r in (4, 5, 6, 7)], [], True, "black", "black"),
            ("white overline", [], horizontal, True, "white", "white"),
            ("freestyle overline", horizontal, [], False, "black", "black"),
        ]:
            with self.subTest(label=label):
                state = position(black, white, renju=renju, player=player)
                before = deepcopy(state)
                value = BLACK if player == "black" else WHITE
                assessment = RuleEvaluator(renju).assess(freeze(state["board"]), (7, 7), value)
                fact = next(f for f in threat_view_payload(state)["tactical_facts"][player]["completion_points"]
                            if (f["row"], f["col"]) == (8, 8))
                self.assertEqual(assessment.winner, winner)
                self.assertEqual(fact.get("forbidden", False), not assessment.legal)
                if winner:
                    self.assertEqual(apply_move(state, 8, 8, player)["winner"], winner)
                    self.assertEqual(fact["line"], [[r + 1, c + 1] for r, c in assessment.winning_line])
                else:
                    with self.assertRaisesRegex(GomokuError, "overline"):
                        apply_move(state, 8, 8, player)
                self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
