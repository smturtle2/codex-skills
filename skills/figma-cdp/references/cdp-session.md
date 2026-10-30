# CDP session and tool contract

The authoring criteria and primary-tool priority are in [SKILL.md](../SKILL.md). This reference describes the connection, accepted data, execution results, and host output. Figma functionality is documented in the [official API reference](https://developers.figma.com/docs/plugins/api/api-reference/).

## Connection

The module exports `createFigmaCDP(cdp, { fileKey })` and has no package dependencies. Supply an existing host connection whose `send(method, params)` supports `Runtime.evaluate`, and the requested file's actual key from its URL. File binding accepts HTTPS Figma Design URLs on `www.figma.com` with a `/design/` or `/file/` path. The selected tab must expose the live `window.figma` API and permit the intended operations.

Load the entry module in the host's JavaScript runtime using its documented local-module support. Resolve `helperModuleUrl` to this installed skill's `scripts/figma-cdp.mjs`. A shell process does not acquire the host's browser connection merely by importing the module.

For a host that exposes the selected tab's CDP capability:

```js
const cdp = await tab.capabilities.get("cdp");
const { createFigmaCDP } = await import(helperModuleUrl);
const tool = createFigmaCDP(cdp, { fileKey });
```

`tab`, `helperModuleUrl`, and `fileKey` come from the actual host and target file. Reacquire the capability and recreate the helper when that connection is replaced or the host's JavaScript session resets. Every request verifies the live file URL, and operations resolve fresh native references by identity.

A newly established or replaced connection is ready for editing after a primary read-only inspection succeeds. Use the host's documented controls to recover an unavailable connection, then verify the target file and observed state again. Handle uncertain writes under [Results and failures](#results-and-failures).

The host assembles the trusted common runtime and self-contained operation factories for CDP evaluation. The browser does not import local host module paths. Native prerequisites and operation sequencing belong to those factories; task-specific scene generators are not part of the interface.

## Primary tools

| Method | Contract |
| --- | --- |
| `inspect(query = {})` | Read bounded document, property, text, resource, font, state, or capability data. |
| `edit({ operations }, options = {})` | Execute an ordered batch of explicit document changes. |
| `view(request, options = {})` | Change active page, selection, or camera state. |
| `export({ id, settings })` | Export the native node using declared format-specific settings. |

Inputs are plain JSON data: finite numbers, strings, booleans, null, arrays, and plain objects. Argument values are copied before queueing. Native objects, functions, callbacks, getters, symbol keys, sparse arrays, and cyclic structures are not accepted as data.

Read the implemented contracts through the registry:

```js
nodeRepl.write(await tool.inspect({ kind: 'capabilities' }));
```

The result identifies the primary tools, fallback, inspection kinds, edit actions, required and optional fields, and declared native requirements. Implemented support and native availability are separate observations. API exposure does not establish that a particular target, font, permission, library, or plan will permit the operation.

## Inspection

`query.kind` defaults to `nodes`. Use actual identities returned by the document or previous operations.

| Kind | Data |
| --- | --- |
| `nodes` | Hierarchy for `ids`; omit them for the current page. Options are `fields`, `depth`, and `limit`. |
| `children` | Child window for `id`, with `offset`, `limit`, `fields`, and `depth`. |
| `property` | Focused value window using `id`, `entityKind`, `path`, `offset`, and `limit`. |
| `text` | Styled segments for a text node's `id`, optional `start`, `end`, `fields`, and character `limit`. |
| `fonts`, `fontAxes` | Available fonts with filtering/paging, or variation axes for a requested `family`. |
| `pages`, `state` | Page identities, or active page, selection, and viewport state. |
| `component` | Component or instance definitions and actual property keys for `id`. |
| `styles`, `variables`, `collections`, `modes`, `images`, `libraries` | Resource observations using the kind's declared identity, filter, and paging fields. |
| `capabilities` | Implemented operation contracts and native availability observations. |

Node inspection defaults to depth 1 and a limit of 100 visited nodes; accepted bounds are depth 0–20 and limit 1–1000. Child windows default to depth 0. `fields` accepts at most 40 direct property names. Identity and type are returned independently of the selected fields; `parentId` is a derived observation. `children` is controlled by hierarchy inspection rather than a property field.

Hierarchy results contain `roots`, `visited`, `depth`, `limit`, `truncated`, and `unvisited`. Bounded branches report actual identities and continuation requests. Child windows also report `offset`, `total`, `nextOffset`, and a continuation. Follow these observations when a complete branch is needed.

Property inspection follows a `path` of property names and nonnegative indices on the identified native entity. It reads data without invoking methods. String windows allow up to 4000 UTF-16 units; array/object windows allow up to 100 entries. Results identify the value kind, total length, offset, next offset, and continuation. Nested truncated values can carry their own focused continuation requests.

Ordinary property serialization is bounded to 4000 characters per string, 100 entries per array/object, six nested levels, and 10000 visited values. Absent fields are omitted; mixed values, references, undefined values, non-finite numbers, unsupported values, getter errors, cycles, and truncated values use explicit `$type` markers. Markers describe observations and are not native values to write back. A hierarchy's `truncated` flag and a property's truncation marker describe different bounds.

Text queries use half-open UTF-16 `start`/`end` offsets and reject boundaries that split surrogate pairs. Their segment window reports completeness and `nextStart`; each call limits returned character range and segment count. Resource and page lists report their own paging metadata. Read-only inspection can load requested page contents but does not import resources or switch the active page.

## Editing

`operations` contains 1–100 flat operations. Each identifies an `action` and `kind`; `kind` defaults to `node`. The capability registry is the source for accepted fields and supported combinations.

| Kind | Actions |
| --- | --- |
| `node` | `create`, `update`, `scale`, `text`, `duplicate`, `move`, `remove`, `group`, `ungroup`, `boolean` |
| `component` | `define`, `updateDefinition`, `removeDefinition`, `createSlot`, `combineVariants`, `detach`, `import` |
| `style` | `create`, `update`, `remove`, `import` |
| `collection` | `create`, `update`, `remove` |
| `variable` | `create`, `update`, `remove`, `import` |
| `mode` | `create`, `update`, `remove` within a collection |
| `image` | `import` from encoded bytes or a URL |

Node creation accepts the native types listed by the registry. `INSTANCE` additionally requires `componentId`; its handler owns creation, attachment to `parentId`, property preparation, and result reporting. Creation and duplication return actual identities for later dependent operations; batches do not provide symbolic scene aliases.

For scene-node creation including `INSTANCE`, omitted `parentId` uses the page captured once when the browser request starts executing, after earlier queued requests. That default remains fixed throughout the request; supply `parentId` for a specific previously observed destination. `PAGE` creation belongs to the document root. Element selection does not determine edit targets.

Destination preparation precedes native creation or cloning; creation and final attachment then run without an intervening await.

For node creation/update, ordinary `props` are applied before `styles`, `bindings`, `modes`, `component`, and `reactions`. The property helper prepares fonts, assigns explicit `layoutMode` and `fontName`, resizes explicit dimensions, then assigns remaining properties in supplied order. Native read-only or method-backed fields use the corresponding declared edit fields:

- `styles`: `fill`, `stroke`, `effect`, `grid`, or `text` mapped to a style ID; an empty string clears the applied style.
- `bindings`: an array of `{ field, variableId }`, using null to unbind; indexed paint/effect/grid bindings also provide `index` and `subfield`. Binding selectors must be distinct within one update.
- `modes`: collection IDs mapped to mode IDs, using null to clear an explicit mode.
- `component`: instance configuration with `mainComponentId` and/or a `properties` value map using actual component property keys.
- `reactions`: native Reaction data, applied through the awaited native setter.

Font preparation accounts for typography bindings and requested mode changes, including affected descendant text. It resolves the relevant variable values and prepares current and prospective fonts before those changes. Font loading is deduplicated within a request.

Text range edits use `start`, `end`, optional replacement `characters`, and range `props`; `useStyle` selects native insertion inheritance. The handler prepares fonts and preserves unaffected runs. `scale` uses native rescaling with `factor`, including descendants, rather than resizing only the container.

`duplicate` returns `root` and `correspondence`, and accepts explicit `parentId`/`index` placement; omitted `parentId` uses the source's parent. Correspondence contains `pairs`, `transformed`, `unresolved`, `visited`, and `complete`. Matching uses native child order with structural checks. Defaults are depth 20 and limit 500; accepted bounds are depth 0–50 and limit 1–2000. Mapping results retain these bounds independently of ordinary property serialization. Type-changing or unresolved branches are explicit.

`move` accepts `coordinates: 'local' | 'absolute'`, defaulting to local. Absolute preservation rejects conflicting position/rotation overrides and requires compatible destination layout positioning. Native layout and parenting restrictions remain applicable. Grouping, ungrouping, booleans, and variant combination are owned compound operations with their own created/affected results; they are not simulated by empty-container creation. Boolean `operation` is `UNION`, `SUBTRACT`, `INTERSECT`, or `EXCLUDE`.

Resources have distinct native identities and write contracts. Variable values use `valuesByMode`, collection modes use mode operations, and imports use native library keys. Images return hashes and size metadata; place them through node image paints. Imports may reuse an existing resource, so an import result does not by itself establish new creation.

Operations run in order and stop on the first failure. Successful edit results contain per-operation outcomes. Failed batches report completed/failed outcomes and unstarted operations in `partial`. Earlier mutations can remain; there is no rollback or automatic replay.

## View and export

`view` accepts `pageId`, `selection`, `fit`, `center`, and `zoom`. Selection and fit targets must belong to the requested page. An empty selection clears selection; fit requires at least one node. Fit and explicit center/zoom are alternative camera specifications. Page, selection, and camera changes return the observed editor state. Selection summaries include at most 100 nodes, with `selectionCount` and `selectionContinuation` for larger selections. Document operations can also have native selection side effects, which their results may report.

Only an explicit `pageId` requests navigation. When omitted, `view` uses the page captured at request execution start. It checks that the expected page is active immediately before each selection or camera write and before reporting success for requested changes. An unexpected page change stops the request; the failure identifies the expected and actual page IDs and retains completed progress under [Results and failures](#results-and-failures).

`export` accepts native settings for `PNG`, `JPG`, `SVG`, `PDF`, `SVG_STRING`, and `JSON_REST_V1`; omitted settings default to PNG. The returned value is one of:

```text
{ kind: 'binary', mimeType, base64 }
{ kind: 'text', mimeType, text }
{ kind: 'json', mimeType, data }
```

Export payloads bypass ordinary inspection serialization limits. The host displays or saves the returned data using its supported APIs.

## Optional inspection and preview

`edit`, `view`, and fallback `run` accept `options.inspect` and `options.preview`, using primary inspection queries and export requests. Node observations can use a single returned node identity when their target is omitted; provide an explicit target when the operation has multiple or non-node results.

The primary operation is acknowledged before optional observations execute. Results are nested under `inspection` and `preview`, each with its own success/error state. A successful edit remains `ok: true` if observation fails. This is not an atomic snapshot against other helpers or human edits.

## Host output

Returned values exist in the host's JavaScript runtime. Expose relevant operation outcomes, identities, and state through the host's tool output API. Saved records and runtime variables are separate from visible tool output. Host-side calculations can use these observations without executing analysis inside the Figma document.

For a host that provides `nodeRepl.write` and `nodeRepl.emitImage`, these independent examples use variables resolved for the current work:

```js
nodeRepl.write(await tool.inspect(query));
```

```js
const result = await tool.edit({ operations }, {
  inspect: inspectionQuery,
  preview: exportRequest
});
const { preview, ...state } = result;
nodeRepl.write(state);
if (preview?.ok && preview.value.kind === 'binary' &&
    ['image/png', 'image/jpeg'].includes(preview.value.mimeType)) {
  await nodeRepl.emitImage(
    `data:${preview.value.mimeType};base64,${preview.value.base64}`
  );
} else if (preview) {
  nodeRepl.write({ ok: preview.ok, error: preview.error, kind: preview.value?.kind });
}
```

Use the image display API only for image formats it supports; save other artifacts through the host's supported file API. Keep binary payloads out of text output and follow the skill's working-file convention when retaining local artifacts.

## Fallback only: `run`

The fallback contract is `run(program, input = {}, options = {})`. The primary-tool priority in [SKILL.md](../SKILL.md) governs its use.

`program` is an explicit JavaScript body inside an awaited async function. Its scope provides `figma`, `input`, `node(id)`, `apply(target, props)`, `brief(target)`, `step(label, fn)`, and `recordCreated(target)`. The shared `apply` mechanics prepare and assign ordinary node properties. Step labels and recorded creations describe declared progress; arbitrary native code does not automatically produce a complete change ledger.

Fallback execution is conservatively treated as a possible write even when its body was intended only to query data. Its return value uses ordinary bounded serialization. It is not a read-only escape from uncertain-write handling.

## Results and failures

Local argument validation throws `TypeError` before queueing. Accepted requests return `ok`, `requestId`, `completedSteps`, `createdNodeIds`, `createdEntities`, `affectedEntities`, and `mutation`. Success contains `value`; failure contains a structured `error`, `failurePoint`, and any available partial batch outcomes. Native identities distinguish node/resource IDs from image hashes, and mode identities retain their collection ID. Ledgers are bounded; `ledgerTruncated` reports omitted entries. A type-specific failure can occur after creation, leaving a known identity in the creation ledger.

`mutation` is `none`, `possible`, or `unknown`. A write transport failure, protocol exception, or missing result leaves its outcome unknown. Neither an error nor a request ID establishes rollback or deduplication.

Requests execute sequentially within one helper instance. An uncertain or potentially partial `edit`, `view`, or `run` blocks that instance's queued and subsequent unstarted writes. `inspect` and `export` remain available for reconciliation. After establishing the actual document and editor state, create a fresh helper to continue writing. Recreating it does not cancel an earlier operation that may still be running.

Sequencing is local to the instance and does not lock the document against other tools or human collaborators. Browser connection controls, file creation/renaming, presentation interaction, browser screenshots, artifact saving, and host-side analysis retain their host responsibilities.
