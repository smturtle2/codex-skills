# subtitle-translator

Translate English subtitles into natural dialogue with readable segmentation and timing informed by the available speech evidence.

[All skills](../../README.md#skills) · [한국어](subtitle-translator.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/subtitle-translator from https://github.com/smturtle2/codex-skills.
```

## Requirements

The default translation workflow requires a host that can dispatch subagents with an explicit model and reasoning effort. Workers use the latest Terra available to that host with reasoning effort `max`, selected when work is dispatched. The agent reports an unavailable requested capability. The subtitle helper uses uv and Python 3.11 or later.

Supply English SRT or WebVTT subtitles and the target language; the target defaults to your language. Matching video or audio provides evidence for speech timing and unclear dialogue. For ambiguous passages in automatically generated captions, the skill can use an existing, runnable local speech recognition model on the relevant audio intervals, using its supported GPU execution when available and CPU otherwise.

## Example

```text
Use $subtitle-translator to translate episode.en.srt into Korean and save episode.ko.srt.
The English captions were automatically generated; use episode.mp4 to clarify uncertain dialogue and improve timing.
```

The main agent maintains terminology and tone and distributes coherent passages with surrounding context to translation workers. Workers interpret the dialogue, choose natural wording and subtitle breaks, and identify passages needing more evidence. The main agent gathers that evidence and reviews passage boundaries and shared decisions.

Source captions and additional recognition results are reference material interpreted together with the surrounding dialogue. Non-dialogue music, sound-effect, and situation annotations are removed while spoken content is retained. Original cue boundaries can be combined or split to fit the translated dialogue and its reading rhythm.

Speech recognition helps identify words; timing may also use available word timestamps, alignment, or review of the relevant audio. With subtitles alone, the skill works from the source timing and reports the extent of synchronization review. Important uncertainty that remains is reported separately from the delivered subtitle text.

## Working files

Working files default to `.codex-skills/subtitle-translator/<run-id>/`, relative to the project root. A new translation uses a unique directory; an explicit work location takes precedence, and continuation reuses the original path, including older locations. Keep `/.codex-skills/` ignored in Git unless its contents are intentionally versioned.

For a new run, the helper's `inspect` command creates `source.json` and `work.json` in an empty workspace. For continuation, read those existing files and the saved decisions, update `work.json`, and use `check` to inspect remaining work. Keep source references, completed translations, and useful recovery data; clean up only expendable intermediates from the current run. Write the final subtitle to the requested destination, separately from the source.

[Work data and helper commands](../../skills/subtitle-translator/references/work-data.md) · [Speech evidence](../../skills/subtitle-translator/references/audio-evidence.md)

## Output

A new SRT or WebVTT file containing the translated display text, plus resumable working files and a report of the actual output path, speech recognition used, timing evidence reviewed, and remaining uncertainty. Source formatting and positioning information are retained as working reference; the helper exports plain subtitle text with the authored line breaks and times.

The helper checks data structure, source coverage, timing values, and correspondence between saved output and current work. Translation quality and speech synchronization are assessed from the content and available media evidence.

[Read the agent instructions](../../skills/subtitle-translator/SKILL.md)
