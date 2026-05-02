# QA Rubric

Do not accept an animation action until the automatic checks and visual review pass.

## Geometry

- Final frames preserve the generated sheet's actual per-cell size after component or slot extraction.
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

- The requested action is recognizable.
- Poses progress through one readable continuous motion, not repeated copies of the same still or disconnected pose studies.
- Adjacent frames keep consistent camera distance, character scale, facing direction, rendering density, and body registration.
- The body center, head, hands, and feet move along plausible arcs without unexplained teleports, pops, flips, or sudden scale changes.
- Pose spacing feels smooth during playback, with no accidental strobing, frozen duplicates, abrupt timing gaps, or missing in-between beats.
- Timing uses readable easing, anticipation, follow-through, overshoot, and settle when the motion needs them.
- Looping actions have compatible first and last frames.
- Non-looping actions have a clear start and end pose.

## Extraction Fitness

- Component extraction is preferred, matching the hatch-pet path, because it removes generated layout margins while preserving generated frame scale.
- Known-layout slot extraction is the fallback when components cannot be separated and must still preserve the generated slot size.
- No generated cell border, registration-guide, safe-box, or centerline pixels appear in extracted frames.
- No detached effects create separate components that confuse extraction.
- No chroma-key-adjacent pixels remain in character-visible regions.

## Repair Policy

Repair the smallest failing scope:

1. Regenerate the failed action grid.
2. Adjust extraction settings only when the generated grid is visually correct.
3. Recreate the base character only when the canonical base itself is wrong.
