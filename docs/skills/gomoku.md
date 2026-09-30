# gomoku

Play on a local board while Codex reads the position and chooses its own moves.

[All skills](../../README.md#skills) · [한국어](gomoku.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/gomoku from https://github.com/smturtle2/codex-skills.
```

Requires a desktop GUI environment, Python 3.11+, and Pygame; the launcher manages the Python dependency through uv. Codex supplies the opponent’s moves.

## Example

```text
Use $gomoku to start a game. I’ll play black on a 15×15 board.
```

## Working files

Keep resumable game state in the project-root-relative `.codex-skills/gomoku/<run-id>/` workspace when no location is requested. An explicit location wins; resume older existing state in place. Retain data needed to resume and clean up only expendable intermediates created by this run.

Closing the board ends the attached wait and preserves the game. Reopening the same workspace resumes it. Reset creates a new game generation; Codex supplies the generation and revision from its current view when moving, so an outdated selection cannot modify a reset or changed board. GUI and CLI updates use the same locked, atomic storage.

## Output

An interactive Pygame board with legal-move checks, win detection, and optional Renju restrictions. Renju checks distinct fours and legally extendable threes through the new stone, including forbidden recursive extensions; an exact five takes precedence over a simultaneous forbidden pattern. White and freestyle wins allow five or more. The public tactical view uses the same rule evaluator as move validation, without choosing or scoring moves. Opening play and board settings remain freely configurable.

[Read the agent instructions](../../skills/gomoku/SKILL.md)
