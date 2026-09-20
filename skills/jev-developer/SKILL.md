---
name: jev-developer
description: Design, implement, and improve software using TypeSafe AI's Jev. Use for Jev questions, evidence representation, typed judgment composition, API integration, and diagnosis of Jev-backed behavior.
---

# Jev Developer

Design and implement Jev judgments that fit the requested behavior. Jev evaluates supplied information and returns typed judgments. The SDK handles transport and response types; the calling software prepares evidence, performs exact calculations, resolves returned IDs, and applies results. Jev does not retrieve external evidence, generate free-form content, or execute selected operations. Additional capabilities belong to the application only when its requirements need them.

## Know the Interface

Jev evaluates one `state` against named `questions`. Each question contains its own `instructions` and answer definition. The response associates each typed answer with its question ID.

- **Choice** selects a supplied option. Its probabilities compare those alternatives; a relative winner need not be suitable.
- **Noul** returns the probability that its proposition is true. It has no separate confidence and does not measure attribute intensity.
- **Score** returns the expected index of described, ordered levels, with their distribution and legend. It does not reconstruct an exact numeric value.
- Question IDs are caller associations, invisible to the model. Choice option IDs and descriptions are model-facing. Put complete judgment meaning in the question content.
- Instructions and criterion descriptions can carry structured content. Their keys express ordinary meaning, not additional API operators.
- Questions in one request do not read one another's answers. Conditional consumption does not itself require sequential inference.

## Apply the Knowledge

Derive the judgment from the subject, available evidence, and distinctions the consumer needs. Choose the primitive by that information, not the final programming-language type alone. Keep a coherent relationship together; separate factors when their individual answers enable useful policy or diagnosis.

| Need | Reference |
| --- | --- |
| Choose a primitive or interpret its distribution | [Model and answer semantics](references/model-and-answer-semantics.md) |
| Build evidence, locate subjects, or define criteria | [Evidence and question design](references/evidence-and-question-design.md) |
| Combine judgments, assemble values, or arrange requests | [Composition and execution](references/composition-and-execution.md) |
| Write HTTP/SDK calls or diagnose integration failures | [Integration](references/integration.md) |

Use relevant references as needed and retain their knowledge in context. For new integrations, default to `jev-latest` unless the project explicitly selects another model. Prefer English for authored instructions and criteria where appropriate, reflecting Jev's stronger English accuracy; preserve source-language meaning. Confirm version-sensitive contracts against the installed binding and official documentation.

When behavior is wrong, locate the first mismatch among supplied evidence, candidate coverage, question meaning, response association, and consuming policy. The references give the corresponding selection and repair criteria. Within the user's permitted scope, evaluate semantic quality on relevant labeled inputs and deterministic integration with project checks. Report measured outcomes separately from source inspection and unresolved assumptions. Preserve the distinction between design discussion and requested implementation.

## Working Files

When separate working files are needed, use the project-root-relative `.codex-skills/jev-developer/<run-id>/` unless the user chooses another location. Use a unique ID for new work and reuse the original path for continuation, including older locations. Do not create a workspace for direct edits that need none. Keep implementation files in the existing project and requested deliverables at their destination. Preserve resumable data and remove only expendable files created by the current run.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.
