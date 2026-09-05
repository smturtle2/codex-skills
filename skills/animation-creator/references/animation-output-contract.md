# Animation Output Contract

Read before action-sheet generation. This describes the existing rembg pipeline; native transparency support in the image generator does not replace its input contract.

## Run Files

Under the project-local run directory:

- `animation_manifest.json`: character, canonical base, action plans, timing, geometry, and removal configuration.
- `animation-jobs.json`: job status, prompts, input/output paths, hashes, timestamps, and recorded processing metadata.
- `references/canonical-base.png`: preserved identity image.
- `references/registration-guides/<action-id>.png`: action edit template.
- `prompts/base-character.md` and `prompts/actions/<action-id>.md`: helper-owned prompts.
- `generated/raw/<job-id>.png`: raw generated source; `generated/<job-id>.png`: recorded base or normalized action sheet.
- `generated/attempts/`: unselected generation attempts.
- `generated/rembg-work/<job-id>/`: per-slot removal work.
- `frames/<action-id>/`: extracted transparent PNG frames.
- `final/<action-id>.webp`, `final/<action-id>-frames.png`, and `final/<action-id>-validation.json`: animation, frame sheet, and validation.
- `qa/<action-id>-contact-sheet.png`, `qa/<action-id>-review.json`, and `qa/run-summary.json`: review artifacts.

## Sheet Geometry

Registration guides use a fixed `4x3` grid at `1448x1086`, nominal `362x362` cells, and safe margins of 30 horizontal and 24 vertical pixels. Use 1–12 planned frames, ordered left-to-right then top-to-bottom. Each used cell holds one complete pose; unused cells remain empty.

Preserve the guide's layout, boundaries, and outer black cell borders. Replace guide characters with the planned poses and remove inner safe boxes, centerlines, labels, numbers, and ghost characters. Preserve identity, scale, facing, body registration, and camera distance across cells.

Processing uses the actual generated sheet dimensions. Do not assume the tool returned the nominal guide resolution.

## Raw Background and Normalization

Raw action sheets require one flat vivid sky-blue `#00B7FF` matte, reserved exclusively for background pixels. Do not use it in characters, props, markings, effects, outlines, or highlights.

Exclude scene backgrounds, floors, horizons, gradients, textures, fake checkerboards, cast/contact shadows, glows, dust, and landing marks. These interfere with extraction.

Recording an action performs this sequence:

1. Cut the raw sheet into planned slots at its actual size.
2. Strip outer black borders from each crop.
3. Run rembg on each stripped slot and clean matte residue.
4. Reassemble the alpha-normalized sheet and record processing metadata.

The manifest uses `background_mode: "rembg-matte"`, `removal_background.hex: "#00B7FF"`, and required `background_removal.engine: "rembg"`. The removal model is `birefnet-general-lite`; the uv project declares `rembg[gpu,cli]`.

The runtime selects CUDA or ROCm when available, otherwise CPU. If a detected GPU provider fails, retry that slot once on CPU and record the backend and fallback reason. If neither works, the job fails; there is no alternate key-color path. Never run rembg on the canonical base.

## Extraction

Finalization requires component extraction from the normalized alpha sheet. Only planned slots contribute frames; unused slots are cleared. Slot extraction is a manual diagnostic, not an acceptable finalization substitute.

Recorded sheets, extracted frames, and final WebP must retain real alpha and contain no cell borders or guides. MP4 diagnostic previews may use an opaque background, but do not satisfy the final WebP contract.
