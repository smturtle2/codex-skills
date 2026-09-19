---
name: jev-developer
description: Design, implement, and improve software using TypeSafe AI's Jev. Use for Jev questions, evidence representation, typed judgment composition, API integration, and diagnosis of Jev-backed behavior.
---

# Jev Developer

Use Jev's semantic judgments to implement the requested behavior in the existing project. Jev evaluates supplied information; it does not generate prose, retrieve external evidence, calculate exact quantities, or execute the selected operation. Code supplies those capabilities. Preserve the distinction between discussing a design and implementing it.

## Know the Interface

Jev evaluates one `state` against named `questions`. Each question contains its own `instructions` and answer definition. The response associates each typed answer with its question ID.

- **Choice** selects a supplied option. Its probabilities compare those alternatives; a relative winner need not be suitable.
- **Noul** returns the probability that its proposition is true. It has no separate confidence and does not measure attribute intensity.
- **Score** returns the expected index of described, ordered levels, with their distribution and legend. It does not reconstruct an exact numeric value.
- Question IDs are caller associations, invisible to the model. Choice option IDs and descriptions are model-facing. Put complete judgment meaning in the question content.
- Instructions and criterion descriptions can carry structured content. Shared evidence can live in `state`; question-specific material can live with the question.
- Questions in one request do not read one another's answers. Conditional consumption does not itself require sequential inference.

Read [model and answer semantics](references/model-and-answer-semantics.md) when choosing or interpreting judgments, and [evidence and question design](references/evidence-and-question-design.md) when constructing or revising requests. Retain relevant knowledge in context; do not reread mechanically. These references contain the operational distinctions, not just links to external documentation.

## Construct the Judgment

Identify the actual subject, the relation to judge, the available evidence, and the answer distinctions the consumer needs. Derive fields and criteria from those distinctions. Preserve source ownership, occurrence identity, qualifications, units, and observation scope where they affect the answer. A clearer label cannot supply a missing observation.

Bind each question to its actual evidence location or include its local subject in structured instructions. Construct paths and answer-to-subject mappings from the same input snapshot. Keep observations distinct from proposed values and prior model assessments. Descriptive application keys organize content; they do not add API operators or access controls.

Give neighboring alternatives distinguishable meanings. Define Noul polarity consistently and Score levels on one interpretable dimension. Keep a coherent relationship together; separate judgments when their answers carry independently useful information. Neither a universal state schema nor one question per field follows from the API.

## Compose and Integrate

Use [composition and execution](references/composition-and-execution.md) when combining judgments, assembling values, choosing actions, or arranging calls. Preserve the information required by the consumer rather than choosing a primitive from the final programming-language type alone. Let actual data dependencies determine which requests must wait.

Use [integration](references/integration.md) before writing API code or changing an existing binding. Inspect the project's SDK version and existing request, configuration, and error handling. Verify version-dependent details against the relevant official documentation or installed types; do not replace project choices with cookbook settings. If live documentation is unavailable, use the recorded contracts and installed types, identifying what remains unverified.

For new integrations, default to `jev-latest` unless an explicit project requirement selects another model. Prefer English for authored instructions and criteria when appropriate, reflecting Jev's stronger English accuracy; preserve the meaning of source-language evidence. The integration reference explains model selection and language considerations.

Implement the evidence preparation, typed request, answer association, and consuming behavior that the task needs. Keep exact arithmetic, parsing, compatibility checks, and effects in code. A selected source ID resolves to original content; a selected operation resolves to supported code. Use a generative component only where content production is needed.

## Diagnose and Verify

Inspect the actual evidence projection, instructions, criteria, candidate mapping, answer, and consumer at the first observed mismatch. Missing evidence, incomplete candidates, subject mix-ups, incorrect question boundaries, and incorrect result handling require different repairs. Revise the responsible representation or composition instead of appending exceptions to a misunderstood question.

Compare semantic quality on relevant labeled inputs and verify deterministic behavior with the project's established checks, within the user's permitted scope. The references explain representation comparisons, probability interpretation, and failure boundaries. Do not infer correctness from valid types, increased confidence, or a successful HTTP response. Separate measured outcomes from source-level inspection and unexecuted assumptions.

Keep question meaning separate from acceptance thresholds, ranking rules, and execution policy. Derive those policies from the requested behavior and available evaluation evidence. Report implemented behavior, meaningful validation, and unresolved limitations; do not claim a policy is calibrated without relevant measurements.

## Working Files

When separate working files are needed, use the project-root-relative `.codex-skills/jev-developer/<run-id>/` unless the user chooses another location. Use a unique ID for new work and reuse the original path for continuation, including older locations. Do not create a workspace for direct edits that need none. Keep implementation files in the existing project and requested deliverables at their destination. Preserve resumable data and remove only expendable files created by the current run.

When creating the default workspace in a Git project, ensure `/.codex-skills/` is ignored unless the user intends to version that data.
