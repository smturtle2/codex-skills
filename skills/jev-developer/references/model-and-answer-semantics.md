# Model and Answer Semantics

Use this reference to choose a judgment, interpret its answer, or distinguish model behavior from consumer policy. Model behavior depends on the selected release; verify applicable limitations in its documentation.

## What Is Evaluated

```text
state + one question's instructions + its answer definitions
    → typed answer associated with the caller's question ID
```

The request can carry several questions over the same state. A question does not receive another question's answer as hidden context. Jev suits focused semantic judgments with the needed information directly available. Code constructs intermediate subjects or resolves exact relationships when a judgment would otherwise require several hidden reasoning steps. Paths guide interpretation of supplied content; they do not fetch records, execute JSONPath, or restrict access to other state.

| Request location | Semantic role |
| --- | --- |
| `state` | Supplied observations and context, as text or structured content |
| `questions[question_id]` | Caller association; the model does not see `question_id` |
| `instructions` | The subject, condition or relationship, and evidence scope to evaluate |
| Choice `criteria[option_id]` | Both the option ID and its description are model-facing |
| Score `criteria[i]` | Description of level `i`; array position supplies its index |
| Noul `criteria.true` / `criteria.false` | Optional clarification of the proposition's truth boundary |

Names inside structured content are ordinary model-facing language. Their meanings come from the content; naming a field as verified does not verify it. Shape compatibility belongs to the actual SDK and server contract; see [integration](integration.md).

Sources: [Primitives](https://docs.typesafe.ai/primitives), [Choice](https://docs.typesafe.ai/primitives/choice), [structured content](https://docs.typesafe.ai/primitives/advanced).

## Choice: Relative Alternatives

```text
choice ∈ supplied option IDs
probabilities: option ID → probability in [0, 1]
Σ probabilities[option ID] = 1
choice = an option with maximal probability
```

Use Choice when the consumer needs one identity from supplied alternatives. Its distribution belongs to that answer space. Adding, removing, or changing alternatives changes the comparison; probabilities from separate candidate sets are not a common absolute-quality scale. Overlapping or near-duplicate alternatives can divide probability among acceptable answers. Clarify the selection rule or consolidate equivalent candidates when their identity is immaterial; preserve distinct occurrences when identity matters. Independently applicable labels call for separate applicability judgments.

An explicit rejection option participates in this same distribution. Its description determines the scope of rejection. It may mean no supplied candidate fits; it does not automatically establish absence from a larger source. Ambiguity among candidates and a definite no-match are also different information.

Candidate identity, source presence, and candidate suitability have different meanings even when code assembles the same optional return type. See [selection and absence](composition-and-execution.md#selection-presence-and-suitability).

Source: [Choice](https://docs.typesafe.ai/primitives/choice).

## Noul: Truth of a Proposition

```text
noul ∈ [0, 1]
noul = estimated probability that the defined proposition is true
```

There is no separate `confidence`. A midpoint probability expresses unresolved truth, not a medium amount of an attribute.

Use Noul when truth of a defined condition is the useful signal, including independent membership or suitability. The proposition's scope determines the meaning of a negative answer. Lack of support in supplied material does not establish falsity outside it. Missing evidence may support a clear negative about documented support while leaving a broader truth question unresolved; absence is not automatically encoded as a midpoint.

Keep `true` aligned with the instruction and `false` with its negation. Either positive or defect-oriented propositions are possible; consumer thresholds must use the actual polarity. Independently phrased questions need not produce complementary probabilities. For an exact complement of the same proposition, derive `1 - p` from its single answer.

Source: [Noul](https://docs.typesafe.ai/primitives/noul).

## Score: Distribution over Described Levels

```text
L = number of ordered descriptions
i ∈ {0, …, L - 1}
score = Σ i × probabilities[i]
legend[i] = description associated with level i
```

Use Score when the consumer needs degree on a describable ordered scale. Each level should stand on its own and levels should progress along the same property. Combining independently varying properties can leave no meaningful position for an input; use separate judgments when the consumer needs those dimensions.

The expected index can fall between levels. It is not an exact quantity, a percentage of affected subjects, or a probability that the answer is correct. Equal expectations can hide different concentrations or mass at opposite ends of the scale. Use the distribution when those distinctions affect behavior.

`score / (L - 1)` rescales the index range; it does not calibrate the result as a probability or establish equal semantic spacing. Numeric labels inside descriptions do not change the index weights. When levels have externally defined values or utilities `v[i]`, code may compute `Σ v[i] × probabilities[i]`, provided those values meaningfully represent the levels. Exact numeric extraction instead requires source candidates or deterministic parsing; the [composition reference](composition-and-execution.md#values-and-structure) explains that boundary.

HTTP maps use stringified indices; Python SDK maps use integer indices. Retain the legend rather than inferring level meaning from an unassociated number.

Source: [Score](https://docs.typesafe.ai/primitives/score).

## Confidence and Consistency

Choice and Score `confidence ∈ [0, 1]` summarizes the returned distribution's concentration. It is not an additional probability of correctness, suitability, permission, or successful execution. The inspected confidence documentation does not publish a formula to reimplement; use the returned field or an explicitly defined alternative measure over the distribution.

Low concentration can reflect several acceptable alternatives, conflicting criteria, or insufficient evidence. Inspect those causes before choosing clarification, additional evidence, or a consumption rule. High concentration can coexist with an incomplete candidate set or a mistaken premise. Uncertainty in an unused conditional answer need not block a different branch.

Independent question evaluation is not statistical independence. Separate answers are not a joint distribution, and changing primitive type need not preserve probabilities or thresholds. Exact numerical repeatability is not guaranteed. For probability-consuming policies, assess calibration on relevant outcomes; for ranking, assess order quality. For acceptance or abstention, measure errors among accepted items together with coverage. [Consumer policy](composition-and-execution.md#joint-meaning-and-consumer-policy) explains combination and threshold evaluation.

Sources: [Confidence](https://docs.typesafe.ai/confidence), [structural invariants](https://docs.typesafe.ai/model-jaggedness/jev-1.13#common-sense-structural-invariants). [Recorded repeated-request observations](https://github.com/anessbelbati/jev-rerank-bench/blob/cd9a35b22aeb4187334f7018a0ee1960a7470586/results/determinism.json) are community measurements, not a universal variability bound.

## Model Limitations to Check

The following are documented failure modes to investigate for the selected model, not permanent limitations assigned to every release.

| Failure mode | Consequence for request construction |
| --- | --- |
| Literal interpretation of scope, negation, and conditions | State the intended condition explicitly; do not rely on implied intent |
| Weak exact arithmetic, counting, and date ordering | Compute exact relations in code and supply what remains relevant to semantic interpretation |
| Difficulty with encoded numerical representations | Resolve authoritative encodings and expose their known meaning or computed relation |
| Sensitivity to indirection | Make the actual subject and comparison directly identifiable |
| Irrelevant state can reduce accuracy | Preserve decision-changing evidence while removing material unrelated to the judgment |
| Adversarial framing can change an answer | Keep source content distinct from evaluation instructions; assess the actual input conditions rather than assuming names create protection |
| Conflicting instructions and criteria impair interpretation | Describe the same relationship with consistent polarity and answer boundaries |

These properties motivate concrete representations; they do not establish a preferred key casing, nesting depth, field count, or batch size. Numeric preprocessing should preserve units and provenance rather than turn every number into an unsupported adjective. Verify model changes before carrying forward release-specific assumptions.

Source: [Documented model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).
