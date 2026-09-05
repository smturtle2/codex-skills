---
name: image-creator
description: Generate or edit raster images with the built-in image generation tool, use local file paths for every edit or reference input, preserve authoritative prompts or rewrite ordinary requests without changing meaning or exact rendered text, request native transparent PNGs when needed, and save the tool-returned file to the requested destination or current project. Use for generated raster assets, image edits, local image references, and transparent-background output; do not use for prompt-only or vector/code-native output.
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
- Do not visually inspect, critique, or regenerate the generated result inside this skill. The helper may read image metadata and verify requested transparency without changing pixels. This restriction ends after the saved file is handed back; subsequent workflows may inspect it under their own rules.

## Final Prompt

For an ordinary request, rewrite the creative instructions into concise English suitable for image generation. Keep underspecified details underspecified. Remove execution details from the prompt.

If supplied text is marked as an authoritative or final prompt, pass it through exactly; do not translate, rewrite, reorder, shorten, or append to it. If an authoritative prompt mixes execution details into the prompt or conflicts with the requested background, request a corrected final prompt instead of modifying it.

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

1. Resolve the destination before generation. Keep PNG as this skill's transparent-output format. If the user supplied a non-PNG file destination, resolve the format with the user before generation.
2. Request an actual transparent background with an alpha channel directly in the generation prompt. Do not introduce a colored matte, color exclusions, or blanket bans on shadows and glows. Preserve the user's visual requirements. Pass authoritative final prompts unchanged; resolve conflicts instead of silently rewriting them.
3. Use only arguments exposed by the current built-in tool. API options such as `background`, `output_format`, and `size` must not be added to a tool call that does not expose them. Express transparency in the prompt when no dedicated parameter exists.
4. Pass the returned source file to the helper with `--require-transparency`. It verifies PNG format and the presence of both non-opaque and visible pixels, then saves an exact copy. This checks file transparency, not the visual correctness of the background.
5. If verification fails, report the helper error. Do not remove the background locally, re-encode the file, publish an opaque fallback, or regenerate automatically.

GPT Image 2 supports native transparency in preview according to the [official image generation guide](https://developers.openai.com/api/docs/guides/image-generation#customize-image-output), checked 2026-09-06. Actual returned-file verification determines whether the output meets this skill's contract.

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

Add `--overwrite` only with explicit replacement permission. For transparent output, add `--require-transparency`. When a path relative to a handoff root is requested, add `--relative-to <root>` and use the returned `relative_path`; keep external history or metadata updates outside this skill.

The helper preserves the generated source byte for byte and returns `saved_path`, `relative_path`, `suffix`, `format`, `width`, `height`, `transparency_requested`, `transparency_verified`, and `overwritten`. Dimensions and format describe the returned file, not a guaranteed generation size. `transparency_verified` is `true` after a successful requested check, or `null` when no transparency check was requested. The former `--transparent` / `--matte` options and `transparent` metadata field are removed; use the new contract above. On helper failure, report the error and do not claim that the asset was saved.

For multiple assets, complete the generation-and-save cycle for one asset before starting the next.

## Response

Report:

- `saved_path`
- the exact final prompt sent to `image_gen`
- the absolute input paths and their roles, if any
- whether transparency was requested and verified
- the actual image dimensions and format
- whether an existing file was overwritten
- `relative_path` when requested
