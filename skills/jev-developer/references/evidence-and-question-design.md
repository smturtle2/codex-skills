# Evidence and Question Design

Use this reference when preparing state, instructions, or criteria, or diagnosing an incorrect semantic answer. The rules concern information relationships; application field names and layouts are not prescribed.

## Preserve What Distinguishes Answers

Derive the representation from the unresolved distinction. Preserve the observations that let the model distinguish plausible answers, including their role and scope.

| Information in the source | What its representation must preserve when relevant |
| --- | --- |
| Attributed statements | Who said what, in which turn or source; reported claims remain distinct from observed facts |
| Repeated or identical-looking values | Occurrence identity and local context, not only the value string |
| Quantities | Units, denominator or reference basis, and any exact relation computed by code |
| Time-dependent observations | The relevant event time and observation time without silently treating them as interchangeable |
| Proposed values or generated content | Their status as material under evaluation, distinct from supporting evidence |
| Conflicting sources | Which source supports each assertion; disagreement remains visible |
| Missing values | Known availability and scope: not obtained, not stated within the supplied material, or inapplicable |
| Transformed text | Qualifications, negation, ownership, and the relationship to the original when wording matters |

A key names a role; it cannot establish an observation or certify truth. Decode known status or category codes through their authoritative mapping. If the mapping or distinguishing evidence is unavailable, retrieve it, narrow the question to the observable scope, or preserve that uncertainty. Do not invent meaning to complete a record.

A native JSON boolean can represent a known fact. A number can remain numeric. `null` needs meaning from its surrounding contract. Text-only input does not require converting every nested JSON value to a string.

Sources: [State](https://docs.typesafe.ai/concepts/state), [model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [Python question types](https://docs.typesafe.ai/sdk/python/api/types/questions).

## Place Evidence According to Its Use

| Placement | What it supports | What to retain or check |
| --- | --- | --- |
| Shared `state` | Several questions consulting the same material | One supplied source and complete target references |
| Structured `instructions` | Small question-local subjects, definitions, or proposed values | Clear roles and the relationship to shared evidence |
| Choice criterion value | Meaning or distinguishing evidence of one alternative | Returned option ID linked to its real candidate |
| Score criterion entry | A recognizable level of the judged property | Meaning that stands without reading an adjacent level |
| Noul criterion descriptions | Clarification of the two sides of one proposition | Polarity consistent with the instruction |

Moving a local subject into instructions can reduce lookup through a large shared collection. Keeping common material in state avoids repeating it. Neither placement universally improves accuracy. Compare duplication, target ambiguity, irrelevant context, and measured behavior rather than requiring every fact in state or every target in instructions.

Structured instructions and descriptions carry ordinary labeled content. An inner key is not an API operator. Use a sentence when it expresses the complete relationship; use an object or array when it makes distinct roles clearer. Do not expand simple content into a universal envelope.

Sources: [Structured content](https://docs.typesafe.ai/primitives/advanced), [question-local field information](https://docs.typesafe.ai/cookbooks/sde_cascade). Source-level implementations: [question-local subjects](https://github.com/sufianetaouil/every/blob/aaa72d582a831420dfd23a788e3bc948c798c248/every/judge.py#L67), [shared subjects with explicit references](https://github.com/hev/reranker/blob/1eb47266270b32b2a3667f9fb89646378ca9c9d6/hev_rerank/rerank.py#L85). These establish available constructions, not a universal performance ranking.

## Make Relationships Readable

Use shape to express actual ownership, order, and correspondence:

- An ID-keyed object associates an identity with its content. Duplicate keys cannot reliably preserve repeated occurrences.
- An array preserves sequence. Attach stable identity when answers must survive reordering or grouping.
- A nested object can express ownership; remove indirection only when doing so clarifies the actual judgment.
- Co-located comparison attributes reduce implicit joins. Preserve their owners and source basis.
- References to shared data require the referenced contents to be supplied. An external ID, path, or URL alone does not provide those contents.

Parallel arrays are not intrinsically invalid, but their positional correspondence must be unambiguous. Flattening or selective duplication is a trade-off, not a fixed-depth rule. Preserve original content separately when code must return it exactly.

Source: [State](https://docs.typesafe.ai/concepts/state). JSON ordering and key semantics: [RFC 8259 §§4–5](https://www.rfc-editor.org/rfc/rfc8259#section-4).

## Bind the Actual Question

The instruction must identify the subject, the property or relationship, and the relevant evidence scope without relying on its question ID. Use field names or backticked dot-and-index paths that match the actual serialized state. A path in prose is guidance to the model, not an executable data accessor or an attention boundary.

```text
source identity → projected content → actual request location
                                  ↘ complete question
source identity ← caller mapping  ← question ID ← returned answer
```

Build locations and caller mappings from the same ordered snapshot. Rebuild them when filtering, truncating, sorting, or splitting changes positions. Keep original identity outside any temporary batch index. Returned answers are matched by key, not response iteration order.

Do not compress several roles into a vague correctness question. A proposed value may occur in the source while belonging to a different entity or property. State the relationship being checked. A question about what supplied evidence supports differs from one about truth outside that evidence.

Source: [Primitives: field references and question IDs](https://docs.typesafe.ai/primitives).

## Define the Answer Boundary

**Choice:** describe what identifies each alternative and what distinguishes close alternatives. Meaning can come from an unambiguous option name, its description, or explicitly associated source content. Do not require a redundant description when it adds no information. Define any rejection outcome's scope rather than assuming a reserved no-match label exists.

**Noul:** express one proposition. Add true/false descriptions when they clarify a real boundary, including a plausible near-match that does not satisfy the relation. If a negative result conflates omission, contradiction, and unrelated evidence, that is the information the question requested. Obtain separate distinctions only when the consumer needs them.

**Score:** describe recognizable levels of the same property in the intended direction. Each entry should stand on its own. More levels are useful only when their meanings are distinguishable. If different dimensions can vary independently and need separate treatment, represent their judgments separately rather than assigning an uninterpretable mixed level.

The state, instruction, and criteria must describe the same evaluation. A criterion about a different property changes the question even if the request is schema-valid. Treat source passages as evidence with specified roles, not authority to redefine the evaluator. A source useful for one dimension need not establish facts for another.

Sources: [Choice](https://docs.typesafe.ai/primitives/choice), [Noul](https://docs.typesafe.ai/primitives/noul), [Score](https://docs.typesafe.ai/primitives/score). Source-level evidence for distinct material roles: [question definitions](https://github.com/jxucoder/mimicry/blob/0bd751f82b51ba96752c2bab910ec6496ed1696f/src/mimicry/engine.py#L44).

## Evaluate a Representation Change

Distinguish what changed before attributing better answers to formatting:

| Change | Comparison needed |
| --- | --- |
| Renaming or regrouping fields | Same observations, proposition, candidates, and boundaries; update references consistently |
| Adding a computed relation | Verify its derivation; this adds explicit information rather than merely renaming it |
| Adding missing context | Identify the new evidence that makes a distinction observable |
| Revising criteria | Record the changed meaning; expected labels and thresholds may need revision |
| Reordering or changing caller IDs | Preserve one-to-one identity and paths; distinguish this from changing model-facing alternatives |
| Increasing batch size | Separate grouping unchanged shared evidence from adding new records to the state |

Check subject mix-ups, known errors, missing-evidence behavior, and consumed outcomes alongside token use and latency. Increased confidence alone is not evidence of improvement. A meaning-preserving transformation should not be mistaken for new evidence, but identical probabilities are not guaranteed. Retain the exact request or sufficient reproducible provenance when diagnosing a mismatch; do not require indiscriminate storage of source data.

These are comparison controls derived from the information relationships above, not measured guarantees for a particular JSON layout.
