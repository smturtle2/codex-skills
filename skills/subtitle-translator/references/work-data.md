# Subtitle Work Data

Read before preparing source data, briefing a translation worker, or editing a run. The helper uses UTF-8 JSON and integer milliseconds. Source times initially follow the subtitle clock; establish its mapping to matching media before authoring media-based output or evidence ranges.

## Source and Work Files

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" inspect \
  --input <source.srt-or-vtt> --workdir <run-dir>
```

`inspect` requires an empty new work directory and creates `source.json` and `work.json`. Omitting `--workdir` prints the parsed source snapshot without creating a workspace. Use `--encoding <name>` when the source needs a different encoding; the default is `utf-8-sig`.

`source.json` has `version: 1`, source `path`, `format`, and `encoding` under `source`, a `cues` list, and a `metadata` list. Each cue retains its parsed `start_ms`, `end_ms`, and `text`, with an optional original `identifier` or timing `settings`. IDs `s1`, `s2`, and onward follow source file order independently of the original cue identifiers.

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

Write groups and their output cues in delivery order, with nondecreasing start times. Output and evidence times use the matching media timeline when media is supplied, otherwise the source subtitle timeline. Each output cue has nonempty display text, no blank lines within the cue, and an end time greater than its nonnegative start time. An entirely annotation-only source can yield an empty track when every source ID is explicitly omitted.

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

Brief a worker with the owned source IDs and their original text/times, adjacent context, target language, shared terminology and tone decisions, available speech evidence, and relevant delivery specifications. Have it return `groups`, `omitted`, `pending`, and `notes` for its owned range. The main agent merges those results into `work.json`, resolves passage joins, and updates shared decisions.

Preserve completed results when obtaining new evidence or repairing a passage. Resume by reading `source.json`, `work.json`, working notes, and the current check result in the same run directory. The helper's `inspect` command initializes a new run; existing work is continued by editing its saved data.

## Check and Publish

```bash
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check --workdir <run-dir>
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" export \
  --workdir <run-dir> --output <translated.srt-or-vtt>
uv run --script "$SKILL_DIR/scripts/subtitle_io.py" check \
  --workdir <run-dir> --output <translated.srt-or-vtt>
```

`check` reports `valid` for structurally usable data, `complete` for source coverage with a target language and no pending decisions, and `export_ready` for the combined conditions. Inspect `errors`, `blockers`, `warnings`, and `unprocessed_ids` to identify remaining work. An exit code of `0` means ready, `1` means invalid or incomplete, and `2` means the input could not be read or the command could not be completed.

Measurements include counts, per-cue characters, line lengths, reading speed, and overlapping times. Character counts are Unicode code points including spaces and punctuation, excluding line breaks; the reported rate is that count divided by the cue duration. Use these to review the affected content under the selected delivery requirements. Each overlap record identifies an earlier cue still active at the current cue's start; overlaps can represent simultaneous speech, so assess them in context. Source correspondence checks cannot establish preservation of meaning.

When the actual media duration is known, pass `--media-duration-ms <integer>` to `check` and `export` to check that boundary. The last source cue is not a media-duration measurement.

`export` writes a complete UTF-8 SRT or WebVTT file and returns its actual `saved_path` with check information. Choose the requested format, defaulting to the source format, and a destination separate from the source and run data. An existing destination requires `--overwrite`, used only with replacement permission. `check --output` compares the published cue text, including its literal-text encoding, and times with the current work data; export again after revisions.
