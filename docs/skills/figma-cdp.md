# figma-cdp

Create and refine designs directly in a live Figma document through a shared CDP tool, with native editing and access to the actual rendered result.

[All skills](../../README.md#skills) · [한국어](figma-cdp.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/figma-cdp from https://github.com/smturtle2/codex-skills.
```

## Requirements

The host must provide an existing browser CDP connection supporting `Runtime.evaluate` and a JavaScript runtime that can load the installed helper module. The requested Figma file must be accessible in that browser, allow the intended edits, and expose the live `window.figma` API. The connection and API are checked against the actual environment; availability in one environment does not establish support in every browser or Figma context.

The bundled module has no package dependencies. It uses the host's browser connection and does not establish a separate connection or install a browser extension or MCP server.

## Example

```text
Use $figma-cdp to {design_request}.
Figma file: {figma_file}
References: {reference_materials}
```

Supply the requested design and target file or open tab. Reference materials are optional. These placeholders represent values from the current request.

## Working in Figma

The agent creates and refines the result in the actual Figma document using the shared tool. Operations that carry out a settled design choice are grouped. When a further design choice depends on document structure or a visual result, the agent inspects or renders the relevant result and uses that evidence to decide.

The primary interface has four tools:

| Tool | Responsibility |
| --- | --- |
| `inspect` | Observe document structure, properties, text segments, resources, fonts, editor state, and supported operations. |
| `edit` | Apply declared changes to nodes, structure, text, components, resources, and prototype reactions. |
| `view` | Change the active page, selection, and camera. |
| `export` | Return native exports with format-specific settings and typed output. |

`run` is a fallback only. The agent uses it solely when a required native capability is unavailable through the primary tools, and never to bypass or replace operations they already support.

The shared implementations own native reference resolution, font preparation, compound-operation sequencing, and outcome reporting. The agent owns design decisions and analyzes returned observations in the host. Capability inspection reports the implemented contracts and native availability separately; a listed API is not a guarantee that a target, permission, font, library, or plan will permit an operation.

Bounded inspection includes continuation, and duplication preserves conditional descendant correspondence. Ordered edit batches use actual identities and report per-operation outcomes. Optional inspection and export reuse the primary tools after the edit acknowledgement. Unsuccessful operations report known progress and uncertainty; uncertain edits are not replayed automatically. Fallback execution has the same connection and uncertainty handling and is conservatively treated as a possible write.

When creation omits a parent, scene nodes and instances use the page fixed when the request starts executing. Explicit-ID document edits keep their targets while the user views another page. `view` stops when its page changes unexpectedly.

The host retains browser connection and recovery controls, file creation and renaming, presentation interaction, browser screenshots, artifact saving, and analysis. The helper uses trusted common runtime code in the browser; it does not require the browser to import host filesystem modules.

Consult the [Figma Design guides](https://help.figma.com/hc/en-us/categories/360002042553-Figma-design) for Figma features and their use. The skill's [session and tool contract](../../skills/figma-cdp/references/cdp-session.md) defines connection readiness, recovery, page behavior, and the helper's operation contracts.

## Working files

When local files are useful, their default location is the project-root-relative `.codex-skills/figma-cdp/{run-id}/`. A requested location takes precedence. New work uses a unique directory, and existing work resumes at its original path, including older locations. Keep resumable data and remove only expendable intermediates created by the current run. Keep `/.codex-skills/` ignored in Git unless its contents are intentionally versioned.

## Output

The result is the authored Figma document, with links to the relevant file or nodes and any requested exports. Before completion, the agent evaluates the actual composition and native editability against the requested outcome and resolves substantive problems. Links, returned state, and image previews support that assessment but do not by themselves establish quality. Saved renders and working records can support follow-up work; material limitations are reported with the result.

[Read the agent instructions](../../skills/figma-cdp/SKILL.md)
