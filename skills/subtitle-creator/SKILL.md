---
name: subtitle-creator
description: Create natural SRT or WebVTT subtitles from video, audio, or existing subtitle tracks, using timed speech evidence and contextual composition to refine meaning, segmentation, and timing.
---

# Subtitle Creator

Build subtitles from timed speech evidence through contextual interpretation, translation where needed, annotation cleanup, segmentation, timing refinement, and review. The main agent owns evidence acquisition, shared context, terminology, tone, work allocation, and final acceptance. Workers compose their assigned passages; the helper reads and writes timed data and checks coverage, timing values, and publication consistency.

Use the requested target language, defaulting to the user's language. Confirm that supplied media and subtitle tracks refer to the same edition and establish their time-axis relationship. Deliver a separate subtitle file at the requested destination; otherwise choose a descriptive filename with the target language, preserving a supplied subtitle format or using SRT for media-only input.

Set `SKILL_DIR` to this skill's absolute directory and run from the session project root. Keep working files in `.codex-skills/subtitle-creator/{run_id}/` unless the user chooses another workspace. Use a unique ID for new work and resume existing runs at their original paths, including older locations. Retain native recognition results, decisions, completed passages, and recovery data; remove only expendable intermediates created by this run.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.

## Acquire Evidence and Delegate

Read [references/work-data.md](references/work-data.md) before preparing or editing a run. Existing subtitles supply the initial timed evidence:

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" inspect \
  --input "{subtitle_path}" --workdir "{run_dir}"
```

When subtitles are absent, read [references/audio-evidence.md](references/audio-evidence.md), recognize the full requested media range through an already usable local runtime, and prepare its timed observations using the same work-data contract. Record completed and unresolved recognition ranges and retain the native results. Successful range processing supplies evidence; assess its content and any empty result before accepting it.

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" prepare \
  --evidence "{evidence_path}" --workdir "{run_dir}"
```

Read the timed source and available context to establish coherent passage boundaries and shared name, term, relationship, and tone decisions. Keep those decisions compact in the run's notes and update them when later context changes an interpretation.

Default composition workers to the latest Terra model available through the host, with reasoning effort `max`; resolve the concrete model when dispatching and honor an explicit user override. Report an unavailable requested model or reasoning setting.

Assign coherent contiguous passages with enough neighboring source to interpret references and sentence boundaries. Give each worker its owned source IDs, source and target language, shared decisions, available speech evidence, delivery constraints, and the work-data contract. Workers return results for their owned IDs for the main agent to merge; neighboring passages remain context. Parallelize independent passages within available capacity.

## Compose Subtitles

- Preserve meaning, speaker intent, relationships, and tone in natural target-language speech. Treat subtitle tracks and recognition results as fallible observations, using surrounding dialogue and available audio to resolve their meaning. Keep important remaining uncertainty in working notes and the completion report.
- Remove non-dialogue sound, music, and situation descriptions by their meaning. Preserve dialogue sharing the same cue, and retain useful speaker information as working context. Interpret spoken or sung content according to the requested content scope.
- Distinguish rolling-caption duplication from repeated speech using neighboring cues and available audio. Reconstruct sentence meaning across source cue boundaries before choosing the target cuts.
- Split and merge cues around meaning, speech rhythm, speaker changes, and reading time. Keep phrases together where the target language needs them, and use concise phrasing that preserves the intended information. Apply the requested delivery specifications and use timing measurements to locate passages needing attention.
- Keep delivered cue text focused on the composed subtitles. Store explanations, evidence requests, and accepted limitations in the work data.

When a passage remains unclear, collect its original-time range and relevant context, then use [references/audio-evidence.md](references/audio-evidence.md) to obtain targeted recognition. Use operational GPU execution when supported and CPU otherwise. Retain the additional observation separately and continue independent composition while resolving the passage.

Use available word times, alignment, and direct audio review to support timing decisions. With subtitles alone, use the source times to improve segmentation and report that speech synchronization was not verified. Each worker reviews its passage; the main agent reconciles passage joins, shared decisions, and sections changed by new evidence.

## Export and Finish

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check --workdir "{run_dir}"
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" export \
  --workdir "{run_dir}" --output "{output_path}"
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check \
  --workdir "{run_dir}" --output "{output_path}"
```

Review `errors`, `blockers`, `warnings`, and timing measurements. Resolve pending decisions, reconcile requested recognition coverage, and account for every source cue through a composed group or an explicit omission. After changing work data, export again and check the published file. Structural checks establish processing coverage, correspondence, and file consistency; meaning and synchronization require content and media evidence.

Report the actual saved subtitle and run paths, source and recognition coverage, removed annotation categories, recognition used, timing evidence and review performed, and remaining limitations. Claim completion after the requested acquisition and passage reviews are complete, `export_ready` is true, and the published file matches the accepted work data.
