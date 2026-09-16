# podcast-writer

Turn documents, websites, and YouTube sources into a source-grounded monologue, revised through independent content review.

[All skills](../../README.md#skills) · [한국어](podcast-writer.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/podcast-writer from https://github.com/smturtle2/codex-skills.
```

Requires subagent tools for content review. YouTube audio transcription fallback requires a compatible GPU; captions are used first.

## Example

```text
Use $podcast-writer to turn these sources into a 10-minute solo episode for beginners. Save the script as plain text.
```

## Working files

Keep candidate scripts, source notes, and review state in the project-root-relative `.codex-skills/podcast-writer/<run-id>/` workspace. An explicit work location wins; resume older existing locations in place. Retain resumable data and clean up only expendable intermediates created by this run. Save the final `.txt` script to the requested destination.

## Output

A `.txt` file containing only the spoken script, ready for a separate TTS or recording step.

[Read the agent instructions](../../skills/podcast-writer/SKILL.md)
