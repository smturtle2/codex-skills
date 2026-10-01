# image-creator

Generate or edit raster images and save the returned file directly into your project, including native transparent PNGs when requested.

[All skills](../../README.md#skills) · [한국어](image-creator.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/image-creator from https://github.com/smturtle2/codex-skills.
```

Requires the built-in image generation tool.

Ordinary prompts discourage unrequested grain, speckling, and repetitive microtexture while preserving intentional material detail. Requested texture and authoritative prompts take precedence; edits preserve texture outside the requested changes.

When you request style imitation, the skill uses suitable visual references and describes the traits to borrow in the prompt. Ordinary edits or original artwork alone do not require extra style research.

## Example

```text
Use $image-creator to make a small orange fox mascot with a teal scarf on a transparent background. Save it to assets/fox.png.
```

## Output

A saved image, the exact generation prompt, and verified format, dimensions, and transparency when requested.

[Read the agent instructions](../../skills/image-creator/SKILL.md)
