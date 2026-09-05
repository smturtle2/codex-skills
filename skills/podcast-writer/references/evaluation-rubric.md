# Podcast Content Review

Evaluate the current candidate against the user's requirements and supplied source notes. Judge content only; the writer owns TTS formatting, labels, paths, and ingestion mechanics.

## Criteria

All eight criteria must pass. Be strict: merely acceptable or generic material is insufficient. Explain a concrete defect or missing evidence for every failure; uncertainty about a criterion means it fails.

1. **Source Fidelity:** Correct facts, causal relationships, and essential context. No misreading, exaggeration, invented facts, or unsupported speculation.
2. **Content Selection:** Weight material according to the user's goal. Fail misplaced emphasis, important omissions, or mechanical compression.
3. **Insight And Interpretation:** Explain meaning, stakes, or implications with source support. A plain summary or unsupported interpretation fails.
4. **Logical Coherence:** Claims, background, evidence, transitions, and conclusions connect. Fail unsupported conclusions or passages that read like shuffled notes.
5. **Non-Repetition:** Repetition must add meaning, emphasis, or progression. Rephrasing to stretch length fails.
6. **User Intent Fit:** The purpose, audience, angle, emphasis, and exclusions shape the content, beyond surface tone.
7. **Source Integration:** Synthesize supplied material into one narrative. Source-by-source narration or unnecessary source mentions fail unless attribution was requested.
8. **Overall Content Value:** A worthwhile finished episode with a clear through-line and message. A generic summary or unfinished draft fails.

## Response Contract

Start with `EVALUATION:`. For each criterion in the order above, write its assessment immediately before its own result. After all eight entries, give concrete required fixes and put the overall result last.

```text
EVALUATION:
- <criterion name>:
  Assessment: <evidence and reasoning>
  Criterion Result: PASS|FAIL
[repeat for each remaining criterion]

REQUIRED_FIXES:
- <specific content revision, or None when all criteria pass>

RESULT: PASS|FAIL
```

Replace the angle-bracket fields and repetition marker; do not include them literally. Overall `PASS` requires eight `PASS` results; any failed criterion means overall `FAIL`.

A result before its own assessment, missing criteria, or an overall result inconsistent with the criteria is a format error. The writer must obtain a valid review without treating format errors as content findings.
