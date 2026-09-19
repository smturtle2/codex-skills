# Integration

Use this reference for transport, SDK compatibility, response association, and operational diagnosis. Verify the actual installed binding before implementation; the shapes below express explicit request relationships, not an exhaustive acceptance schema.

## HTTP Relationships

```text
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <API key>
Content-Type: application/json

Request = {
  state: string | object | array,
  model: supported model ID or alias,
  questions: nonempty map<question ID, Question>
}

Question = {
  type: "choice",
  instructions: content,
  criteria: map<option ID, content>
} | {
  type: "score",
  instructions: content,
  criteria: ordered array<content>
} | {
  type: "noul",
  instructions: content,
  criteria?: { true?: content, false?: content }
}
```

`content` denotes the text or structured description accepted at that location by the binding. Nested JSON can contain numbers, booleans, and nulls; top-level state and nullable descriptions have more specific contracts. The structured-content guide accepts broader forms than some compact HTTP descriptions. Python's exposed question types exclude null Score entries, while the JavaScript entry type is more permissive. Use explicit, meaningful instructions and level descriptions rather than depending on permissive null acceptance.

Custom keys inside these containers have no special transport behavior. Neither source paths nor application-specific dictionaries extend the API.

Sources: [HTTP API](https://docs.typesafe.ai/api), [structured content](https://docs.typesafe.ai/primitives/advanced), [Python question types](https://docs.typesafe.ai/sdk/python/api/types/questions), [JavaScript SDK reference](https://docs.typesafe.ai/sdk/javascript).

## Response Handling

```text
Response = {
  model: string,
  answers: map<question ID, Answer>,
  usage: { input_tokens: integer, output_tokens: integer }
}

ChoiceAnswer = {
  type: "choice", choice: option ID,
  probabilities: map<option ID, finite number in [0, 1]>,
  confidence: finite number in [0, 1]
}
ScoreAnswer = {
  type: "score", score: finite number in [0, L - 1],
  legend: map<level index, content>,
  probabilities: map<level index, finite number in [0, 1]>,
  confidence: finite number in [0, 1]
}
NoulAnswer = { type: "noul", noul: finite number in [0, 1] }
```

Use the SDK's typed results and validate any assumptions it does not enforce. Associate answers by requested IDs, check the expected primitive, and ensure selected IDs resolve to supplied candidates. Do not silently replace missing or malformed answers with negative probabilities or no-match outcomes.

Retain the mapping needed to interpret distributions. HTTP Score indices are strings; Python uses integer keys. Allow numerical rounding when checking distribution sums and expected scores. Missing fields, non-finite values, and an unmapped choice are interface failures, not uncertain semantic judgments.

Keep the original item-to-question association through batching and concurrency. Preserve the actual returned model identity when reproducibility matters. Application output may be simpler than the raw answer, but discard information deliberately according to what the consumer needs.

Sources: [HTTP API](https://docs.typesafe.ai/api), [Python response types](https://docs.typesafe.ai/sdk/python/api/types/responses), [Score wire and SDK mappings](https://docs.typesafe.ai/primitives/score).

## Bindings and Time Budgets

| Binding | Package and entry points | Timing semantics |
| --- | --- | --- |
| Python | `typesafe-sdk`; import `typesafe_sdk`; `TypeSafeClient`, `AsyncTypeSafeClient`; `Choice`, `Score`, `Noul`; `system_one` | HTTP-operation timeouts use seconds; `RetryPolicy.timeout` is a separate total retry budget |
| JavaScript / TypeScript | `@typesafe-ai/sdk`; `TypeSafeClient`; `choice`, `score`, `noul`; `systemOne` | Request timeout uses milliseconds per attempt; `AbortSignal` can cancel the request and pending retries |

The inspected JavaScript request options do not specify Python's total retry-budget field. Do not copy timeout numbers or retry configuration between languages without translating the contract. Preserve project connection reuse, cancellation, and asynchronous conventions. Follow the project's environment and dependency tooling. Use uv for skill-owned Python helper scripts, with incidental dependencies isolated from the target project.

Distinguish an HTTP-operation timeout, a retry budget, and the application deadline after which a result is no longer useful. SDK retries and application retries can multiply attempts if layered blindly. Inference retry must not automatically repeat an already executed effect.

Sources: [Python SDK](https://docs.typesafe.ai/sdk/python), [Python client](https://docs.typesafe.ai/sdk/python/api/clients/sync), [Python retries](https://docs.typesafe.ai/sdk/python/api/retries), [JavaScript request options](https://docs.typesafe.ai/sdk/javascript/api/interfaces/RequestOptions).

## Resolve Model Capabilities

Use `model: "jev-latest"` by default for new integrations. It tracks the latest stable official release and is the SDK default. Preserve an existing explicit model selection; use a versioned ID when the project requires reproducibility or policies calibrated against that version. Do not hardwire the alias to a particular release.

English is Jev's primary training language and its strongest language for accuracy according to the model documentation. Prefer English for authored instructions and criteria when the task permits. Preserve source-language evidence where translation could alter meaning, and evaluate non-English workloads on their actual content. English preference is not an English-only input restriction.

Resolve configuration from the target project and the selected model's current contract:

| Needed information | Where to establish it |
| --- | --- |
| Model identity and alias resolution | Project configuration, model documentation, and the actual response |
| Supported input modalities | Selected model's documented capabilities |
| Request-wide and per-question context limits | Model-specific limits, including how shared state and question content are counted |
| Choice option and Score level limits | Primitive documentation and the installed binding's validation rules |
| Language suitability | Model documentation and evaluation on the actual input language |

Account for serialized overhead in both context budgets. A token ceiling does not establish a useful batch size or guarantee quality with unrelated context. A permissive SDK schema does not by itself establish server support.

`GET /v1/models` discovers account-available model names. Check the model documentation before treating that listing as exhaustive of accepted versioned IDs. The response's `model` identifies the version that answered. Keep version-dependent policies reproducible; do not silently move a threshold calibrated for one version onto a moving alias. Do not translate source material merely to satisfy an assumed language requirement.

Sources: [Models](https://docs.typesafe.ai/models), [Choice limits](https://docs.typesafe.ai/primitives/choice), [Score levels](https://docs.typesafe.ai/primitives/score).

## Errors and Diagnosis

`401` indicates authentication failure; `422` indicates request validation failure; `429` indicates rate limiting; `529` indicates service overload. Follow the actual SDK's documented transient-error handling. A failed request has no proposition probability. Preserve partial failures explicitly rather than reporting missing items as negative judgments.

Trace the first incorrect transformation:

| Observation | Inspect |
| --- | --- |
| Expected answer cannot be selected | Source availability, candidate coverage, and the stated answer boundary |
| Answers belong to the wrong items | Projection order, paths, question IDs, and original-item mapping |
| An optional result has the wrong meaning | Scope of absence, candidate fit, ambiguity, and source lookup |
| Ranking changes unexpectedly | Question comparability, candidate-set changes, rubric direction, ties, and preserved distributions |
| Individually plausible components conflict | Candidate domains, tuple constraints, and missing information dependencies |
| Correct judgment causes the wrong effect | Consumed answer, policy, target freshness, preconditions, and observed execution |
| Behavior changes after an update | Evidence, instructions, criteria, model resolution, and consumer policy versions |

Record enough of these associations to reproduce the relevant failure, without requiring every source to be logged. Distinguish request acceptance, model quality, consumer correctness, and observed outcomes. Community implementations and saved measurements support concrete design alternatives; their default thresholds, batch widths, and performance claims are not API guarantees.

Source: [HTTP errors](https://docs.typesafe.ai/api). Use the [official documentation index](https://docs.typesafe.ai/llms.txt) to locate current details; `.md` variants of documentation pages can provide a compact reading form.
