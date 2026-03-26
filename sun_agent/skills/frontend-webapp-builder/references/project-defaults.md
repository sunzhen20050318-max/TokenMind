# Project Defaults

Read this file first when the task is inside this repository.

## Current Stack

- Frontend runtime: React 18
- Build tool: Vite
- Language: TypeScript
- State management present in repo: Zustand
- Existing markdown rendering dependency: `react-markdown`

## Current Frontend Layout

The repository uses a dedicated frontend app under `frontend/`.

- App entry: `frontend/src/main.tsx`
- Root app shell: `frontend/src/App.tsx`
- Shared UI: `frontend/src/components/`
- Page-level screens: `frontend/src/pages/`
- Hooks: `frontend/src/hooks/`
- Services: `frontend/src/services/`
- Stores: `frontend/src/stores/`
- Shared types: `frontend/src/types/`

## Implementation Bias

- Prefer React function components in TypeScript.
- Follow the existing folder layout before inventing a new one.
- Put route- or screen-level composition in `pages/`.
- Put reusable UI pieces in `components/`.
- Put data-fetching or environment interactions in `services/` or hooks, not inline in large page components.
- Reuse Zustand stores when state must be shared across screens or layout regions.

## Styling Guidance

The current codebase already includes global CSS and also uses inline style objects in some places.

- Respect existing patterns when making small changes.
- If building a larger new surface, introduce a more structured styling approach inside the feature rather than expanding ad hoc inline styles everywhere.
- Prefer CSS variables for color, spacing, radius, and shadows when a new visual system is introduced.
- Keep tokens local and obvious if there is no app-wide design token layer yet.

## Sensible Defaults For New Work

If the user does not specify otherwise:

- Build for desktop and mobile.
- Use semantic HTML where possible.
- Add empty and loading states.
- Make repeated blocks into components.
- Keep fake content product-shaped and plausible.

## Do Not Do This

- Do not replace the whole app shell unless the user asks for a redesign.
- Do not introduce a new framework or CSS system without a strong reason.
- Do not scatter one-off styles across many files when one page-scoped stylesheet or token set would be clearer.
