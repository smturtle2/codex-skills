# Composition and Execution

Use this reference when joining judgments into a value or behavior, scheduling requests, or changing consumer policy. The relationships below are composable; they are not mandatory pipelines or a closed catalog.

## Selection, Presence, and Suitability

Let `C` be supplied candidate IDs. Let `⊥` denote an explicitly described rejection alternative; it is notation, not a reserved API label.

| Construction | Information obtained |
| --- | --- |
| `Choice(C ∪ {⊥})` | Relative selection with rejection under the given description |
| `Choice(C)` plus source-presence Noul | Candidate preference and whether the value exists in the specified source scope |
| `Choice(C)` plus candidate-specific fit Nouls | Candidate preference and fit information for the evaluated candidates |
| Noul over whether any member of `C` fits | An existential proposition about the supplied set |

An existential fit answer does not establish that the selected candidate fits. Source presence does not establish candidate coverage: retrieval or parsing may have omitted the correct occurrence. No supplied candidate is different from no matching candidate, and both differ from uncertainty among plausible matches.

With no candidates, do not construct a candidate-selection request. With one candidate, identity is already known, but suitability may still need judgment. With several, choose the information the consumer needs rather than attaching every construction mechanically.

Sources: [Selection with source presence](https://docs.typesafe.ai/cookbooks/semantic_find), [source candidate selection](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook), [relative choice and applicability](https://docs.typesafe.ai/model-jaggedness/jev-1.13#common-sense-structural-invariants).

## Collections and Reusable Judgments

```text
item identity ↔ evidence ↔ question definition ↔ answer

map     : reconnect answers to their original items
rank    : order the quantity whose meaning is being compared
filter  : apply an acceptance policy
group   : use category identity or independently assessed membership
reduce  : compute counts or aggregates in code
```

Per-item Nouls compare the truth of a common condition on each item; they are not normalized across the collection. Per-item Scores require the same rubric meaning and direction. One Choice distribution compares its supplied alternatives and cannot be merged with another shortlist's distribution as if both were an absolute scale.

Ranking does not itself require exclusion or a cutoff. For filtering, losing a relevant item and retaining an irrelevant item may have different consequences. Context selection can preserve exact surviving text and required dependencies instead of generating a replacement summary.

Keep raw judgments and their definitions separate from weights, display filters, and acceptance policy. If evidence and question meaning remain unchanged, a policy change can sometimes reuse the same answers. Changing a model, criterion, or candidate set changes the judgment-producing process and requires reconsidering that reuse.

Sources: [Re-ranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe), [composite scoring](https://docs.typesafe.ai/patterns/composite-scoring), [features consumed by a learned model](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery).

## Values and Structure

For a source-backed value, code discovers candidate occurrences, Jev selects the semantic role, and code resolves the ID to exact source content. Preserve each occurrence's identity and context. Parsing, normalization, and exact calculations belong after or before the judgment as their dependencies require. Selection cannot repair missing candidates.

Bounded components can also be evaluated and assembled into a larger typed value. Distinguish omission from explicit false or a supplied value when the domain requires it. Code checks the assembled result: individually valid fields do not imply a compatible tuple. When a field needs information that another answer determines, construct that information before the dependent judgment.

Boundary judgments can determine how ordered source units are grouped. Code then constructs blocks while preserving order and content. A later judgment about those blocks has a genuine dependency because its subjects did not exist before grouping.

Sources: [Source occurrence extraction](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook), [bounded component assembly](https://docs.typesafe.ai/cookbooks/date_extraction_cookbook), [structure recovery](https://docs.typesafe.ai/cookbooks/autoformat).

## Requests and Information Dependencies

Questions whose evidence and subjects already exist can share a request. State a speculative question's premise explicitly; consume its answer only for the applicable branch. Do not write a question that implicitly reads another answer from the same request.

Sequence inference when an earlier answer is needed to retrieve material, construct the next subject, or establish the next candidate set. Separate calls can also be a scheduling choice without a semantic dependency. Distinguish these reasons before serializing a workflow.

Batching common evidence saves repeated input, but each added question costs tokens. Adding unrelated records to shared state also changes what each judgment sees. Balance context reuse with target clarity and measured quality. Concurrent independent requests still transmit their own states. Use the current request-wide and per-question limits in [integration](integration.md#resolve-model-capabilities), including serialization overhead.

Sources: [Independent and dependent questions](https://docs.typesafe.ai/primitives), [shared-state batching](https://docs.typesafe.ai/cookbooks/parallel_questions), [speculative questions](https://docs.typesafe.ai/patterns/fan-out).

## Operations and Arguments

An option ID can identify data or an executable handler. Code exposes supported operations and compatible candidate values; Jev supplies semantic selection. When argument domains already exist, conditional argument questions can accompany operation selection. Their instructions state the operation premise rather than referring to its unanswered selection question.

Code consumes only the selected operation's relevant answers and checks tuple compatibility. It resolves IDs to actual values and execution targets. Values supplied by the caller or present in source material need not be regenerated. A selection over values is distinct from generating new, open-ended content.

For changing state, bind a decision to its observation, check relevant preconditions before applying it, and inspect the actual effect. Model-facing identifiers need not carry execution authority. A correct semantic choice can still produce a wrong action if its target mapping or observation is stale.

Source: [Function calling](https://docs.typesafe.ai/cookbooks/function_calling). Source-level evidence for binding choices to existing values and targets: [input binding](https://github.com/tontoko/jev-browser/blob/2ca31b23d463c3bad43f28130344b02867a73e91/src/bindings.ts#L70). Do not inherit implementation-specific labels, limits, or thresholds from that source.

## Search, Verification, and Generation

Coarse evidence can support an initial candidate comparison; additional material can support distinctions not observable in that view. Code controls expansion and stopping. Retaining several plausible branches may preserve coverage that greedy selection loses. A local Choice probability is relative to local alternatives; a combined path value is a search statistic, not an established end-to-end success probability.

A generated value or claim can become a later judgment's subject alongside its independent evidence and requirements. Exact syntax, membership, and arithmetic can be checked in code. Semantic support, contradiction, and requirement coverage need appropriately scoped questions. A proposal cannot independently verify itself.

Use separate signals when they lead to different corrections or acceptance rules. A weighted mean expresses compensation between dimensions; it is unsuitable when one disqualifying condition must remain decisive. Do not mistake a `max`-based gate for a computed union probability. Jev returns judgments, not generated explanations; code can build feedback from the evaluated dimensions, definitions, and outcomes without inventing a rationale the model never supplied.

Sources: [Hierarchical selection](https://docs.typesafe.ai/cookbooks/hierarchical_classification), [source support](https://docs.typesafe.ai/cookbooks/citation_check), [field-level verification and consumption](https://docs.typesafe.ai/cookbooks/sde_cascade). Source-level evidence for reusing definitions and judgments as feedback: [feedback construction](https://github.com/jxucoder/mimicry/blob/0bd751f82b51ba96752c2bab910ec6496ed1696f/src/mimicry/engine.py#L505).
