# Composition and Execution

Use this reference to derive a Jev-backed implementation from required behavior. The constructions are application designs using Jev's primitives, not additional API operators or a fixed workflow.

## Find the Judgment That Enables the Result

Relate the required output or effect to available inputs. Separate known transformations from unresolved meaning: parsing exposes possible values, known constraints narrow candidates, and semantic judgment identifies the requested role. Jev contributes the missing information at that boundary.

Work backward from what the consumer needs to know. Express it as a distinction over an identifiable subject and evidence. A useful answer changes the output, a policy decision, or evidence obtained next. If every answer leads to the same behavior, reconsider the question's purpose. If available evidence cannot resolve the distinction, obtain the missing material or represent the unresolved state.

Choose judgment units by both the required result and the context each judgment needs. An item-level question may still depend on shared conditions or other items. Supply those relationships or judge the relation as a unit. Decompose when the resulting questions each have sufficient context and their answers preserve what the consumer needs. When a later judgment uses an earlier result, explicitly supply that result as an assessment together with the evidence needed to interpret it.

## Represent the Result Through Judgments

The required output type alone does not determine the primitive. Consider what information must survive from input to output:

| Required information | Possible representation | What calling code supplies |
| --- | --- | --- |
| Identity of an existing value or operation | Choice over meaningful candidate IDs | Candidate discovery, ID-to-value/handler mapping |
| Which subjects satisfy a condition | Noul per subject with a common definition | Subject enumeration, membership policy, collection assembly |
| Relative quality or preference | Comparable Scores/Nouls, or Choice between alternatives | Ranking or comparison aggregation appropriate to that meaning |
| Relations or boundaries among source units | Questions over relevant pairs or boundaries | Pair construction, grouping, consistency and order preservation |
| A structured value with bounded parts | Component judgments or Choice over compatible tuples | Allowed domains, compatibility checks, final assembly |

Compare constructions by retained information, candidate coverage, evidence availability, and cost. Direct tuple selection preserves joint alternatives but can enlarge the candidate space; component judgments require compatibility handling. Itemwise judgments support reuse; comparisons expose preferences within the compared set. Boundary judgments let original content survive reconstruction.

Keep the connection explicit in the implementation:

```text
source identity → supplied evidence → question/answer association
                                       ↓
required output ← code assembly/policy ← resolved semantic information
```

Determine how answers become output and whether the next subject already exists. This establishes implementation responsibilities and request dependencies; the sections below explain the choices.

## Selection, Presence, and Suitability

Let `C` be supplied candidate IDs. Let `⊥` denote an explicitly described rejection alternative; it is notation, not a reserved API label.

| Construction | Information obtained |
| --- | --- |
| `Choice(C ∪ {⊥})` | Relative selection with rejection under the given description |
| `Choice(C)` plus source-presence Noul | Candidate preference and whether the value exists in the specified source scope |
| `Choice(C)` plus candidate-specific fit Nouls | Candidate preference and fit information for the evaluated candidates |
| Noul over whether any member of `C` fits | An existential proposition about the supplied set |

An existential fit answer does not establish that the selected candidate fits. Source presence does not establish candidate coverage: retrieval or parsing may have omitted the correct occurrence. No supplied candidate is different from no matching candidate, and both differ from uncertainty among plausible matches.

With no candidates, handle the empty set in code or obtain candidates before selection. With one, identity is known but suitability may still need judgment. Measure candidate coverage separately from selection quality: judging the supplied set more accurately cannot recover an omitted answer.

Sources: [Selection with source presence](https://docs.typesafe.ai/cookbooks/semantic_find), [source candidate selection](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook), [relative choice and applicability](https://docs.typesafe.ai/model-jaggedness/jev-1.13#common-sense-structural-invariants).

## Collections and Reusable Judgments

Per-item Nouls compare the truth of a common condition on each item; they are not normalized across the collection. Per-item Scores require the same rubric meaning and direction. One Choice distribution compares its supplied alternatives and cannot be merged with another shortlist's distribution as if both were an absolute scale.

Ranking does not itself require exclusion or a cutoff. Itemwise evaluation offers a reusable common criterion; pairwise comparison can express relative preference but requires code to aggregate comparisons, handle ties or cycles, and control call count. Grouping uses category identity for exclusive membership and separate applicability for overlapping membership. Code computes counts and aggregates from the consumed decisions.

For filtering, choose policy using the consequences of false inclusion, false exclusion, and abstention. Measure retained quality together with coverage; an apparently accurate filter may discard most useful items. Context selection can retain exact surviving content and dependencies without producing a summary.

Keep raw judgments and definitions separate from weights, display filters, and acceptance policy. Reuse answers when only the consuming policy changes and the required evidence, instructions, criteria, candidates, and model identity remain applicable. An alias alone is insufficient to identify the model behind cached answers. Recheck policy quality when inputs or outcome frequencies shift.

Sources: [Re-ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe), [composite scoring](https://docs.typesafe.ai/patterns/composite-scoring), [features consumed by a learned model](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery).

## Values and Structure

Preserve source occurrence identity through parsing and normalization so selected IDs resolve to exact content. A numeric return type can come from source selection, exact code calculation, or Score's estimated degree; choose according to the required meaning.

Preserve omission separately from explicit false when meaningful. Individually valid components do not imply a compatible tuple: code checks known constraints, while a joint semantic relation may need its own judgment. Construct later candidates from earlier answers when their domains genuinely depend on those answers.

Boundary judgments can determine how ordered source units are grouped. Code then constructs blocks while preserving order and content. A later judgment about those blocks has a genuine dependency because its subjects did not exist before grouping.

Sources: [Source occurrence extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook), [bounded component assembly](https://docs.typesafe.ai/cookbooks/date_extraction_cookbook), [structure recovery](https://docs.typesafe.ai/cookbooks/autoformat).

## Requests and Information Dependencies

Questions whose evidence and subjects already exist can share a request. State a speculative question's premise explicitly; consume its answer only for the applicable branch. Do not write a question that implicitly reads another answer from the same request.

Sequence inference when an earlier answer is needed to retrieve material, construct the next subject, or establish the next candidate set. Separate calls can also be a scheduling choice without a semantic dependency. Distinguish these reasons before serializing a workflow.

Batching common evidence saves repeated state input; each added question contributes input tokens. For unchanged state and independent questions, batching avoids repeated transmission and serial latency. Adding records to state is a different change: every question now sees more context. Separate batches when limits, subject clarity, deadlines, or failure isolation warrant it. Concurrent requests each transmit their own state. Account for request-wide and per-question limits in [integration](integration.md#resolve-model-capabilities), and measure tokens and latency rather than prescribing a batch width.

Sources: [Independent and dependent questions](https://docs.typesafe.ai/primitives), [shared-state batching](https://docs.typesafe.ai/cookbooks/parallel_questions), [speculative questions](https://docs.typesafe.ai/patterns/fan-out).

## Operations and Arguments

When argument domains already exist, conditional argument questions can accompany operation selection. Their instructions state the operation premise rather than referring to its unanswered selection question.

Code consumes the selected operation's relevant answers, checks compatibility, and resolves IDs to values and targets. An unused branch's uncertain answer can be ignored. If the argument domain is open-ended, obtain candidate values from the available input or a capability the application actually needs; selection over supplied values is not generation.

For changing state, bind a decision to its observation, check relevant preconditions before applying it, and inspect the actual effect. Model-facing identifiers need not carry execution authority. A correct semantic choice can still produce a wrong action if its target mapping or observation is stale.

Source: [Function calling](https://docs.typesafe.ai/cookbooks/function_calling). Source-level evidence for binding choices to existing values and targets: [input binding](https://github.com/tontoko/jev-browser/blob/2ca31b23d463c3bad43f28130344b02867a73e91/src/bindings.ts#L70). Do not inherit implementation-specific labels, limits, or thresholds from that source.

## Search, Verification, and Generation

Coarse evidence can support an initial candidate comparison; further material can resolve distinctions unavailable in that view. Code controls expansion and stopping. Supply enough branch description to reveal relevant descendants. Retaining several plausible branches can preserve coverage lost by greedy selection; it also consumes more requests. Splitting candidates into separate Choices changes their comparison sets, so shortlist probabilities need a common comparison stage or another justified aggregation rule. Measure final candidate recovery as well as local judgment quality.

A supplied value or claim, whether authored, extracted, or generated, can be judged against independent evidence and requirements. Code checks exact syntax, membership, and arithmetic; Jev judges semantic support and relationships. A proposal cannot independently verify itself. Feedback can identify failed dimensions and their definitions, but Jev does not return a generated rationale.

Sources: [Hierarchical selection](https://docs.typesafe.ai/cookbooks/hierarchical_classification), [source support](https://docs.typesafe.ai/cookbooks/citation_check), [field-level verification](https://docs.typesafe.ai/cookbooks/sde_cascade), [source-level feedback construction](https://github.com/jxucoder/mimicry/blob/0bd751f82b51ba96752c2bab910ec6496ed1696f/src/mimicry/engine.py#L505).

## Joint Meaning and Consumer Policy

Define the intended proposition or measured attribute before choosing component questions. Ask a coherent relational condition directly when that relationship is the needed answer. Split factors when separate results enable distinct corrections, priorities, or reuse. Code can then enforce a chosen policy, but combining marginal probabilities requires care:

```text
P(A and B) = P(A) × P(B | A)     when P(A) > 0
P(A or B)  = P(A) + P(B) - P(A and B)
E[count]   = Σ P(A_i)
```

The first two need joint/conditional information; independently evaluated questions do not establish statistical independence. The last follows from linearity of expectation without independence, but represents an expected count from meaningful probabilities, not an exact count of observed truths. A model's answer to a conditionally worded question remains an estimate, not a guarantee of probabilistic consistency across calls.

A weighted mean expresses compensation between dimensions; an all-required gate preserves individually required conditions. `min`, `max`, or products used as policy scores do not automatically become calibrated joint probabilities. Choose thresholds on labeled tuning data, then assess errors and coverage on held-out inputs. Enforce known complements and deterministic identities in code instead of asking the model to rediscover them.

Related API behavior: [structural consistency limits](https://docs.typesafe.ai/model-jaggedness/jev-1.13#common-sense-structural-invariants), [confidence](https://docs.typesafe.ai/confidence). The probability identities and policy distinctions above are mathematical and design guidance, not extra model guarantees.
