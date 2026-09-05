# codex-skills

**English** · [한국어](README.ko.md)

A workbench for thinking, making, and a little play with Codex.

![A workbench with a book, character poses, a screen sketch, and a Gomoku board](docs/assets/workbench.png)

Pick the skills you need. Each folder bundles its instructions and supporting files.

[Organize & write](#write) · [Make & build](#make) · [Play & explore](#play)

## Get started

Ask Codex to install a skill. Replace `<skill-name>` with a name from the catalog below.

```text
Use $skill-installer to install skills/<skill-name> from https://github.com/smturtle2/codex-skills.
```

Invoke an installed skill with `$skill-name`. If a new skill does not appear, restart Codex. [Official skill guide](https://learn.chatgpt.com/docs/build-skills)

The prompts below are usage examples. Check each output and tool requirement before choosing.

<a id="write"></a>

## Organize & write

### <img src="skills/idea-scribe/assets/icon.svg" width="28" height="28" alt=""> idea-scribe

**Think aloud. Keep the thread.**

Capture ideas verbatim while keeping a readable brief of what still matters.

```text
Use $idea-scribe. I’ll think aloud about a neighborhood book club. Record and organize without interrupting.
```

**Output** — `raw.txt` preserves the original stream; `organized.html` holds the current brief.

![An example Idea Scribe brief](docs/assets/idea-scribe-preview.png)

*Rendered from the bundled HTML template with sample book-club content.*

[Read the skill](skills/idea-scribe/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/idea-scribe from https://github.com/smturtle2/codex-skills.
```

</details>

### <img src="skills/epub-translator/assets/icon.svg" width="28" height="28" alt=""> epub-translator

**A book that reads naturally in another language.**

Translate an EPUB into a new edition with consistent terminology and continuity across chapters.

```text
Use $epub-translator to translate book.epub into Korean, preserving names consistently throughout the book.
```

**Output** — A translated `.epub`, working translation files, and a validation summary. Reading order, links, and image placement guide the rebuild.

Also install `image-creator` when text inside raster images needs translation.

[Read the skill](skills/epub-translator/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/epub-translator from https://github.com/smturtle2/codex-skills.
```

</details>

### <img src="skills/podcast-writer/assets/icon.svg" width="28" height="28" alt=""> podcast-writer

**Sources into something worth listening to.**

Turn documents, websites, and YouTube sources into a source-grounded monologue, revised through independent content review.

```text
Use $podcast-writer to turn these sources into a 10-minute solo episode for beginners. Save the script as plain text.
```

**Output** — A `.txt` file containing only the spoken script, ready for a separate TTS or recording step.

Requires subagent tools for content review. YouTube audio transcription fallback requires a compatible GPU; captions are used first.

[Read the skill](skills/podcast-writer/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/podcast-writer from https://github.com/smturtle2/codex-skills.
```

</details>

<a id="make"></a>

## Make & build

### <img src="skills/image-creator/assets/icon.svg" width="28" height="28" alt=""> image-creator

**From a description to a project asset.**

Generate or edit raster images and save the returned file directly into your project, including native transparent PNGs when requested.

```text
Use $image-creator to make a small orange fox mascot with a teal scarf on a transparent background. Save it to assets/fox.png.
```

**Output** — A saved image, the exact generation prompt, and verified format, dimensions, and transparency when requested.

Requires the built-in image generation tool. The banner above was made with this workflow.

[Read the skill](skills/image-creator/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/image-creator from https://github.com/smturtle2/codex-skills.
```

</details>

### <img src="skills/animation-creator/assets/icon.svg" width="28" height="28" alt=""> animation-creator

**One character. More ways to move.**

Build an action from distinct motion beats, using a shared character reference across generated frames.

```text
Use $animation-creator to make this fox wave and settle back into its idle pose as a looping WebP.
```

**Output** — Animated WebP files plus the canonical reference, frame sheets, extracted frames, contact sheets, and validation records.

Install `image-creator` too. Local helpers use `uv` and rembg for frame processing.

[Read the skill](skills/animation-creator/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/image-creator and skills/animation-creator from https://github.com/smturtle2/codex-skills.
```

</details>

### <img src="skills/ui-blueprint/assets/icon.svg" width="28" height="28" alt=""> ui-blueprint

**See the screen before building it.**

Generate a visual blueprint, read its design decisions, then implement the screen in the existing frontend stack.

```text
Use $ui-blueprint to redesign the reading dashboard in this app. Show current books, reading progress, and recent notes.
```

**Output** — A saved mockup under `ui-blueprints/`, an implemented screen, and desktop/mobile visual verification.

Install `image-creator` too. Designed for new screens and substantial redesigns.

[Read the skill](skills/ui-blueprint/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/image-creator and skills/ui-blueprint from https://github.com/smturtle2/codex-skills.
```

</details>

### <img src="skills/subagent-creator/assets/icon.svg" width="28" height="28" alt=""> subagent-creator

**Give a specialist a clear job.**

Turn a role brief into custom Codex agent definitions with explicit responsibilities and boundaries.

```text
Use $subagent-creator to create one read-only reviewer that checks accessibility and reports findings with file references.
```

**Output** — Validated TOML definitions, saved to the personal agents directory by default. Project scope and preview-only output are available on request.

Creates definitions; running the agents is a separate step.

[Read the skill](skills/subagent-creator/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/subagent-creator from https://github.com/smturtle2/codex-skills.
```

</details>

<a id="play"></a>

## Play & explore

### <img src="skills/world-simulator/assets/icon.svg" width="28" height="28" alt=""> world-simulator

**Build a world. Live with the consequences.**

Co-author a setting in the browser Studio, then play a persistent solo RPG through natural-language actions.

```text
Use $world-simulator to create a city where memories are traded. I want to play an apprentice archivist arriving on their first day.
```

**Output** — A browser Studio and Play interface, player sheet, worldbook, chronological story, and resumable `world.sqlite3` ledger.

Requires a local browser and Python runtime. Codex directs the story; the runtime stores the world and its history.

[Read the skill](skills/world-simulator/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/world-simulator from https://github.com/smturtle2/codex-skills.
```

</details>

### <img src="skills/gomoku/assets/icon.svg" width="28" height="28" alt=""> gomoku

**Take a break. Make your move.**

Play on a local board while Codex reads the position and chooses its own moves.

```text
Use $gomoku to start a game. I’ll play black on a 15×15 board.
```

**Output** — An interactive Pygame board with legal-move checks, win detection, and optional Renju restrictions.

Requires a desktop GUI environment and Python with Pygame. Codex supplies the opponent’s moves.

[Read the skill](skills/gomoku/SKILL.md)

<details>
<summary>Install prompt</summary>

```text
Use $skill-installer to install skills/gomoku from https://github.com/smturtle2/codex-skills.
```

</details>

## Inside the repository

- [`skills/`](skills/) — per-skill instructions, scripts, references, runtime assets, and icons.
- [`docs/assets/`](docs/assets/) — README banner and example screenshot.

## Contributing

Bundle a clear trigger in `SKILL.md` with the files the skill needs. Keep instructions concise and helper scripts locally auditable. Include an icon and agent metadata, and update both language versions of this README.
