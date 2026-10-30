# subtitle-creator

Create natural subtitles from video, audio, and available subtitle tracks, with readable segmentation and timing grounded in the available speech evidence.

[All skills](../../README.md#skills) · [한국어](subtitle-creator.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/subtitle-creator from https://github.com/smturtle2/codex-skills.
```

## Requirements

The host must support subagents with an explicit model and reasoning effort. Semantic workers default to the latest Terra available through the host with reasoning effort `max`, selected when work is dispatched. The subtitle helper uses uv and Python 3.11 or later.

Supply media, an available SRT or WebVTT track, or both, and the desired subtitle language. The language defaults to your language; requesting the source language produces same-language subtitles. Media without an existing track needs a usable local speech recognition runtime and existing model data to obtain its initial timed speech evidence. The agent uses operational GPU execution when supported and CPU otherwise, and reports an unavailable required capability.

## Example

```text
Use $subtitle-creator to create subtitles from {input_files}.
Language: {target_language}
Output: {output_path}
```

Fill `input_files` with the available media and subtitle paths. Omit optional language or output preferences when their defaults are appropriate.

## Subtitle production

Existing subtitles already provide timed text. When they are absent, the agent recognizes the requested media range first. Both inputs then follow the same work: contextual interpretation and translation, removal of non-dialogue annotations, natural subtitle segmentation, timing refinement, review, and publication.

The main agent acquires speech evidence, maintains shared terminology and tone, allocates coherent passages with neighboring context, and accepts the final result. Terra workers compose the subtitles and identify uncertain passages. Additional recognition targets those unclear intervals while useful completed work is retained.

Source captions and recognition results are observations interpreted with the surrounding dialogue and available audio. Music, sound-effect, and situation annotations are removed while actual dialogue remains. Source cue boundaries can be combined or split to fit the target language and speech rhythm.

Full recognition records the requested, completed, and pending ranges and the associated result files, so interrupted acquisition can continue from unfinished work. Processing every range does not establish that every spoken word was recognized. Empty recognition is assessed against the available speech evidence before accepting an empty subtitle track.

Timing can use available word timestamps, alignment, and review of matching audio or video. With a subtitle track alone, the agent works from its timing and reports the extent of synchronization review. Important unresolved meaning and evidence limitations are reported separately from delivered subtitle text.

## Working files

Working files default to the project-root-relative `.codex-skills/subtitle-creator/{run_id}/`. Use a unique directory for new work; a requested location takes precedence. Resume existing work at its original path, including runs created under the earlier skill name. Keep `/.codex-skills/` ignored in Git unless its contents are intentionally versioned.

The helper initializes shared source and work data from the available timed evidence. Read the saved source, work, recognition records, and decisions when continuing; retain completed passages and useful recovery data. Clean up only expendable intermediates created by the current run.

[Work data and helper commands](../../skills/subtitle-creator/references/work-data.md) · [Speech evidence](../../skills/subtitle-creator/references/audio-evidence.md)

## Output

A new SRT or WebVTT file with the authored subtitle text, line breaks, and times, plus resumable work data and a report of the actual saved path, processing coverage, recognition used, timing evidence reviewed, and remaining limitations. Save the final track separately from every input. When no output format is requested, use SRT for media-only input or the existing subtitle track's format.

Source formatting and positioning are retained as working reference; the helper publishes plain display text. Its structural, coverage, timing, and publication checks support the agent's content review. Translation quality and speech synchronization require evidence from the actual content and media.

[Read the agent instructions](../../skills/subtitle-creator/SKILL.md)
