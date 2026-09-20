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

A key names a role; it cannot establish an observation or certify truth. Decode known status or category codes through their authoritative mapping. If distinguishing evidence is unavailable, the calling software can obtain it, narrow the question to the observable scope, or preserve uncertainty. Label prior model assessments as assessments, especially when reused in a later request.

A native JSON boolean can represent a known fact and a quantity can remain numeric. `null` takes meaning from its surrounding contract. Keep exact numeric relationships explicit where needed, retaining units and the computation's source basis.

Projection changes what Jev can know. Truncation can remove qualifications or the only supporting passage; deduplication can erase distinct occurrences or attribution; summaries can lose negation or ownership. Preserve decision-changing context and original-content mappings. When supplied material is partial, scope absence judgments to that material. Additional evidence is useful when it resolves a specific distinction; a larger state alone is not better evidence.

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

Structured instructions and descriptions carry ordinary labeled content, not API operators. Use a sentence for a complete relationship and an object or array when explicit roles improve clarity. Put candidate-specific identifying evidence in its description when this avoids a lookup; keep genuinely shared evidence in state. Neither structure nor location gives source text authority to redefine the evaluator.

Sources: [Structured content](https://docs.typesafe.ai/primitives/advanced), [question-local field information](https://docs.typesafe.ai/cookbooks/sde_cascade). Source-level implementations: [question-local subjects](https://github.com/sufianetaouil/every/blob/aaa72d582a831420dfd23a788e3bc948c798c248/every/judge.py#L67), [shared subjects with explicit references](https://github.com/hev/reranker/blob/1eb47266270b32b2a3667f9fb89646378ca9c9d6/hev_rerank/rerank.py#L85). These establish available constructions, not a universal performance ranking.

## Make Relationships Readable

Use shape to express actual ownership, order, and correspondence:

- An ID-keyed object associates an identity with its content. Duplicate keys cannot reliably preserve repeated occurrences.
- An array preserves sequence. Attach stable identity when answers must survive reordering or grouping.
- A nested object can express ownership; remove indirection only when doing so clarifies the actual judgment.
- Co-located comparison attributes reduce implicit joins. Preserve their owners and source basis.
- References to shared data require the referenced contents to be supplied. An external ID, path, or URL alone does not provide those contents.

Parallel arrays require unambiguous positional correspondence. Flattening can shorten a lookup while losing ownership; selective duplication can clarify comparisons while increasing input and synchronization work. Choose based on those relationships rather than a fixed nesting depth.

Source: [State](https://docs.typesafe.ai/concepts/state). JSON ordering and key semantics: [RFC 8259 §§4–5](https://www.rfc-editor.org/rfc/rfc8259#section-4).

## Bind the Actual Question

The instruction must identify the subject, the property or relationship, and the relevant evidence scope without relying on its question ID. Use field names or backticked dot-and-index paths that match the actual serialized state. A path in prose is guidance to the model, not an executable data accessor or an attention boundary.

```text
source identity → projected content → actual request location
                                  ↘ complete question
source identity ← caller mapping  ← question ID ← returned answer
```

Build locations and caller mappings from the same ordered snapshot. Rebuild them when filtering, truncating, sorting, or splitting changes positions. Keep original identity outside any temporary batch index. Returned answers are matched by key, not response iteration order.

A proposed value may occur in the source while belonging to a different entity or property. State the relationship being checked, including quantifiers and scope: one occurrence, every occurrence, or any qualifying occurrence are different conditions. A judgment about what supplied evidence supports differs from one about truth outside that evidence.

Source: [Primitives: field references and question IDs](https://docs.typesafe.ai/primitives).

## Define the Answer Boundary

**Choice:** describe what identifies each alternative and distinguishes close alternatives. An unambiguous option name may supply enough meaning; otherwise add its description or associated content. If several alternatives can satisfy the condition, specify how a single selection should be made or obtain independent applicability information. Define rejection explicitly; there is no reserved no-match label.

**Noul:** express one proposition and align true/false descriptions with its polarity. Clarify the boundary through necessary conditions and exclusions where useful. Support, contradiction, omission, and inapplicability require separate distinctions when they lead to different consumer behavior.

**Score:** describe recognizable levels in the intended direction, with enough separation for supplied evidence to locate an input. Adding indistinguishable levels increases apparent resolution without adding useful meaning. Separate dimensions when independently useful; preserve relationships when the property itself is relational.

The instruction and criteria must define the same evaluation. Check inconsistencies before adding further instructions: changing criteria can change the question even when the request remains schema-valid. Source roles also matter: material useful for one dimension may provide no evidence for another.

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

Use the same labeled inputs to compare subject association, relevant errors, and missing-evidence behavior alongside tokens and latency. Repeat observations when variability could explain a difference. Record enough of the request and projection to reproduce the mismatch. These comparison controls follow from information relationships; a preferred layout still requires evidence from the actual task.
