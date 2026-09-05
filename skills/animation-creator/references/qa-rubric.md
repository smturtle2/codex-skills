# Animation Acceptance and Repair

Read before accepting an action. Use [animation-output-contract.md](animation-output-contract.md) for exact geometry and processing requirements; do not infer them from appearance alone.

## Required Evidence

- Validation reports the planned frame count, non-empty foreground, unclipped edges, expected output files, and component extraction.
- Processing metadata confirms per-slot border stripping, rembg normalization, residue cleanup, actual source dimensions, and any backend fallback.
- Raw-sheet review confirms compliance with the registration and background contract.
- Recorded sheets, frames, and final output have no guide marks, matte residue, opaque blocks, or border pixels.

## Visual Quality

- Character face, proportions, silhouette, markings, palette, outfit, and props match the preserved canonical base.
- Every planned beat changes the pose meaningfully; no frozen duplicates, accidental objects, missing transitions, or redundant micro-steps.
- Adjacent poses maintain camera distance, scale, facing, balance, contact, and body registration.
- The requested action is recognizable and reads continuously without strobing or abrupt timing gaps.
- A loop has a compatible bridge from last to first frame; a non-loop has a clear beginning and end.

Review the contact sheet and playback where available. If playback cannot be inspected, report that limitation and distinguish frame review from motion verification.

## Repair the Smallest Failure

1. Wrong raw poses or sheet: request a new generation for that action using the exact built prompt and required inputs.
2. rembg failure: repair the runtime, or regenerate only when the raw matte is the identified cause.
3. Extraction failure on a visually correct normalized sheet: adjust extraction settings rather than regenerate the character.
4. Repeated failure caused by the motion plan: revise that plan, then regenerate its action.
5. Recreate the canonical base only when the base itself is wrong.

Repair requests are owned by this workflow after reviewing saved artifacts. Do not ask `$image-creator` to run an automatic critique/retry loop. If an identified blocker cannot be resolved, report the unfinished action instead of accepting failed checks.
