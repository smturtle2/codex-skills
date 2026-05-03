# QA Rubric

Do not accept an animation action until the automatic checks and visual review pass.

## Geometry

- Final frames preserve the generated sheet's actual per-cell size after chroma removal, guide-canvas cleanup, and component extraction.
- The action has exactly the requested frame count.
- Each frame contains a non-empty character pose.
- No important pixels touch the frame edge.
- Visible character pixels stay inside the extracted frame safe inset.
- Contact sheets show whole poses inside cells, not cropped tiles from a larger image.
- The final animation output exists in the requested format.

## Character Consistency

- Same character identity as the canonical base.
- Same face, proportions, silhouette, markings, palette, outfit, and prop design.
- No frame introduces a new unintended character, object, logo, or symbol.
- Pose changes serve the action instead of redesigning the character.

## Animation Quality

- The frame action list was built sequentially, then audited and revised before generation.
- The action has neither missing transition beats nor redundant duplicate beats.
- Each planned beat states a visible change from the previous beat while preserving scale, facing, body-center path, contact, balance, and weight transfer.
- The requested action is recognizable.
- Poses progress through one readable continuous motion, not repeated copies of the same still or disconnected pose studies.
- Adjacent frames keep consistent camera distance, character scale, facing direction, rendering density, and body registration.
- The body center, head, hands, and feet move along plausible arcs without unexplained teleports, pops, flips, or sudden scale changes.
- Pose spacing feels smooth during playback, with no accidental strobing, frozen duplicates, abrupt timing gaps, or missing in-between beats.
- Timing uses readable easing, anticipation, follow-through, overshoot, and settle when the motion needs them.
- Looping actions have compatible first and last frames.
- Non-looping actions have a clear start and end pose.

## Extraction Fitness

- Component extraction is required in the default finalize path, matching the hatch-pet path, because it removes generated layout margins while preserving generated frame scale.
- Known-layout slot extraction is only a manual diagnostic fallback. If the default finalize path used slot extraction, treat the action as failed and regenerate the action sheet.
- Raw generated sheets are expected to keep black cell borders and blue safe-area rectangles, remove gray dashed centerlines and faint guide characters, and use chroma-key background only inside each inner safe area.
- Raw generated sheets must be reviewed before extraction. If the sheet has the wrong grid, missing requested frames, wrong slot order, obvious duplicate stills, broken identity, disconnected motion, visible labels, extra guide marks, malformed or missing safe-area rectangles, or non-chroma safe-area interiors, regenerate the action sheet instead of trying to fix it with post-processing.
- No generated cell border, registration-guide, safe-box, or centerline pixels appear in extracted frames.
- No detached effects create separate components that confuse extraction.
- No exterior-connected chroma-key remnants or visible background halos remain in character-visible regions. Chroma-like colors embedded inside the character are acceptable when they are not connected to the exterior background.

## Repair Policy

Repair the smallest failing scope:

1. If the raw action sheet is wrong, regenerate that action grid from the exact built prompt and input images. Keep rejected attempts for debugging, but record and finalize only the accepted attempt.
2. Adjust extraction settings only when the raw generated grid is visually correct and the failure is clearly post-processing.
3. Revise the frame action plan only when repeated generations fail for the same motion-planning reason.
4. Recreate the base character only when the canonical base itself is wrong.
