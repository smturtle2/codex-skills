# <img src="docs/assets/catalog-mark.svg" width="32" height="32" alt=""> codex-skills

A growing collection of skills for Codex. Pick the skills that fit your work.

[Install](#install) · [Browse skills](#skills) · [Contribute](CONTRIBUTING.md) · [한국어](README.ko.md)

<a id="install"></a>

## Install

Choose a name from the catalog and ask Codex:

```text
Use $skill-installer to install skills/<skill-name> from https://github.com/smturtle2/codex-skills.
```

Then invoke it with `$skill-name` and describe your task. Each guide includes a ready-to-copy install prompt, an example, and tool requirements. If an installed skill does not appear, restart Codex.

<a id="skills"></a>

## Skills

Browse by name. Guides explain usage; instructions define how Codex carries out the work.

<!-- skills:start -->

### animation-creator

Build an action from distinct motion beats, using a shared character reference across generated frames.

[Guide](docs/skills/animation-creator.md) · [Instructions](skills/animation-creator/SKILL.md) · [Install](docs/skills/animation-creator.md#install)

### epub-translator

Translate an EPUB into a new edition with consistent terminology and continuity across chapters.

[Guide](docs/skills/epub-translator.md) · [Instructions](skills/epub-translator/SKILL.md) · [Install](docs/skills/epub-translator.md#install)

### gomoku

Play on a local board while Codex reads the position and chooses its own moves.

[Guide](docs/skills/gomoku.md) · [Instructions](skills/gomoku/SKILL.md) · [Install](docs/skills/gomoku.md#install)

### idea-scribe

Capture ideas verbatim while keeping a readable brief of what still matters.

[Guide](docs/skills/idea-scribe.md) · [Instructions](skills/idea-scribe/SKILL.md) · [Install](docs/skills/idea-scribe.md#install)

### image-creator

Generate or edit raster images and save the returned file directly into your project, including native transparent PNGs when requested.

[Guide](docs/skills/image-creator.md) · [Instructions](skills/image-creator/SKILL.md) · [Install](docs/skills/image-creator.md#install)

### podcast-writer

Turn documents, websites, and YouTube sources into a source-grounded monologue, revised through independent content review.

[Guide](docs/skills/podcast-writer.md) · [Instructions](skills/podcast-writer/SKILL.md) · [Install](docs/skills/podcast-writer.md#install)

### subagent-creator

Turn a role brief into custom Codex agent definitions with explicit responsibilities and boundaries.

[Guide](docs/skills/subagent-creator.md) · [Instructions](skills/subagent-creator/SKILL.md) · [Install](docs/skills/subagent-creator.md#install)

### ui-blueprint

Generate a visual blueprint, read its design decisions, then implement the screen in the existing frontend stack.

[Guide](docs/skills/ui-blueprint.md) · [Instructions](skills/ui-blueprint/SKILL.md) · [Install](docs/skills/ui-blueprint.md#install)

### world-simulator

Co-author a setting in the browser Studio, then play a persistent solo RPG through natural-language actions.

[Guide](docs/skills/world-simulator.md) · [Instructions](skills/world-simulator/SKILL.md) · [Install](docs/skills/world-simulator.md#install)

<!-- skills:end -->

## Add or improve a skill

Each folder under [`skills/`](skills/) contains a `SKILL.md` and the supporting files it needs. Usage guides live under [`docs/skills/`](docs/skills/).

See the [contributing guide](CONTRIBUTING.md) for adding, updating, or removing a skill and refreshing this catalog. Examples and custom icons are optional.
