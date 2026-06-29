# QA Rubric

Do not accept an animation action until automatic checks and visual review pass.

## Geometry

- The action has exactly the requested frame count.
- Each frame contains a non-empty foreground pose.
- No important pixels touch the frame edge.
- Contact sheets show whole poses inside cells, not cropped tiles from a larger image.
- The final animation output exists in the requested format.
- Final frames preserve the generated sheet's actual per-cell size after rembg normalization and component extraction.

## Character Consistency

- Same character identity as the canonical base.
- Same face, proportions, silhouette, markings, palette, outfit, and prop design.
- No frame introduces an unintended character, object, logo, or symbol.
- Pose changes serve the action instead of redesigning the character.

## Animation Quality

- The frame action list was built sequentially, audited, and revised before generation.
- The action has neither missing transition beats nor redundant duplicate beats.
- Each planned beat states a visible change from the previous beat while preserving scale, facing, body-center path, contact, balance, and weight transfer.
- The requested action is recognizable.
- Adjacent frames keep consistent camera distance, character scale, facing direction, rendering density, and body registration.
- Pose spacing feels smooth during playback, with no accidental strobing, frozen duplicates, abrupt timing gaps, or missing in-between beats.
- Looping actions have compatible first and last frames.
- Non-looping actions have a clear start and end pose.

## Extraction Fitness

- The canonical base preserves the source or generated identity reference without rembg damage.
- Raw generated action sheets use one flat vivid sky-blue removable matte background `#00B7FF`.
- No foreground character pixel, prop, marking, outline, highlight, shadow, or motion effect uses the reserved matte color `#00B7FF`.
- Raw action sheets preserve the outer black cell borders as registration marks.
- Recorded action sheets are true alpha PNGs produced by cutting the raw sheet into planned slots from the actual generated size, stripping outer black cell borders before rembg, running rembg per stripped slot, cleaning matte-color residue, and reassembling the sheet.
- Raw action sheets do not contain scene backgrounds, floor lines, shadows, glows, gradients, textures, or fake checkerboard transparency.
- Raw action sheets do not copy inner safe boxes, centerlines, guide marks, labels, frame numbers, or ghost characters.
- Recorded sheets, extracted frames, and final animations do not retain outer borders or guide lines.
- Component extraction is required in the default finalize path.
- Slot extraction is a manual diagnostic mode only. If the default finalize path used slot extraction, treat the action as failed.
- No matte-background residue or opaque background block remains in final frames.

## Repair Policy

Repair the smallest failing scope:

1. If the raw action sheet is wrong, regenerate that action grid from the exact built prompt and input images.
2. If rembg fails, fix the rembg runtime or regenerate with a cleaner flat matte raw image.
3. Adjust extraction settings only when the rembg-normalized action sheet is visually correct and the failure is clearly extraction-specific.
4. Revise the frame action plan only when repeated generations fail for the same motion-planning reason.
5. Recreate the base character only when the canonical base itself is wrong.
