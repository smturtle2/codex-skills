---
name: image-creator
description: Generate or edit raster images through the same generation path as imagegen while preserving the user's intended image prompt verbatim, including referenced input images, then save the resulting file to the requested destination or the current project root.
---

# Image Creator

Generate images through the same image generation path as `imagegen`, while giving that path the user's intended image prompt as-is and saving the result where the user wants it.

## Hard Rules

- Preserve this skill's prompt policy even when mirroring `imagegen` execution. Do not invoke the `$imagegen` prompt-shaping workflow.
- Do not rewrite, translate, summarize, embellish, sanitize, structure, or otherwise improve the user's intended image prompt.
- Do not add creative details, negative prompts, style labels, quality language, aspect-ratio hints, safety disclaimers, or prompt scaffolding unless the user wrote those words as part of the prompt.
- Preserve exact text the user wants rendered in the image. Keep spelling, capitalization, punctuation, and line breaks.
- Treat destination paths, filenames, and file-loading instructions as execution instructions when they are clearly not part of the creative prompt.
- If the boundary between creative prompt and execution instruction is genuinely unclear and affects output, ask one short clarification before generating.
- Always save the final generated image to the requested destination. If the user gives no destination, save it in the current project root.
- Never overwrite an existing file unless the user explicitly requested replacement.

## Generation Path

Use the same execution path as `imagegen`:

- Use the built-in `image_gen` tool by default for normal generation and editing. This path does not require `OPENAI_API_KEY`.
- Never switch to the CLI fallback automatically.
- If the built-in tool fails or is unavailable, tell the user the CLI fallback exists and requires `OPENAI_API_KEY`. Proceed only if the user explicitly asks for that fallback.
- If the user explicitly asks for CLI mode, use the `imagegen` CLI fallback workflow for execution only. Keep this skill's exact-prompt policy and do not add `imagegen` prompt scaffolding.
- For many requested assets or variants in built-in mode, issue one built-in `image_gen` call per selected asset or variant.

Built-in save-path policy:

- In built-in mode, generated images are saved under `$CODEX_HOME/*` by default.
- Do not rely on OS temp as the default built-in destination.
- Do not rely on a destination-path argument on the built-in `image_gen` tool. Generate first, then copy or move the selected output from `$CODEX_HOME/generated_images/...`.
- If the output is meant for the current project, never leave it only in the default `$CODEX_HOME/*` location.

## When To Use

Use this skill when the user wants to:

- create a new generated image from a prompt
- edit an existing image using a prompt
- use one or more local, attached, or previously generated images as inputs
- save the generated image to a specific file or directory
- get a project-local image asset without prompt rewriting

Do not use this skill for:

- SVG, HTML/CSS, canvas, or vector-native artwork that should be authored as code
- UI blueprint workflows that explicitly require `$ui-blueprint`
- image requests where the user asks for prompt engineering, prompt improvement, or multiple rewritten prompt options

## Workflow

1. Identify the user's intended image prompt.
   - If the user provided a quoted string, fenced block, or explicit "prompt:", use that text exactly.
   - If the user wrote a natural request without an explicit prompt block, pass the image-producing part in the user's own words, removing only clearly operational instructions such as where to save the file.
   - If removing an operational instruction would risk changing the image intent, ask instead of guessing.
2. Decide the execution path.
   - Use built-in `image_gen` unless the user explicitly requested the CLI fallback.
   - Treat existing images as edit targets only when the user clearly asks to change them. Otherwise, treat images as references.
3. Resolve input images.
   - For attached or previously generated images, keep their role exactly as the user described it.
   - For local image paths in built-in mode, resolve them to absolute paths and load each with `view_image` before calling `image_gen` so the image is visible in the conversation context.
   - Do not describe an input image back into the prompt unless the user asked for that description to be part of the prompt.
4. For built-in mode, record a timestamp immediately before calling `image_gen`.
   - Example: `START_EPOCH=$(date +%s)`.
5. For built-in mode, call `image_gen` with only the preserved prompt text.
6. For explicit CLI fallback mode, follow the `imagegen` CLI execution workflow with only the preserved prompt text and any user-requested CLI controls.
7. Inspect the generated result enough to confirm an image exists and the requested input images were considered when applicable.
8. Save the output:
   - If the user gave a file path, save there.
   - If the user gave a directory, save inside it with a descriptive non-overwriting filename.
   - If the user gave no destination, save in the current project root.
   - In built-in mode, use `scripts/save_generated_image.py` to locate the new generated image and copy it to the destination.
   - In explicit CLI fallback mode, use the CLI output controls from the `imagegen` fallback workflow.
9. Report the saved path, the exact prompt text sent to the generation path, the input images used, and whether built-in mode or explicit CLI fallback was used.

## Save Helper

Use the bundled helper after built-in `image_gen` returns:

```bash
python3 skills/image-creator/scripts/save_generated_image.py --since "$START_EPOCH" --destination <path>
```

Options:

- Omit `--destination` to save in the project root.
- Use `--project-root <path>` when the current working directory is not the intended project root.
- Use `--generated-root <path>` only when the generated image directory is known and the default lookup fails.
- Use `--overwrite` only when the user explicitly asked to replace an existing file.

The helper searches for the newest generated image created at or after `--since`, copies it to the destination, creates parent directories as needed, and prints the saved path.

## Response

When finished, report:

- the saved file path
- the exact prompt passed to the generation path
- the input images used, if any
- whether built-in mode or explicit CLI fallback was used
- whether an existing file was overwritten
