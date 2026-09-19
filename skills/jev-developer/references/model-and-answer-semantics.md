# Model and Answer Semantics

Use this reference to choose a judgment, interpret its answer, or distinguish model behavior from consumer policy. Model behavior depends on the selected release; verify applicable limitations in its documentation.

## What Is Evaluated

```text
state + one question's instructions + its answer definitions
    → typed answer associated with the caller's question ID
```

The request can carry several questions over the same state. A question does not receive another question's answer as hidden context. Instruction paths identify content already supplied; they do not fetch external records, execute JSONPath, or isolate the model from other supplied content.

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
probabilities: option ID → probability
Σ probabilities[option ID] = 1
choice = an option with maximal probability
```

The distribution belongs to that answer space. Adding, removing, or changing alternatives changes the comparison. Probabilities from separate candidate sets are not a common absolute-quality scale. One Choice selects one alternative; multiple independently applicable labels require separate applicability information.

An explicit rejection option participates in this same distribution. Its description determines the scope of rejection. It may mean no supplied candidate fits; it does not automatically establish absence from a larger source. Ambiguity among candidates and a definite no-match are also different information.

Candidate identity, source presence, and candidate suitability have different meanings even when code assembles the same optional return type. See [selection and absence](composition-and-execution.md#selection-presence-and-suitability).

Source: [Choice](https://docs.typesafe.ai/primitives/choice).

## Noul: Truth of a Proposition

```text
noul ∈ [0, 1]
noul = estimated probability that the defined proposition is true
```

There is no separate `confidence`. A midpoint probability expresses unresolved truth, not a medium amount of an attribute. An unavailable source is a data-availability condition, not a special meaning of `noul = 0.5`.

The proposition's scope determines the meaning of a negative answer. Lack of support in supplied material does not establish falsity outside it. A question combining support, completeness, and compatibility will not reveal which condition failed; request separate information only when that distinction matters to the consumer.

Keep `true` aligned with the instruction and `false` with its negation. Either positive or defect-oriented propositions are possible; consumer thresholds must use the actual polarity. Independently phrased questions need not produce complementary probabilities. For an exact complement of the same proposition, derive `1 - p` from its single answer.

Source: [Noul](https://docs.typesafe.ai/primitives/noul).

## Score: Distribution over Described Levels

```text
L = number of ordered descriptions
i ∈ {0, …, L - 1}
score = Σ i × probabilities[i]
legend[i] = description associated with level i
```

The descriptions define the property. Each level needs an independently understandable meaning, not a reference to a neighboring description. Combining unrelated properties in one scale can leave inputs high on one property and low on another without a meaningful position.

The expected index can fall between levels. It is not an exact quantity, a percentage of affected subjects, or a probability that the answer is correct. Equal expectations can hide different concentrations or mass at opposite ends of the scale. Use the distribution when those distinctions affect behavior.

`score / (L - 1)` rescales the index range; it does not calibrate the result as a probability or establish equal semantic spacing. Combining normalized scores requires aligned direction and a meaningful trade-off between their dimensions. A weighted preference does not automatically represent the probability of a joint outcome.

HTTP maps use stringified indices; Python SDK maps use integer indices. Retain the legend rather than inferring level meaning from an unassociated number.

Source: [Score](https://docs.typesafe.ai/primitives/score).

## Confidence and Consistency

Choice and Score `confidence` summarizes the returned distribution's concentration. It is not an additional probability of correctness, suitability, permission, or successful execution. The inspected confidence documentation does not publish a formula to reimplement; use the returned field or an explicitly defined alternative measure over the distribution.

Low concentration can reflect several acceptable alternatives as well as insufficient evidence. Inspect what the alternatives mean before interpreting a low value as failure. Uncertainty in an unused conditional answer need not block a different branch.

Independent question evaluation is not statistical independence. Separate answers are not a joint distribution, and changing primitive type need not preserve probabilities or an established threshold. Do not assume exact repeatability of returned numbers. Calibration is an empirical property over relevant predictions and outcomes, not a certificate for one answer.

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
| No free-form text generation | Obtain candidate values from source processing or another producer; Jev can select or assess them |

These properties motivate concrete representations; they do not establish a preferred key casing, nesting depth, field count, or batch size. Numeric preprocessing should preserve units and provenance rather than turn every number into an unsupported adjective. Verify model changes before carrying forward release-specific assumptions.

Source: [Documented model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).
