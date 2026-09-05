---
name: podcast-writer
description: Turn supplied documents, websites, or YouTube sources into a one-person podcast script saved as plain text, with independent content review before completion.
---

# Podcast Writer

Create a source-grounded monologue in the user's requested language, angle, audience, length, and tone.

## Workflow

1. Identify the supplied sources and requested output. Default the final file to `scripts/<descriptive-name>.txt` under the session project, never the skill's own scripts directory.
2. Collect source text and keep concise evidence notes outside the final file. For YouTube input or extraction problems, read [references/source-ingestion.md](references/source-ingestion.md).
3. Remove timestamps, navigation, ads, duplicate captions, boilerplate, and broken transcript fragments before writing.
4. Choose a central episode message and synthesize the relevant facts, examples, context, and uncertainty into one narrative.
5. Write a candidate script outside the final output path. Check its speech formatting directly.
6. Read [references/evaluation-rubric.md](references/evaluation-rubric.md) and give a fresh independent evaluator the candidate path, source-note paths, user requirements, and rubric.
7. Revise concrete content failures, then use a new independent evaluator for the revised candidate. Finish only when every rubric item passes.
8. Save the approved script body to the final file, then delete this run's temporary collection, transcription, draft, and evaluation files.

Keep track of temporary files created by this run. Preserve user-provided originals and the final output; do not clean up a directory merely because it contains working material.

## Script Contract

- Use one speaker without labels, interviews, or dialogue formatting.
- Save only the TTS-ready script body: no headings, metadata, evaluation results, source notes, or delivery wrappers.
- Ground factual claims in the sources. Preserve material uncertainty; do not invent facts or present speculation as fact.
- Integrate sources around the episode's message. Avoid separate source summaries and phrases such as “the PDF says” unless the user requests attribution.
- Prefer spoken phrasing and coherent transitions. Treat TTS formatting as the writer's responsibility, not an evaluator criterion.

## Review and Recovery

Each evaluation attempt uses a new thread with fresh context limited to the current candidate and evidence paths, user requirements, and rubric. Disable inherited conversation when supported. Do not paste entire source material or previous verdicts into the handoff. Replace any handoff placeholders with real paths.

The evaluator judges content only. Its required response format and eight criteria are defined solely in the rubric.

- On content failure, fix the identified issue before requesting another review.
- On malformed evaluation output, request a fresh evaluation of the same candidate; do not treat formatting failure as evidence that the script content is wrong.
- If required sources or subagent tools are unavailable, or repeated attempts cannot advance for a specific unresolved reason, report that blocker and retain the working candidate for recovery. Do not claim approval or silently skip review.

## Handoff

Report the final script link, sources used or inaccessible, all-item evaluation result, temporary-file cleanup, and any material uncertainty retained in the script.
