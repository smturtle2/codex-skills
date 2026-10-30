# Subtitle Work Data

Read before acquiring timed evidence, briefing a composition worker, or editing a run. The helper uses UTF-8 JSON and integer milliseconds. Establish the relationship between subtitle, clip, and original-media clocks before authoring media-based evidence or output.

## Prepare Timed Evidence

Existing subtitle tracks already supply timed observations:

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" inspect \
  --input <source.srt-or-vtt> --workdir <run-dir>
```

Use `--encoding <name>` when the subtitle needs a different encoding; the default is `utf-8-sig`. Omitting `--workdir` prints its parsed source snapshot without creating a workspace.

For media without a subtitle track, retain the selected recognizer's native outputs and normalize its observed segments and processing receipt in an evidence file:

```json
{
  "version": 1,
  "media_path": "episode.mp4",
  "requested_range": {"start_ms": 0, "end_ms": 60000},
  "completed_ranges": [
    {"start_ms": 0, "end_ms": 60000, "result_path": "recognition/raw.json"}
  ],
  "pending_ranges": [],
  "segments": [
    {"start_ms": 1500, "end_ms": 3800, "text": "We can discuss it later."}
  ]
}
```

Paths are absolute or relative to the evidence file's directory. `media_path` and each native `result_path` must name an existing file when preparing the source. Use actual recognition results and preserve their original files. Segment times use the original media clock; add clip offsets when the runtime returns clip-relative times.

Record the actual requested range and completed recognition ranges, with any unresolved ranges in `pending_ranges` as `{start_ms, end_ms, reason}` objects. Retain successful results and resume incomplete acquisition in this evidence file. Overlapping completed ranges are combined for coverage; gaps and pending ranges keep the initial evidence incomplete. A completed processing range does not establish that every spoken word was recognized.

If `segments` is empty, review the available speech evidence before accepting a dialogue-free result and add a nonempty `empty_review` explanation. Empty results awaiting that judgment remain incomplete.

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" prepare \
  --evidence <timed-evidence.json> --workdir <run-dir>
```

`prepare` reports `evidence_ready`, recognition coverage, and any `errors`, `blockers`, or `missing_ranges`. It writes no workspace while acquisition is incomplete. Exit `0` means the initial evidence is ready, `1` means the evidence is invalid or incomplete, and `2` means it could not be read or the command could not be completed. Omitting `--workdir` checks and describes the evidence without initializing work.

Both `inspect` and ready `prepare` use the same initializer to create `source.json` and `work.json` in the selected run directory. Acquisition files and working notes can already be there; initialization preserves them and requires that neither `source.json` nor `work.json` exists. Resume saved state when either work file is already present. Composition continues through the same work contract below.

## Source and Work Files

New `source.json` snapshots have `version: 2`, source `path`, `format`, and `encoding` under `source`, a `cues` list, a `metadata` list, and `inputs` listing protected absolute input paths. Each cue has an ID, `start_ms`, `end_ms`, and `text`, with an optional original `identifier` or timing `settings`. IDs `s1`, `s2`, and onward follow observation order independently of original subtitle identifiers.

Subtitle imports use format `srt` or `vtt`. Recognition imports use `timed-evidence`; their `source.path` names the evidence JSON, and `inputs` includes that file, the media, and the native result files. The `recognition` receipt preserves `media_path`, `requested_range`, `completed_ranges`, `pending_ranges`, and any `empty_review`. Once initial evidence is prepared, keep this snapshot as the common source reference; subsequent recognition supplies separate observations for the affected passages. Saved snapshots can be used without requiring the external media and native results to remain present for text publication.

Source text retains markup and inline timestamps, which may carry speaker and timing context. Header, style, region, and comment metadata are archived for reference. WebVTT timestamp mapping can change the relation between the subtitle clock and the media clock. The translated output is a plain display-text subtitle track; compose target text and line breaks accordingly. The writer encodes literal `&`, `<`, and `>` as character references so text is not interpreted as cue markup. Keep the source snapshot as the common reference when resuming or combining worker results.

`work.json` starts with an empty target language and empty collections. Set `target_language` to the selected language and author the results in this shape:

```json
{
  "version": 1,
  "target_language": "ko",
  "groups": [
    {
      "source_ids": ["s1", "s2"],
      "cues": [
        {"start_ms": 1000, "end_ms": 2600, "text": "그때는\n그 사실을 몰랐어요"}
      ]
    }
  ],
  "omitted": [
    {"source_ids": ["s3"], "reason": "Non-dialogue music caption."}
  ],
  "pending": [],
  "notes": ["Timing follows source cues; no matching audio was supplied."]
}
```

One group relates any number of source cues to the authored output cues, allowing sentences to be merged or split. A source ID belongs exactly once across `groups` and `omitted`. Removing a sound annotation from a cue that also contains translated dialogue leaves that cue in its translated group. A group may carry an optional `note`.

Write groups and their output cues in delivery order, with nondecreasing start times. Output and evidence times use the matching media timeline when media is supplied, otherwise the source subtitle timeline. Recognition-derived output stays within its requested range. Each output cue has nonempty display text, no blank lines within the cue, and an end time greater than its nonnegative start time. An annotation-only source can yield an empty track when every source ID is explicitly omitted; reviewed recognition with no relevant speech can enter the same work path with no source cues.

Use `pending` for material decisions awaiting resolution:

```json
{
  "source_ids": ["s4"],
  "reason": "The automatic caption gives an unclear technical term.",
  "start_ms": 17500,
  "end_ms": 21200
}
```

The time range is optional and uses the original media timeline. Pending entries can reference already drafted or unassigned cues and block export. After resolving a decision, update its translation and remove the pending entry. Record an accepted interpretation and important remaining evidence limitations in `notes`; keep them separate from delivered text.

## Worker Results and Resume

Brief a worker with the owned source IDs and their observed text/times, adjacent context, target language, shared terminology and tone decisions, available speech evidence, and relevant delivery specifications. Have it return `groups`, `omitted`, `pending`, and `notes` for its owned range. The main agent merges those results into `work.json`, resolves passage joins, and updates shared decisions.

Preserve completed results when obtaining new evidence or repairing a passage. Resume by reading `source.json`, `work.json`, working notes, and the current check result in the same run directory. Existing version-1 source and work snapshots remain usable in their original locations, including earlier skill workspaces. Initialization creates new work; continuing an existing run uses its saved files without recreating or relocating them.

## Check and Publish

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check --workdir <run-dir>
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" export \
  --workdir <run-dir> --output <translated.srt-or-vtt>
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check \
  --workdir <run-dir> --output <translated.srt-or-vtt>
```

`check` reports `valid` for structurally usable data, `complete` for source coverage with a target language and no pending decisions, and `export_ready` for the combined conditions. Recognition-derived work also rechecks its saved acquisition receipt and requested range. Inspect `errors`, `blockers`, `warnings`, `unprocessed_ids`, and recognition coverage to identify remaining work. An exit code of `0` means ready, `1` means invalid or incomplete, and `2` means the input could not be read or the command could not be completed.

Measurements include counts, per-cue characters, line lengths, reading speed, and overlapping times. Character counts are Unicode code points including spaces and punctuation, excluding line breaks; the reported rate is that count divided by the cue duration. Use these to review the affected content under the selected delivery requirements. Each overlap record identifies an earlier cue still active at the current cue's start; overlaps can represent simultaneous speech, so assess them in context. Source correspondence checks cannot establish preservation of meaning.

When the actual media duration is known, pass `--media-duration-ms <integer>` to `check` and `export` to check that boundary. The last source cue is not a media-duration measurement.

`export` writes a complete UTF-8 SRT or WebVTT file and returns its actual `saved_path` with check information. Choose the requested format, using the subtitle input format or SRT for media-only input when none was specified. Keep the destination separate from every input and the run data. An existing destination requires `--overwrite`, used only with replacement permission. `check --output` compares the published cue text, including its literal-text encoding, and times with the current work data; export again after revisions.
