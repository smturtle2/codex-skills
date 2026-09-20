---
name: jev-developer
description: Design, implement, and improve software using TypeSafe AI's Jev. Use for Jev questions, evidence representation, typed judgment composition, API integration, and diagnosis of Jev-backed behavior.
---

# Jev Developer

Build the requested software behavior using Jev where semantic judgment supplies information the program needs. Jev evaluates supplied information and returns typed judgments. The SDK handles transport and response types; calling software prepares evidence, performs exact calculations, resolves IDs, and applies results. Jev does not retrieve external evidence, generate free-form content, or execute selected operations.

## Design from the Required Behavior

Start from the required output or effect and available inputs. Identify the unresolved meaning that changes the result and the information Jev must read to judge it. Express the subject, conditions, and evidence relationships in the request. Assign known transformations, exact calculations, and data joins to code where appropriate, so the remaining semantic judgment has the context it needs.

Choose judgment units and answer spaces that preserve the information needed to construct the result. Existing values can become candidates, relations can be judged over pairs, and structure can be assembled from boundary or component judgments. A complex output need not require a complex model answer.

Use [composition and execution](references/composition-and-execution.md) to derive and compare constructions. Implement the evidence preparation and result consumption with the API call, including how absence or uncertainty affects behavior. Its sections describe alternatives, not a mandatory pipeline.

## Know the Interface

Jev evaluates a shared `state` through named questions and returns answers by question ID.

- `state` supplies the evidence and situation to evaluate.
- `instructions` define what to judge about that evidence.
- `criteria` define the answer meanings: optional true/false clarification for Noul, alternatives for Choice, or ordered levels for Score.

- **Choice** selects a supplied option. Its probabilities compare those alternatives; a relative winner need not be suitable.
- **Noul** returns the probability that its proposition is true. It has no separate confidence and does not measure attribute intensity.
- **Score** returns the expected index of described, ordered levels, with their distribution and legend. It does not reconstruct an exact numeric value.
- Question IDs are caller associations, invisible to the model. Choice option IDs and descriptions are model-facing. Put complete judgment meaning in the question content.
- Instructions and criterion descriptions can carry structured content. Their keys express ordinary meaning, not additional API operators.
- Questions in one request do not read one another's answers. Conditional consumption does not itself require sequential inference.

## Apply the Knowledge

| Need | Reference |
| --- | --- |
| Choose a primitive or interpret its distribution | [Model and answer semantics](references/model-and-answer-semantics.md) |
| Build evidence, locate subjects, or define criteria | [Evidence and question design](references/evidence-and-question-design.md) |
| Turn required behavior into judgments, values, and request dependencies | [Composition and execution](references/composition-and-execution.md) |
| Write HTTP/SDK calls or diagnose integration failures | [Integration](references/integration.md) |

Use relevant references as needed and retain their knowledge in context. For new integrations, default to `jev-latest` unless the project explicitly selects another model. Prefer English for authored instructions and criteria where appropriate, reflecting Jev's stronger English accuracy; preserve source-language meaning. Confirm version-sensitive contracts against the installed binding and official documentation.

When behavior is wrong, locate the first mismatch among supplied evidence, candidate coverage, question meaning, response association, and consuming policy. The references give the corresponding selection and repair criteria. Within the user's permitted scope, evaluate semantic quality on relevant labeled inputs and deterministic integration with project checks. Report measured outcomes separately from source inspection and unresolved assumptions. Preserve the distinction between design discussion and requested implementation.

## Working Files

When separate working files are needed, use the project-root-relative `.codex-skills/jev-developer/<run-id>/` unless the user chooses another location. Use a unique ID for new work and reuse the original path for continuation, including older locations. Do not create a workspace for direct edits that need none. Keep implementation files in the existing project and requested deliverables at their destination. Preserve resumable data and remove only expendable files created by the current run.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.
