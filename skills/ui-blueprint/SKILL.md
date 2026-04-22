---
name: ui-blueprint
description: Use when building or substantially redesigning frontend UI where visual quality matters, including websites, landing pages, web apps, dashboards, prototypes, and game UI. This skill requires Codex to generate a UI mockup image with image-creator first, inspect that image, and then implement the frontend against the generated visual blueprint instead of jumping directly into code.
---

# UI Blueprint

Build frontend UI from a generated visual blueprint, not from an unvisualized text-only plan.

## Hard Rules

- Use `gpt-5.4` as the reasoning model for this workflow whenever model selection is available.
- Before writing UI code, generate a UI mockup image through the `$image-creator` workflow.
- Save or copy the selected generated blueprint image under the project-root `ui-blueprints/` directory before implementation. Do not leave it only in the default image generation output location.
- Inspect the generated image and extract concrete implementation notes before coding.
- Do not silently skip the image step for new UI, major redesigns, visually led pages, app surfaces, prototypes, or game UI.
- Do not implement from a generic placeholder mockup. The image prompt must reflect the user's actual product, audience, content, and constraints.
- If image generation fails or is unavailable, stop and report the blocker. Continue without a generated blueprint only if the user explicitly accepts that fallback.

## When To Use

Use this skill for:

- new websites, landing pages, marketing pages, product pages, and portfolios
- new app screens, dashboards, admin tools, inspectors, editors, and data surfaces
- visual redesigns or "make it look better" requests
- prototypes, demos, games, and interactive tools where the first screen must feel designed
- UI work where layout, hierarchy, imagery, color, typography, or motion matters

Do not use this skill for:

- small text, copy, spacing, or color tweaks on an existing UI
- narrow bug fixes where the intended UI is already clear
- backend, API, data, CI, deployment, or test-only tasks
- pure accessibility or performance fixes that should preserve the current visual design

## Workflow

1. Read the existing frontend structure, design system, routes, and styling conventions.
2. Distill the UI brief into a blueprint prompt:
   - product or surface type
   - target user and primary task
   - viewport or screen type
   - information hierarchy
   - required content and controls
   - visual tone, density, and constraints from the repo
3. Use `$image-creator` to generate one strong UI mockup image before implementation. Pass the distilled blueprint brief as the image request, let `$image-creator` convert it into a model-friendly prompt, and specify the project-root `ui-blueprints/` directory as the save destination.
4. Confirm the selected image was persisted under the project-root `ui-blueprints/` directory:
   - create `ui-blueprints/` if it does not exist
   - use a descriptive, non-overwriting filename
   - keep the blueprint image even if the final UI does not directly reference it
5. Inspect the saved mockup and write a short visual extraction:
   - layout grid and major regions
   - typography scale and hierarchy
   - color palette and contrast strategy
   - component states, controls, imagery, and iconography
   - spacing, density, and responsive behavior implied by the image
6. Implement the UI in the existing stack, using existing components and local patterns first.
7. Verify in the browser or an equivalent renderer. Compare the result against the blueprint for composition, hierarchy, spacing, color, and responsiveness.
8. If the implemented screen drifts from the blueprint, revise the UI rather than rationalizing the drift.

## Blueprint Prompt Rules

- Ask for a complete screen, not a decorative fragment.
- Make the prompt specific to the user's domain; avoid generic SaaS, generic dashboard, and generic portfolio language.
- Include real UI elements that the final implementation must contain.
- Request polished product-quality UI with clear hierarchy and usable controls.
- Avoid asking the image model to render long paragraphs of exact text. Use realistic text blocks and reserve exact copy for implementation.
- Avoid mockups that depend on impossible assets, overly dense effects, or decorative elements that would not survive real implementation.

## Implementation Rules

- The generated image is the visual source of truth, but the repo remains the engineering source of truth.
- Preserve existing routing, state management, data contracts, component APIs, and design tokens unless the task explicitly requires changing them.
- Use visual assets when the screen needs imagery. Do not replace the blueprint's visual anchor with gradients or empty placeholders.
- Build responsive behavior deliberately; do not assume the desktop composition will collapse cleanly on mobile.
- Keep UI text user-facing. Do not include prompt notes, implementation commentary, or design rationale in the product surface.
- Validate that text fits, controls remain usable, and key content is visible on common desktop and mobile viewports.

## Response

When finished, report:

- where the implementation changed
- the project-local path of the saved blueprint image
- that a generated UI blueprint was used
- what verification was run
- any meaningful deviations from the blueprint and why they were necessary
