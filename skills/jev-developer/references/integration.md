# Integration

Use this reference to implement calls and diagnose transport or binding failures. The syntax below uses caller-defined variables, not application schemas. Match the installed SDK to its documentation; the HTTP overview, structured-content guide, and SDK types differ in permissiveness.

## HTTP Contract and Input Types

```text
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <API key>
Content-Type: application/json

Request = {state: string | object | array, model: string,
           questions: nonempty map<question ID, Question>}
Question = {type: "choice", instructions: content,
            criteria: map<option ID, content>}
         | {type: "score", instructions: content,
            criteria: ordered array<content>}
         | {type: "noul", instructions: content,
            criteria?: {true?: content, false?: content}}
```

This is the explicit request form. `content` is a text or structured description; acceptance of omission and null depends on its location and binding:

| Location | Contract distinction |
| --- | --- |
| `state` | HTTP and Python describe text/object/array; JavaScript's `EntryType` additionally admits null, which alone does not establish server acceptance |
| `instructions` | HTTP overview marks it required; the structured guide and SDK question types permit null, and SDK question types permit omission. Supply complete meaning explicitly |
| Choice descriptions | Text/object/array or null; null leaves the model-facing option ID as its label |
| Score descriptions | Ordered levels, starting at index zero; Python uses non-null `JSONContent` entries, JavaScript permits null entries. Use meaningful descriptions |
| Noul criteria | Optional true/false descriptions; SDKs permit structured content and null |

Nested JSON values can include numbers, booleans, and nulls. Choice uses a map; Score uses an array with at least two levels. Check current upper limits in the primitive documentation rather than inferring server limits from SDK validation. Application keys inside content carry meaning, not new transport options.

Sources: [HTTP API](https://docs.typesafe.ai/api), [structured content](https://docs.typesafe.ai/primitives/advanced), [Python question types](https://docs.typesafe.ai/sdk/python/api/types/questions), [JavaScript types](https://github.com/typesafe-ai/typesafe-sdk-js/blob/v0.6.0/src/types.ts).

## Python Binding

Package: `typesafe-sdk`. `TYPESAFE_API_KEY` supplies authentication; explicit `api_key=` overrides it. Constructors also accept `model=` and `base_url=`; environment fallbacks are `TYPESAFE_DEFAULT_MODEL` and `TYPESAFE_BASE_URL`.

These are alternative question constructors and calls; variables stand for the application's prepared content:

```python
from typesafe_sdk import TypeSafeClient, AsyncTypeSafeClient, Choice, Noul, Score

Choice(instructions=instructions, criteria=option_descriptions)
Score(instructions=instructions, criteria=level_descriptions)
Noul(instructions=instructions, criteria=truth_descriptions)  # criteria optional

with TypeSafeClient() as client:
    result = client.system_one(state=state, questions=questions, model="jev-latest")

async with AsyncTypeSafeClient() as client:
    result = await client.system_one(state=state, questions=questions, model="jev-latest")

result.answers[question_id]       # narrow by answer.type
result.choices[choice_id].choice
result.scores[score_id].score
result.nouls[noul_id].noul
```

Keep a client alive across related calls for connection reuse; context managers close it. Closing the SDK client also closes a supplied HTTP client, so ownership matters. The async fragment belongs in an async function. Questions may mix SDK objects and raw question dictionaries with explicit `type`.

`system_one(..., response_model=ResponseType)` parses the response into a Pydantic model. `SystemOneResponse` subclasses can expose named answers; a custom `BaseModel` describes the response body. This changes client-side access, not Jev's output vocabulary. `extra_body=` shallow-merges last and can replace `state`, `questions`, or `model`; use it only for a confirmed API feature requiring it.

Sources: [Python client](https://docs.typesafe.ai/sdk/python/api/clients/sync), [async client](https://docs.typesafe.ai/sdk/python/api/clients/async), [response types](https://docs.typesafe.ai/sdk/python/api/types/responses), [usage](https://docs.typesafe.ai/sdk/python/usage).

## JavaScript / TypeScript Binding

Package: `@typesafe-ai/sdk`. The constructor uses `apiKey`, `defaultModel`, and `baseURL`; their environment fallbacks match Python's variables. A request's `model` overrides the client default.

```javascript
import { TypeSafeClient, choice, score, noul } from "@typesafe-ai/sdk";

choice(instructions, optionDescriptions);
score(instructions, levelDescriptions);
noul(instructions, truthDescriptions);  // second argument optional

const client = new TypeSafeClient({ defaultModel: "jev-latest" });
const result = await client.systemOne({ state, questions });
const answer = result.answers[questionId];
```

Question definitions determine inferred answer types. For a heterogeneous/dynamic map, narrow `answer.type` before reading `.choice`, `.score`, or `.noul`. `systemOne(request, { signal, timeout, retry })` takes transport options separately from the request. `.withResponse()` on its returned promise provides `{ data, response, requestId }` for HTTP metadata. Keep API-key-bearing calls in a trusted runtime; browser enablement exposes the key to page users.

Sources: [JavaScript SDK](https://docs.typesafe.ai/sdk/javascript), [client](https://github.com/typesafe-ai/typesafe-sdk-js/blob/v0.6.0/src/client.ts), [builders](https://github.com/typesafe-ai/typesafe-sdk-js/blob/v0.6.0/src/questions.ts), [response access](https://github.com/typesafe-ai/typesafe-sdk-js/blob/v0.6.0/src/api-promise.ts).

## Response Association

```text
Response = {model: string, answers: map<question ID, Answer>,
            usage: {input_tokens: integer, output_tokens: integer}}
ChoiceAnswer = {type: "choice", choice: option ID, probabilities, confidence}
ScoreAnswer  = {type: "score", score, legend, probabilities, confidence}
NoulAnswer   = {type: "noul", noul}
```

Ranges and formulas are in [answer semantics](model-and-answer-semantics.md). HTTP and JavaScript Score maps use string indices; Python maps use integers. Associate answers by requested ID, preserve original-item mappings across batches, and resolve choices against the supplied candidates. Check missing answers, expected primitive types, finite ranges, and distribution sums with rounding tolerance where the binding does not enforce them.

A missing/malformed answer is an interface failure, not a negative proposition or no-match. Python's forward-compatible parser can skip unknown answer kinds; inspect `result.raw_http_response.json()` when diagnosing missing entries. Static TypeScript inference establishes expected types, not semantic correctness. Keep distributions and legends when downstream policy needs them.

Sources: [HTTP responses](https://docs.typesafe.ai/api), [Python response handling](https://docs.typesafe.ai/sdk/python/usage).

## Time Budgets and Failures

| Binding | Controls and meaning |
| --- | --- |
| Python | `timeout=` in seconds for HTTP operations; `retry=RetryPolicy(...)` on client/call; `max_retries` counts attempts after the first |
| Python retry budget | `RetryPolicy.timeout` counts the initial attempt and delays when deciding further retries; this is not a guaranteed interruption of an in-flight operation |
| JavaScript | `timeout` in milliseconds per attempt; `retry: { maxRetries: ... }`; no Python-style total retry budget in the inspected binding |
| JavaScript cancellation | `signal: AbortSignal` cancels the request and pending retries |

Derive budgets from when the application still needs the answer. Layered SDK/application retries multiply attempts; coordinate their ownership. Retrying inference and repeating an effect already executed by the application are separate decisions.

`401` calls for authentication repair; `422` for request repair; `429` and `529` for backoff under the SDK's retry policy. Use returned retry timing where supported. Python HTTP errors expose `TypeSafeAPIError.status`, `.body`, `.request_id`; connection/timeouts have separate exception classes. JavaScript `APIError` exposes `.status`, `.body`, `.requestId`, with separate connection, timeout, and user-abort errors. A successful HTTP status can still fail response validation.

Record request identity and the relevant evidence/question/model mapping for diagnosis. SDK debug logging includes unredacted request and response bodies even when credential headers are redacted; choose logging deliberately when capturing source material.

Sources: [Python retries](https://docs.typesafe.ai/sdk/python/api/retries), [exceptions](https://docs.typesafe.ai/sdk/python/api/exceptions), [JS request options](https://docs.typesafe.ai/sdk/javascript/api/interfaces/RequestOptions), [JS errors](https://github.com/typesafe-ai/typesafe-sdk-js/blob/v0.6.0/src/errors.ts).

## Resolve Model Capabilities

Use `jev-latest` for new integrations unless the project explicitly selects another model. It tracks the stable official release; versioned IDs support reproducibility and version-calibrated policies. Preserve the returned `model`. `GET /v1/models`, Python `client.models.list()`, or JavaScript `await client.models.list()` discovers available names; the listing may omit accepted versioned IDs.

Jev evaluates text and structured JSON; non-text sources need an appropriate representation before evaluation. English is its primary training language and strongest for accuracy. Prefer English for authored instructions and criteria where appropriate, preserving source-language meaning and assessing other-language workloads on their actual inputs. Domain adaptation uses supplied evidence, instructions, criteria, and consuming policy; a client response model does not train Jev.

Consult model-specific limits for both `state + all questions` and `state + longest question`, including serialized overhead. Check option/level limits in primitive documentation. These ceilings constrain valid requests; batch size and policy thresholds depend on quality and workload. If documentation conflicts, compare the precise feature reference and installed SDK/source, and identify unresolved server behavior rather than inventing a contract.

Follow the target project's environment tooling. Use uv for skill-owned Python helpers with incidental dependencies isolated from the project.

Sources: [Models](https://docs.typesafe.ai/models), [Choice](https://docs.typesafe.ai/primitives/choice), [Score](https://docs.typesafe.ai/primitives/score), [documentation index](https://docs.typesafe.ai/llms.txt).
