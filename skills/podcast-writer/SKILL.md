---
name: podcast-writer
description: Create one-person podcast scripts from user-provided sources such as PDFs, text files, websites, and YouTube links. Use when Codex needs to collect and preprocess source material, fetch YouTube transcripts with the bundled Python helper, fall back to GPU-only local Whisper transcription when YouTube captions are unavailable, write a clean TTS-ready plain-text monologue script, save it as .txt, and run strict subagent content-quality evaluation until every rubric item passes.
---

# Podcast Writer

Create a one-person podcast script from supplied source material, then save only the final script body as a plain `.txt` file.

## Hard Rules

- Produce a one-person monologue. Do not use speaker labels such as `화자1:`, `Host:`, `Narrator:`, or dialogue/interview formatting.
- Save the final approved `.txt` under the current project root as `./scripts/<descriptive-name>.txt`. Do not save the podcast output inside `skills/podcast-writer/scripts/`.
- Save the final `.txt` with script body only. Do not include headings, metadata, evaluation notes, source notes, or "here is the script" wrappers in the saved script.
- After the evaluator returns all-pass, delete temporary working files created by this skill, including downloaded audio, extracted transcripts, scratch source notes, draft scripts, and evaluation handoff files. Do not delete user-provided original source files or the final approved `./scripts/*.txt` output.
- Follow the user's requested topic, angle, audience, length, tone, emphasis, and exclusions.
- Ground the script in the provided sources. Do not invent source facts or present speculation as fact.
- Blend all provided sources into one unified podcast script. Do not mention source boundaries in the final script, such as "in the PDF", "the website says", "the video explains", "source one", or separate source-by-source summaries, unless the user explicitly requests source attribution.
- Remove preprocessing noise before writing the podcast script: timestamps, repeated captions, navigation text, ads, transcript artifacts, broken subtitle fragments, boilerplate, and duplicate passages.
- Treat TTS-readability rules as writer obligations, not evaluator duties. Keep the script clean for speech output, but do not ask the evaluator to judge TTS or formatting.
- Before completion, send the script and source notes to a newly created independent strict subagent for content-quality evaluation using `references/evaluation-rubric.md`.
- Create a fresh independent evaluator subagent for every evaluation attempt, including every re-evaluation after revisions. Do not reuse the same evaluator thread.
- Revise and re-evaluate with a fresh independent evaluator until every rubric item is `PASS`. Do not report the task complete while the evaluator returns any `FAIL`.
- If subagent tools are unavailable or repeated evaluation cannot progress because of missing source access, stop and report the blocker instead of silently skipping evaluation.

## Source Handling

- Local text or Markdown: read the file, separate user-authored content from metadata, and keep relevant structure.
- PDF: extract text with an appropriate PDF workflow. If extraction quality is uncertain, inspect rendered pages or use OCR only when needed.
- Website URL: fetch the current page, extract main article/body content, and remove navigation, footer, comments, ads, related links, and cookie text.
- YouTube URL: first use the bundled transcript helper:

  ```bash
  uv run skills/podcast-writer/scripts/fetch_youtube_transcript.py '<youtube-url-or-video-id>' --format text
  ```

  The helper accepts normal watch URLs, `youtu.be`, Shorts, embed, and live URL forms. Quote full URLs in shells such as zsh so `?` is not treated as a glob. It preserves transcript segment text, including music cues or lyrics; content filtering happens later during source preprocessing. If `uv` is unavailable, run the script with Python only when `youtube-transcript-api` is already installed.
- YouTube audio fallback: if the transcript helper fails because captions are unavailable or unusable, use the GPU-only Whisper fallback helper:

  ```bash
  uv run skills/podcast-writer/scripts/transcribe_youtube_gpu.py '<youtube-url-or-video-id>' --format text
  ```

  This fallback downloads the YouTube audio with `yt-dlp` and transcribes it with `faster-whisper` on CUDA only. The default model is `turbo`, the faster-whisper alias for Whisper large-v3-turbo. Do not use CPU fallback. If no CUDA GPU is available, stop and report the blocker.
- Multiple sources: process each source separately only in private working notes, then merge the useful material into one coherent script. Do not structure the final script as source-by-source explanation or attribution unless the user explicitly requests that format.

## Workflow

1. Identify source inputs, requested output path, language, audience, topic angle, target length, and any explicit exclusions.
2. Collect source text. Use `fetch_youtube_transcript.py` for YouTube transcripts. If captions are unavailable, use `transcribe_youtube_gpu.py`; it must run through `uv run` and must fail instead of using CPU when CUDA is unavailable. Preserve a working source-notes file or scratch summary outside the final script.
3. Preprocess sources into concise notes:
   - core claims and evidence
   - necessary background
   - important examples or quotes to paraphrase
   - source conflicts or uncertainty
   - material to exclude as noise
4. Choose a central episode message. The script should not be a flat summary; it should have a clear content point.
5. Draft the one-person podcast script as a polished monologue that integrates all selected source material into one narrative. Do not say or imply that the script is walking through separate source files.
6. Save working drafts outside the final output path while iterating. After strict evaluation passes, save the final approved script body to `./scripts/<descriptive-name>.txt` under the current project root.
7. Read `references/evaluation-rubric.md`, then create a new independent strict evaluator subagent. Provide file paths, not pasted full script text:
   - path to the candidate script file
   - path to concise source notes or source extracts needed to verify content
   - the user's original instructions
   - the fixed output contract from the rubric
8. If any rubric item is `FAIL`, revise the script according to `REQUIRED_FIXES`, then create another fresh independent evaluator subagent for the revised script. Never re-use the previous evaluator for re-evaluation.
9. Finish only after the evaluator returns `RESULT: PASS` with every item marked `PASS`.
10. Delete temporary files created during source collection, preprocessing, audio download, draft writing, and evaluator handoff. Keep only the final approved `./scripts/*.txt` output and any user-provided original source files.

## Evaluation Delegation Prompt Contract

Ask the evaluator to assess only script content quality. Do not ask it to evaluate TTS formatting, speaker labels, file naming, or source ingestion mechanics.

Use a new independent evaluator subagent for each evaluation attempt. The evaluator should receive only paths to the revised candidate script and source notes, user instructions, and this rubric contract. Do not paste the full script content into the prompt. Do not include previous evaluator conclusions unless the user explicitly asks to preserve an audit trail.

Before sending the prompt, replace every `{{...}}` field with the actual task content. `{{SOURCE_NOTES_PATH}}` and `{{CANDIDATE_SCRIPT_PATH}}` must be readable local file paths. Do not leave template variables in the prompt sent to the evaluator.

Use this prompt template for every evaluation and re-evaluation:

```text
You are an independent strict podcast script content-quality evaluator.

Evaluate only the content quality of the candidate one-person podcast script.
Do not evaluate TTS readiness, speaker labels, plain-text formatting, file paths, transcript-fetch mechanics, or whether the writer followed operational workflow rules.

Be very strict. PASS is allowed only when the script is strong as podcast content, not merely acceptable.
When uncertain, choose FAIL for the affected criterion.
The final RESULT may be PASS only if every criterion is PASS.

USER INSTRUCTIONS:
{{USER_INSTRUCTIONS}}

SOURCE NOTES:
Read the source notes from this local path:
{{SOURCE_NOTES_PATH}}

CANDIDATE SCRIPT:
Read the candidate script from this local path:
{{CANDIDATE_SCRIPT_PATH}}

RUBRIC:
- Source Fidelity: accurate source understanding; no distortion, unsupported facts, or essential omissions.
- Content Selection: strong selection and weighting of important material for the user's goal.
- Insight And Interpretation: meaningful explanation of significance, context, stakes, or implications beyond plain summary.
- Logical Coherence: claims, background, evidence, transitions, and conclusions connect cleanly.
- Non-Repetition: no repeated claim, setup, explanation, example, transition, or conclusion unless it adds new substance.
- User Intent Fit: user purpose, audience, angle, emphasis, and exclusions shape the content choices.
- Source Integration: multiple sources are synthesized into one coherent script without source-by-source narration or unnecessary source mentions.
- Overall Content Value: worth listening to as a finished episode with a clear through-line and message.

Return exactly this structure:

EVALUATION:
- Source Fidelity:
  Assessment: ...
  Criterion Result: PASS|FAIL
- Content Selection:
  Assessment: ...
  Criterion Result: PASS|FAIL
- Insight And Interpretation:
  Assessment: ...
  Criterion Result: PASS|FAIL
- Logical Coherence:
  Assessment: ...
  Criterion Result: PASS|FAIL
- Non-Repetition:
  Assessment: ...
  Criterion Result: PASS|FAIL
- User Intent Fit:
  Assessment: ...
  Criterion Result: PASS|FAIL
- Source Integration:
  Assessment: ...
  Criterion Result: PASS|FAIL
- Overall Content Value:
  Assessment: ...
  Criterion Result: PASS|FAIL

REQUIRED_FIXES:
- Use `None` only when every item is PASS. Otherwise list concrete content revisions required to reach PASS.

RESULT: PASS|FAIL
```

All eight evaluation items must be `PASS` for `RESULT: PASS`. When the evaluator is uncertain, it must choose `FAIL`.
For every criterion, write `Assessment` before `Criterion Result`. Do not output a criterion-level `PASS` or `FAIL` before the assessment text.

## Response

When finished, report:

- saved script path
- sources used and any sources that could not be accessed
- that strict subagent evaluation passed all rubric items
- that temporary working files created by the skill were deleted
- any important source uncertainty preserved in the script
