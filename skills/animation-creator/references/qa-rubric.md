# QA Rubric

Do not accept an animation action until the automatic checks and visual review pass.

## Geometry

- Final frames match the requested `frame_width x frame_height`.
- The action has exactly the requested frame count.
- Each frame contains a non-empty character pose.
- No important pixels touch the frame edge.
- Contact sheets show whole poses inside cells, not cropped tiles from a larger image.
- The final animation output exists in the requested format.

## Character Consistency

- Same character identity as the canonical base.
- Same face, proportions, silhouette, markings, palette, outfit, and prop design.
- No frame introduces a new unintended character, object, logo, or symbol.
- Pose changes serve the action instead of redesigning the character.

## Animation Quality

- The requested action is recognizable.
- Poses progress through a readable motion, not repeated copies of the same still.
- Looping actions have compatible first and last frames.
- Non-looping actions have a clear start and end pose.

## Extraction Fitness

- Component extraction is preferred over fixed slot slicing.
- Grid slot slicing is acceptable only after visual review confirms each cell contains a complete, unclipped pose.
- No visible layout guide pixels appear in extracted frames.
- No detached effects create separate components that confuse extraction.
- No chroma-key-adjacent pixels remain in character-visible regions.

## Repair Policy

Repair the smallest failing scope:

1. Regenerate the failed action grid.
2. Adjust extraction settings only when the generated grid is visually correct.
3. Recreate the base character only when the canonical base itself is wrong.
