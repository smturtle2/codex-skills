# Server Guide Contract

Use one Markdown file maintained by the server administrator. It is evidence for Moru's answers, not a response-template system.

## Required behavior

- State only server-specific facts that players may be told.
- Keep operational secrets, private player information, network addresses, tokens, and recovery procedures out of the guide.
- Update the guide when a rule, command, economy, event, or supported plugin behavior changes.
- When the guide is silent, Moru must say it cannot verify the answer instead of guessing.

## Recommended sections

```markdown
# Server Guide

## Identity
- Server language and community tone.

## Rules
- Player-visible rules and reporting route.

## Getting started
- Spawn guidance, claimed land, homes, and common commands.

## Features
- Intended player-facing features with versioned plugin names where relevant.

## Events and support
- Active events, support contact, and known limitations.
```

Keep this file concise. Moru may read the configured file paths with `guide`; it does not rewrite them during a steward session.
