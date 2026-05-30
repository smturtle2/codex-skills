# Podcast Writer Evaluation Rubric

Use this rubric for strict subagent evaluation of a candidate one-person podcast script.

Evaluate only content quality. Do not evaluate TTS readiness, speaker labels, plain-text formatting, file paths, transcript-fetch mechanics, or whether the main agent followed operational workflow rules.

## Decision Rule

- Every item must be marked `PASS` or `FAIL`.
- `RESULT: PASS` is allowed only when every item is `PASS`.
- If any item is `FAIL`, final result must be `RESULT: FAIL`.
- When uncertain, choose `FAIL`.
- Be very strict. Do not pass a script that is merely acceptable, generic, or safely written but weak as podcast content.
- The first output line must be exactly `EVALUATION:`.
- If `PASS`, `FAIL`, `RESULT: PASS`, or `RESULT: FAIL` appears before all assessment text is written, the evaluation is invalid and must be treated as `FAIL`.

## Criteria

### Source Fidelity

Pass only if the script accurately understands the provided source material.

Fail if it misreads the source, changes causal relationships, drops essential context, exaggerates claims, invents source facts, or presents unsupported speculation as fact.

### Content Selection

Pass only if the script chooses the right material for the user's requested podcast goal.

Fail if it overweights minor details, misses important points, treats all source material as equally important, or feels mechanically compressed from the source.

### Insight And Interpretation

Pass only if the script explains meaning, stakes, implications, or context beyond restating source sentences.

Fail if it is a plain summary with no interpretive value, or if its interpretation is unsupported by the source.

### Logical Coherence

Pass only if claims, evidence, background, transitions, and conclusions connect cleanly.

Fail if the script jumps between ideas, buries the main point, makes conclusions that do not follow, or reads like reordered notes.

### Non-Repetition

Pass only if repeated material adds new meaning, emphasis, or progression.

Fail if it repeats the same claim, explanation, setup, example, transition, or conclusion without adding new substance. Also fail if it uses rephrasing to stretch length.

### User Intent Fit

Pass only if the user's requested purpose, audience, angle, emphasis, and exclusions shape the actual content choices.

Fail if the script only matches surface tone while ignoring the requested direction, audience level, or priority.

### Source Integration

Pass only if all provided sources are synthesized into one coherent script.

Fail if the script talks about the sources as separate objects, walks through "source one/source two", says things like "the PDF says" or "the video explains", or otherwise feels like separate source summaries stitched together, unless the user explicitly requested source attribution.

### Overall Content Value

Pass only if the script feels worth listening to as a finished podcast episode.

Fail if the listener would get little more than a generic summary, if the final message is unclear, if the script lacks a meaningful through-line, or if it feels like a draft rather than finished content.

## Required Output

Return assessment text before each criterion result, and return final pass/fail last:

```text
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
- Use `None` only when every item is PASS.

RESULT: PASS|FAIL
```

Do not output a criterion-level `PASS` or `FAIL` before its assessment text.
Do not output `PASS`, `FAIL`, `RESULT: PASS`, or `RESULT: FAIL` before the required `EVALUATION` section is complete.
