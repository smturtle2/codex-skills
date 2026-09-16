# world-simulator

Co-author a setting in the browser Studio, then play a persistent solo RPG through natural-language actions.

[All skills](../../README.md#skills) · [한국어](world-simulator.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/world-simulator from https://github.com/smturtle2/codex-skills.
```

Requires a local browser and Python runtime. Codex directs the story; the runtime stores the world and its history.

## Example

```text
Use $world-simulator to create a city where memories are traded. I want to play an apprentice archivist arriving on their first day.
```

## Working files

The default storage root is `.codex-skills/world-simulator/` relative to the project root. Each world's session ID identifies its run folder beneath it. Keep the world database and assets for continued play, and remove only expendable turn files. Explicit storage locations and existing worlds keep their original paths; requested exports go to their delivery destinations.

## Output

A browser Studio and Play interface, player sheet, worldbook, chronological story, and resumable `world.sqlite3` ledger.

[Read the agent instructions](../../skills/world-simulator/SKILL.md)
