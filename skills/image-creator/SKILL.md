---
name: image-creator
description: Generate or edit raster images with the built-in image tool and save them locally, including transparent PNGs. Use for bitmap assets and image edits, not prompt-only requests or vector/code-native artwork.
---

# Image Creator

Complete one generation-and-save cycle per requested asset or variant. Use the built-in `image_gen` tool without API or CLI fallbacks.

## Prepare the Request

- Separate creative instructions from input paths, destination, and overwrite permission.
- For ordinary requests, write concise English preserving the subject, action, composition, style, exclusions, and exact rendered text. Leave unspecified details open; do not add quality claims, camera settings, negative prompts, or aspect-ratio hints.
- Pass text explicitly designated as an authoritative or final prompt unchanged. If it conflicts with the requested background or mixes in execution details, request a corrected final prompt.
- Show the final prompt before generation for information, without adding an approval step. Use the destination defaults below when none was supplied.

## Inputs and Generation

Resolve edit targets and reference images to absolute local paths, relative to the project root when necessary. If an input has no local path, ask for the missing path. Identify each input by filename and its user-given role in ordinary prompts.

Inspect local inputs when required by the current tool instructions; do not turn input inspection into permission to invent creative details or text overrides.

- New image: pass `prompt`.
- Edit or reference image: also pass every input in `referenced_image_paths`, in the order of its prompt role.
- Use only arguments exposed by the current tool. Tool instructions govern invocation and result delivery.
- If the tool fails or provides no generated source file, report the actual failure and stop. Do not retry automatically.

Do not critique or regenerate the output within this skill. A calling workflow may inspect the saved result and request a separate repair attempt.

## Transparent Output

Apply this branch only to an explicit transparency or alpha request; a `.png` filename alone is insufficient.

1. Use a PNG destination. Resolve an explicitly requested incompatible file format before generation.
2. Request a real transparent background with an alpha channel directly in an ordinary prompt. Preserve authoritative prompts unchanged and resolve conflicts. Do not introduce a matte or unrequested restrictions on visual effects.
3. Save with `--require-transparency`. The helper checks PNG format plus non-opaque and visible pixels; it does not judge whether the background is visually correct.
4. On verification failure, report the error without local background removal, re-encoding, an opaque substitute, or automatic regeneration.

## Save

Set `SKILL_DIR` to the absolute directory containing this file. Use only the generated source path returned by the tool; do not search logs, state databases, temporary directories, or image caches.

Use the requested destination file. For a directory or no destination, choose a descriptive, non-overwriting filename using the returned suffix (PNG for transparency), under that directory or the current project root.

```bash
uv run --project "$SKILL_DIR" "$SKILL_DIR/scripts/save_generated_image.py" \
  --source <returned-source-path> --destination <destination-file> --json
```

Add `--require-transparency` for transparent output, `--overwrite` only with explicit replacement permission, and `--relative-to <root>` when a relative handoff path is requested. The helper copies the source byte for byte. On failure, report its error without claiming the file was saved.

## Handoff

Return the saved file link, exact final prompt, input paths and roles, actual dimensions and format, transparency request/check status, and overwrite status. Include the helper's `relative_path` when requested. Dimensions describe the returned file, not a guaranteed generation size.
