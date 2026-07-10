---
name: image-creator
description: Generate or edit raster images with the built-in image generation tool, use local file paths for every edit or reference input, preserve authoritative prompts or rewrite ordinary requests without changing meaning or exact rendered text, optionally produce true-alpha transparent PNGs, and save the tool-returned file to the requested destination or current project. Use for generated raster assets, image edits, local image references, and transparent-background output; do not use for prompt-only or vector/code-native output.
---

# Image Creator

Generate one raster asset at a time, bind every image input by absolute local path, and save the tool-returned source file with the bundled helper.

## Core Contract

- Use the built-in `image_gen` path. Do not switch to an API or CLI fallback.
- Separate creative instructions from input paths, destination, overwrite permission, and other execution details.
- Preserve the requested subject, action, composition, style, exclusions, and constraints. Do not invent creative details, quality language, camera settings, negative prompts, or aspect-ratio hints.
- Preserve rendered text exactly, including spelling, capitalization, punctuation, language, and line breaks.
- Generate once per requested asset or variant. Retry only when the user asks or the tool returns no generated source file.
- Never overwrite an existing file unless the user explicitly requested replacement.
- Do not inspect, critique, or regenerate the generated result inside this skill. This restriction ends after the saved file is handed back; subsequent workflows may inspect it under their own rules.

## Final Prompt

For an ordinary request, rewrite the creative instructions into concise English suitable for image generation. Keep underspecified details underspecified. Remove execution details from the prompt.

If supplied text is marked as an authoritative or final prompt, pass it through exactly; do not translate, rewrite, reorder, shorten, or append to it. If an authoritative prompt mixes execution details into the prompt or lacks a required transparency matte instruction, request a corrected final prompt instead of modifying it.

For an ordinary request with image inputs, state each input's user-given role without describing or transcribing its contents:

```text
[Generation instructions.]

Input images:
- [file name]: [user-given role].
```

Before generation, show the exact final prompt for information only. Do not wait for approval unless a required path, destination, or transparency decision is unresolved.

## Image Inputs and Tool Call

Require an absolute local path for every edit target and reference image. Resolve relative paths against the project root. If an attachment or previously generated image has no local path, ask the user to provide one before generation.

Do not call `view_image` to prepare, verify, load, or attach an input for this workflow. Passing the absolute paths in `referenced_image_paths` is sufficient. Use `view_image` only for a separate user-requested image-inspection task outside this generation workflow.

Call `image_gen` with exactly the applicable shape:

- New image: `{prompt}`
- Any edit or reference input: `{prompt, referenced_image_paths: [absolute paths...]}`

Include every input path in `referenced_image_paths`, in the same order as its role in the prompt. If the tool fails or returns no generated source path, stop and report the actual result.

## Transparent PNG Branch

Enter this branch only when the user explicitly requests transparency, alpha, or a transparent background. A `.png` filename alone does not request transparency.

1. Resolve the destination before generation. If the user supplied a non-PNG file destination, ask to change it to `.png`; do not generate until resolved.
2. Select the first matte that does not conflict with an explicitly required foreground color, in this order: `#00B7FF`, `#FF00FF`, `#00FF00`. If all three explicitly conflict, stop and report that no supported matte is safe.
3. For an ordinary rewritten prompt, require a single flat background of the selected matte and reserve that color for background pixels only. Exclude checkerboards, gradients, textures, scenery, floors, horizons, cast or contact shadows, glows, and detached background effects. An authoritative final prompt must already include these instructions; do not append them yourself.
4. Call `image_gen` once, then pass its generated PNG source path to the helper with `--transparent --matte <HEX>`. If the generated source is not PNG, stop; do not convert it or save an opaque fallback.
5. Accept only a helper-produced true-alpha PNG. The helper uses `rembg` with the `birefnet-general-lite` model, prefers an available GPU provider, retries once on CPU after a GPU failure, removes matte residue, validates RGBA output with at least one transparent pixel, and publishes atomically.

If transparent processing fails, stop with the helper error. Do not save the opaque matte image, substitute another background-removal method, or return an opaque fallback.

## Save the Tool Output

Set `SKILL_DIR` to the absolute directory containing this `SKILL.md`. Treat the generated source path returned by `image_gen` as the only save source; do not search rollout logs, state databases, temporary directories, or generated-image caches.

Choose an explicit destination file after generation:

- Use the requested file path when given.
- For a requested directory, create a descriptive filename using the generated source suffix, or `.png` for transparent output.
- With no destination, create a descriptive non-overwriting filename in the current project root.

Run:

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/save_generated_image.py" \
  --source <generated-source-path> \
  --destination <destination-file> \
  --json
```

Add `--overwrite` only with explicit replacement permission. For transparent output, add `--transparent --matte '<selected-hex>'`; always quote the `#RRGGBB` value in a shell command. When a path relative to a handoff root is requested, add `--relative-to <root>` and use the returned `relative_path`; keep external history or metadata updates outside this skill.

The helper preserves the generated source and returns `saved_path`, `relative_path`, `suffix`, `transparent`, and `overwritten`. On helper failure, report the error and do not claim that the asset was saved.

For multiple assets, complete the generation-and-save cycle for one asset before starting the next.

## Response

Report:

- `saved_path`
- the exact final prompt sent to `image_gen`
- the absolute input paths and their roles, if any
- whether transparent processing was used
- whether an existing file was overwritten
- `relative_path` when requested
