---
name: subtitle-translator
description: Translate English SRT or WebVTT subtitles into natural target-language subtitles, using contextual translation workers and available audio evidence to refine unclear speech, segmentation, and timing.
---

# Subtitle Translator

The main agent owns shared context, terminology, tone, speech evidence, passage boundaries, and final acceptance. Translation workers interpret and translate their assigned passages, remove non-dialogue annotations, and propose segmentation and timing. The helper reads and writes subtitles, calculates timing measurements, and checks structural completeness.

Use the requested target language, defaulting to the user's language. Confirm the source subtitle and any supplied media refer to the same edition and timeline before using the media as timing evidence. Deliver a separate translated subtitle file at the requested destination; otherwise choose a descriptive filename with the target language and the source format.

Set `SKILL_DIR` to this skill's absolute directory and run from the session project root. Keep working files in `.codex-skills/subtitle-translator/<run-id>/` unless the user chooses another workspace. Use a unique ID for new work and resume existing runs at their original paths, including older locations. Retain translation decisions, completed passages, and recovery data; remove only expendable intermediates created by this run.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.

## Prepare and Delegate

Read [references/work-data.md](references/work-data.md) before creating or editing work data. For a new run:

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" inspect \
  --input <source.srt-or-vtt> --workdir <run-dir>
```

Read the source cues and available context to establish useful passage boundaries and shared name, term, relationship, and tone decisions. Keep those decisions compact in the run's working notes and update them when later context changes an interpretation.

Default translation workers to the newest Terra model available through the host, with reasoning effort `max`; resolve the concrete model when dispatching and honor an explicit user override. Report unavailable dispatch requirements before claiming worker translation was performed.

Assign coherent contiguous passages with enough neighboring source to interpret references and sentence boundaries. Give each worker its owned source IDs, source and target language, shared decisions, available speech evidence, requested delivery constraints, and the work-data contract. Workers return results for their owned IDs for the main agent to merge; neighboring context remains context. Parallelize independent passages within available capacity.

## Translate and Compose

- Preserve meaning, speaker intent, relationships, and tone in natural target-language speech. Treat automatic captions and additional recognition as fallible observations, using surrounding dialogue and available audio to resolve their meaning. Keep any important remaining uncertainty in working notes and the completion report.
- Remove non-dialogue sound, music, and situation descriptions by their meaning. Preserve dialogue sharing the same cue, and retain useful speaker information as working context. Interpret spoken or sung content according to the requested content scope.
- Distinguish rolling-caption duplication from repeated speech using neighboring cues and available audio. Reconstruct sentence meaning across source cue boundaries before choosing the target cuts.
- Split and merge cues around meaning, speech rhythm, speaker changes, and reading time. Keep phrases together where the target language needs them, and use concise phrasing that preserves the intended information. Apply the requested delivery specifications and use timing measurements to locate passages needing attention.
- Keep delivered cue text focused on the translated content. Store explanations, evidence requests, and accepted limitations in the work data.

Let uncertainty arise during translation. For unclear speech in automatic captions, collect the affected original-time ranges and relevant context, then read [references/audio-evidence.md](references/audio-evidence.md). Obtain targeted recognition through an already usable local runtime, using operational GPU execution when supported and CPU otherwise. Continue independent text work while resolving these passages.

Use available word times, alignment, and direct audio review to support timing decisions. With subtitles alone, use the source times to improve segmentation and report that speech synchronization was not verified. Each worker reviews its passage; the main agent reconciles passage joins, shared decisions, and sections changed by new evidence.

## Export and Finish

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check --workdir <run-dir>
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" export \
  --workdir <run-dir> --output <translated.srt-or-vtt>
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check \
  --workdir <run-dir> --output <translated.srt-or-vtt>
```

Review `errors`, `blockers`, `warnings`, and timing measurements. Resolve pending decisions and account for every source cue through a translated group or an explicit omission. After changing work data, export again and check the published file. The structural checks establish correspondence and file consistency; translation quality and synchronization require their own evidence.

Report the actual saved subtitle and run paths, translation coverage, removed annotation categories, additional recognition used, timing evidence and review performed, and remaining limitations. Claim completion after the passages and joins have been reviewed, `export_ready` is true, and the published file matches the accepted work data.
