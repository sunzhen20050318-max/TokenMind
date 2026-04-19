# Quality Checklist

Use this checklist before considering the frontend task complete.

## Product And UX

- Does the page make its purpose obvious immediately?
- Is there a clear primary action?
- Are labels concrete instead of generic filler?
- Do loading, empty, and error states exist where needed?
- Does the layout still make sense on narrow screens?

## Visual Design

- Is there a coherent visual direction instead of default framework styling?
- Are spacing and typography consistent?
- Are color choices intentional and readable?
- Are cards, panels, and separators visually balanced?
- Is motion minimal but meaningful?

## Engineering

- Does the implementation follow the repository's stack and structure?
- Are repeated UI patterns extracted appropriately?
- Is business or async logic kept out of oversized presentational components?
- Are types explicit where they improve safety?
- Are new abstractions justified by actual reuse or clarity?

## Accessibility

- Are buttons and inputs semantically correct?
- Are interactive elements keyboard reachable?
- Is contrast acceptable for primary text and controls?
- Do icons with meaning have text labels or accessible names?

## Finish Quality

- Did the build or available checks pass?
- Did you avoid unnecessary framework or dependency changes?
- Did you leave behind any obvious TODO placeholders or fake scaffolding that should be removed?
- Can another engineer understand where to continue from the current file structure?
