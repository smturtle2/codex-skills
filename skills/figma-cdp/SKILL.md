---
name: figma-cdp
description: Create and refine designs in a live Figma document through a browser CDP connection.
---

# Figma CDP

Do not write separate code to generate the complete artifact and apply it in one pass; create it by directly manipulating Figma through the shared CDP tool.

Use `inspect`, `edit`, `view`, and `export` for all supported Figma operations.

`run` is a fallback only. Use it solely when a required native capability is unavailable through the primary tools. Never use `run` to bypass or replace operations the primary tools already support.

Keep reusable operation mechanics in the shared tools and design decisions with the agent. Analyze returned observations in the host when calculations are needed.

Consult the [Figma Design guides](https://help.figma.com/hc/en-us/categories/360002042553-Figma-design) when deciding how to use Figma features.

Group operations that carry out a settled design choice. When a further design choice depends on document structure or a visual result, inspect or render the relevant result and use that evidence to decide.

Evaluate the actual composition and native editability against the requested outcome, and resolve substantive problems before completion.

After making changes in Figma or when requesting approval, save `tool.export` renders and embed them directly in the reply instead of browser screenshots.

Use the host's documented browser controls to obtain CDP access to the requested Figma file. The helper requires `Runtime.evaluate` and access to the live `window.figma` API.

Resolve `helperModuleUrl` to this installed skill's `scripts/figma-cdp.mjs`, and obtain `cdp` and `fileKey` from the selected browser tab and Figma file.

```js
const { createFigmaCDP } = await import(helperModuleUrl);
const tool = createFigmaCDP(cdp, { fileKey });
```

Read [the CDP session and tool contract](references/cdp-session.md) for supported operations, result and image handling, fallback execution, and connection recovery. Use `inspect({ kind: 'capabilities' })` to discover the implemented operation contracts and their reported native API availability.

Keep working files, when needed, in the project-root-relative `.codex-skills/figma-cdp/{run-id}/` unless the user selects another location. Use a unique ID for new work and resume existing work in place, including older locations. Retain resumable data and remove only expendable intermediates created by the current run. Deliver exported files to the requested destinations.

In Git projects, ensure `/.codex-skills/` is ignored unless the user intends to version the working data.
