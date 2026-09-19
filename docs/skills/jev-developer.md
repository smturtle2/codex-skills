# jev-developer

Develop Jev integrations with concrete knowledge of evidence representation, typed questions, answer semantics, and judgment composition.

[All skills](../../README.md#skills) · [한국어](jev-developer.ko.md)

<a id="install"></a>

## Install

```text
Use $skill-installer to install skills/jev-developer from https://github.com/smturtle2/codex-skills.
```

## Use

Invoke `$jev-developer` with the behavior to build, the integration to change, or the observed result to investigate. Design discussions remain discussions until implementation is requested.

The skill covers what Jev reads, evidence placement, question and criterion meaning, answer interpretation, request dependencies, and SDK integration. It supplies domain-independent relationships and API syntax rather than fixed application schemas, workflow templates, or example-specific thresholds.

## Requirements

No bundled runtime or additional skill is required. Live inference needs TypeSafe API access and a compatible client or HTTP integration in the target project. Documentation and existing code can be inspected without making model calls. Version-dependent details are checked against official documentation and the installed binding.

## Output

The requested design, implementation, or diagnosis in the existing project, with verification evidence and unresolved limitations. Working material uses `.codex-skills/jev-developer/<run-id>/` only when needed; existing runs remain at their original paths, and deliverables stay at the requested destination.

[Read the agent instructions](../../skills/jev-developer/SKILL.md)
