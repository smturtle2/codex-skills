# Animation Output Contract

## Run Layout

All paths are project-local by default. A normal run lives under:

```text
<session-project>/animation-runs/<run-id>/
  animation_request.json
  animation-jobs.json
  prompts/
    base-character.md
    actions/<action-id>.md
  references/
    canonical-base.png
    source-character.*
    layout-guides/<action-id>.png
  generated/
    base-character.png
    <action-id>.png
  frames/
    <action-id>/00.png
    <action-id>/01.png
    ...
    frames-manifest.json
  final/
    <action-id>.webp
    <action-id>.gif
    <action-id>-frames.png
    validation.json
  qa/
    <action-id>-contact-sheet.png
    <action-id>-preview.gif
    run-summary.json
```

The exact final files depend on the requested output format.

`render_preview.py --write-final` writes final animated files under `final/`, including `final/<action-id>.gif` when `gif` is in `--formats`.

## Required Manifest Fields

`animation_request.json` should record:

- `character_id`
- `character_name`
- `description`
- `canonical_base`
- `frame_width`
- `frame_height`
- `default_frame_count`
- `fps`
- `loop`
- `background_mode`
- `chroma_key`
- `actions`

`animation-jobs.json` should record each base/action job, source path, output path, prompt file, input images, status, and timestamps.

## Geometry

Defaults:

- frame size: `512x512`
- safe margin: `28px` per side, leaving a normal safe area of `456x456`
- frame count: `6`
- FPS: `8`
- output format: `webp`
- final GIF: `final/<action-id>.gif`

Each action image should be a grid sheet with exactly `frame_count` invisible cells read left-to-right, top-to-bottom. Each cell contains one complete centered pose. The generated sheet size may vary, but extraction normalizes every final frame to `512x512`.

Extraction should preserve a transparent safety inset and scale oversized poses down to stay inside the safe area. This mirrors the hatch-pet pattern: avoid edge contact first, then validate for clipping.

Recommended layouts:

| Frames | Layout |
| ---: | --- |
| 1-4 | `2x2` or smaller as needed |
| 5-6 | `3x2` |
| 7-8 | `4x2` |
| 9 | `3x3` |
| 10-12 | `4x3` |
| 13-16 | `4x4` |

Use `6` frames in a `3x2` grid by default. Treat `12` frames as the normal single-sheet upper bound and `16` as experimental. Split longer animations into multiple action sheets.

## Background

Default background mode is `chroma-key`, because clean background removal and connected-component extraction are central to reliable frame extraction.

The chroma key must not appear in the character, outfit, props, highlights, shadows, or effects. Prefer a high-saturation key color far from source image colors. Use green by default, matching the hatch-pet path, because it collides less often with mouths, blushes, and warm character accents. Extraction removes exact chroma-key pixels everywhere, including holes inside a character silhouette. It also removes exposed chroma-family components that touch transparent/erased background, including dark antialias edges and darker/lighter remnants around internal holes or shadows, while preserving chroma-adjacent pixels embedded in the character body. Validation fails frames that still contain too many non-transparent pixels close to the chroma key.

Transparent output is preferred for GIF/WebP frame assets. MP4 previews may use a checkerboard or flat background because MP4 does not carry alpha.
