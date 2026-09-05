---
name: ui-blueprint
description: Generate a visual blueprint before building new frontend UI or substantially redesigning a screen. Exclude small copy or styling changes, narrow bug fixes, and work that should preserve the existing design.
---

# UI Blueprint

Use the session's selected reasoning model. Build from a generated, saved, and inspected UI mockup.

## Workflow

1. Read the existing frontend structure, design system, routes, and components relevant to the requested screen.
2. Distill the product, audience, primary task, viewport, required content and controls, and visual constraints into a blueprint brief.
3. Use `$image-creator` to generate one product-specific mockup. Give it the brief and the project-root `ui-blueprints/` directory as the destination.
4. Inspect the saved image before writing UI code. Extract actionable notes on layout, hierarchy, typography, color, spacing, controls, and responsive behavior.
5. Implement the screen in the existing stack using local components and patterns.
6. Verify the implementation in a browser or equivalent renderer on desktop and mobile. Compare composition and hierarchy against the blueprint and repair meaningful drift.

Keep the blueprint under `ui-blueprints/` with a descriptive, non-overwriting filename even if the app does not use it as an asset. If image generation fails or is unavailable, report the blocker; proceed without a blueprint only when the user has accepted that fallback.

## Blueprint and Implementation

- Request a complete screen using the user's actual product and content. A generic placeholder mockup does not satisfy the workflow.
- Use short representative text in the image; implement exact copy from the user's requirements. Do not depend on long, precisely rendered image text.
- Choose visual elements that can be implemented with available assets and technology.
- Preserve existing routing, state management, component APIs, data contracts, and design tokens unless the task requires changing them.
- Use the image for visual direction and the repository for engineering constraints. Preserve required controls and behavior even where the static image is incomplete.
- Implement responsive behavior and component states deliberately; a desktop mockup does not specify them fully.
- Supply actual visual assets where the composition needs imagery. Keep implementation notes and prompt commentary out of product UI.
- Check text fit, usable controls, and visibility of key content as part of the visual verification.

## Handoff

Report the implementation changes, saved blueprint link, verification performed, and any meaningful deviation with its reason.
