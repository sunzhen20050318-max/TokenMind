---
name: frontend-webapp-builder
description: Build polished, production-minded frontend pages and web app surfaces with strong visual direction, reusable structure, responsive behavior, and engineering discipline. Use when asked to create or upgrade landing pages, dashboards, admin panels, settings pages, marketing sites, feature flows, or "advanced frontend" / "engineering-grade frontend" experiences, especially in React + TypeScript projects.
---

# Frontend Webapp Builder

## Overview

Build frontend work that feels intentional instead of generic. Favor clear information hierarchy, strong component boundaries, responsive layouts, and production-ready states over quick mockup-level output.

## Workflow

Follow this sequence unless the user explicitly asks for something narrower:

1. Inspect the existing app before designing anything.
2. Infer the active stack, styling approach, routing pattern, and state boundaries.
3. Pick a page concept that fits the product instead of dropping in a generic dashboard.
4. Implement structure first: page shell, sections, navigation, content hierarchy.
5. Add realistic states: loading, empty, error, hover, disabled, selected, narrow screens.
6. Polish spacing, typography, color, and motion only after the structure is stable.
7. Run the project checks that are available and fix regressions before finishing.

## Decision Rules

- Preserve the established design language when the repository already has one.
- Introduce a stronger visual direction only when the current surface is weak, missing, or explicitly being redesigned.
- Prefer the project's existing stack over personal preference.
- Default to small reusable components when a page has repeated UI patterns.
- Keep page-specific decisions near the page; move shared primitives only when reuse is clear.
- Treat loading, empty, and error states as part of the deliverable, not follow-up work.
- Avoid placeholder lorem ipsum and unrealistic fake metrics when the page can use domain-shaped copy.

## Project Defaults

When working in this repository, read [references/project-defaults.md](references/project-defaults.md) first. It captures the current frontend stack and the expected file placement.

For implementation patterns and delivery steps, read:

- [references/page-delivery-playbook.md](references/page-delivery-playbook.md) for the end-to-end build workflow.
- [references/quality-checklist.md](references/quality-checklist.md) for engineering and UX verification.

## Output Standard

Aim for work that another engineer can continue without redoing the page:

- Keep components readable and named after product concepts.
- Use design tokens or CSS variables when introducing a visual system.
- Avoid giant JSX blocks when sections can be extracted cleanly.
- Verify responsive behavior instead of assuming it.
- Leave the page in a shippable state, not a static mock.
