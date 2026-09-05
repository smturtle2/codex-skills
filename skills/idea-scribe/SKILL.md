---
name: idea-scribe
description: Capture an ongoing idea stream verbatim and maintain a current-state HTML brief. Use for silent scribing or thought dumping, rather than requests for discussion or advice.
---

# Idea Scribe

During an active scribing session, maintain exactly two user-facing files in the requested destination, defaulting to the current working directory:

- `raw.txt`: append-only user messages.
- `organized.html`: the current understanding of the user's ideas.

Reuse these files across turns unless the user names a different destination. Treat an explicit request to end recording or discuss the skill as session control, not another idea to silently capture.

## Record Each Idea

1. Append the user's message to `raw.txt` before interpreting it. Preserve wording, spelling, punctuation, and internal line breaks; separate message bodies with one blank line.
2. Read the accumulated record and rewrite `organized.html` to reflect the ideas that remain active.
3. Return only links to both files, without discussion, advice, questions, or commentary.

Do not modify earlier raw text or append assistant messages and tool output.

## Maintain the Brief

- Let explicit corrections, rejections, and replacements supersede earlier positions on the same subject; keep ideas they do not displace.
- Remove superseded positions from the brief. Preserve alternatives and uncertainty only while the user's latest position leaves them unresolved.
- Combine related fragments without inventing requirements, decisions, rationale, or certainty.
- Derive the title, grouping, and order from the active ideas. Restructure the brief when direction changes; do not retain an obsolete arrangement or display revision history.

Use [assets/organized-template.html](assets/organized-template.html) as the presentation shell. Replace its language, title, and `<main>` contents; leave no placeholders. Keep semantic headings, escaped user-derived text, the single-column layout, and embedded CSS. The result must work offline without JavaScript, external assets, graphs, canvases, or fixed-position layouts.

## Reply

After updating both files, use their absolute paths:

```markdown
[raw.txt](/absolute/path/raw.txt) · [organized.html](/absolute/path/organized.html)
```
