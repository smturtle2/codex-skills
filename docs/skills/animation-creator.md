# animation-creator

Build an action from distinct motion beats, using a shared character reference across generated frames.

[All skills](../../README.md#skills) · [한국어](animation-creator.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/image-creator and skills/animation-creator from https://github.com/smturtle2/codex-skills.
```

Install `image-creator` too. Local helpers use `uv` and rembg for frame processing.

## Example

Provide a character image with the request below. You can also describe a new character to generate a base reference first.

```text
Use $animation-creator to make this fox wave and settle back into its idle pose as a looping WebP.
```

## Working files

When a run needs working or resumable files, use the project-root-relative `.codex-skills/animation-creator/<run-id>/` workspace. An explicitly requested work location wins; resume an existing older location in place. Keep resumable data, remove only expendable intermediates created by this run, and put final deliverables at the destinations requested by the user.

## Output

Animated WebP files plus the canonical reference, frame sheets, extracted frames, contact sheets, and validation records.

[Read the agent instructions](../../skills/animation-creator/SKILL.md)
