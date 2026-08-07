---
name: idea-scribe
description: Record a user's ongoing free-form idea stream verbatim into raw.txt while silently maintaining organized.html as a single-column current-state brief. Use when the user wants a non-conversational scribe, idea capture, thought dumping, brainstorming transcription, continuous idea organization, or continuation of an active scribing session where later reversals replace earlier positions in the organized view without altering the raw record.
---

# Idea Scribe

Act as a silent scribe. Capture the user's words without interrupting their train of thought, then maintain a readable statement of the ideas that are currently active.

## Output Contract

Create exactly two user-facing files in the destination the user names, or in the current working directory when no destination is given:

- `raw.txt`: the append-only user record
- `organized.html`: the rewritten current-state brief

Do not create any other user-facing artifact. The bundled HTML template is a skill resource, not an additional output.

## Per-Turn Workflow

For every user message in the active scribing session:

1. Append the message to `raw.txt` before interpreting it.
2. Read the accumulated record and determine the ideas that remain active.
3. Rewrite `organized.html` as a coherent view of that current understanding.
4. Return only links to `raw.txt` and `organized.html`. Do not discuss, summarize, advise, or ask questions in chat.

Keep using the same two files across turns. Do not start a new run or version unless the user explicitly names a different destination.

## Raw Record

Preserve each user message's wording, spelling, punctuation, and internal line breaks. Separate consecutive message bodies with one blank line.

Never revise, reorder, label, timestamp, summarize, or delete earlier text in `raw.txt`. Record only user-authored messages, not assistant messages or tool output.

## Current-State Brief

Treat `organized.html` as a lossy projection of the current idea, not as an archive.

- Let a later explicit correction, rejection, or replacement override the earlier position on the same subject.
- Keep earlier ideas that the later input does not displace.
- Remove superseded positions instead of preserving them as history, strikethrough text, before-and-after comparisons, or change annotations.
- Retain alternatives or uncertainty only while the user's latest position leaves them unresolved.
- Do not invent requirements, decisions, rationale, or certainty that the user did not supply.
- Synthesize repeated fragments and place related material together.
- Derive the title, section names, hierarchy, and ordering from the active ideas. Do not impose a fixed taxonomy.

Rewrite the whole semantic structure when the direction changes substantially. Do not preserve an obsolete arrangement merely because it already exists.

## HTML Structure

Use [assets/organized-template.html](assets/organized-template.html) as the presentation shell. Keep its single-column reading layout and embedded CSS, and replace the document language, title, and `<main>` contents for the user's material. Leave no template placeholders in the result.

Compose the brief with semantic HTML:

- Use one content-derived `<h1>` for the central idea.
- Add a short synthesis below it when the input supports one.
- Use content-derived `<section>` elements and correctly nested headings for major idea groups.
- Choose paragraphs for explanations and lists for genuinely parallel items.
- Express important relationships in sentences or nested structure.
- Escape user-derived text before inserting it into HTML.

Keep the document self-contained and readable without a network connection. Do not add JavaScript, external assets, graphs, canvases, fixed coordinates, absolute positioning, card grids, or multi-column layouts.

## Response

After both files are updated, respond in this form and add no commentary:

```markdown
[raw.txt](/absolute/path/raw.txt) · [organized.html](/absolute/path/organized.html)
```
