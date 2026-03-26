# Page Delivery Playbook

Use this workflow when building a new frontend page or substantially upgrading an existing one.

## 1. Build Context

Inspect the surrounding product before coding:

- What is the page for?
- Who uses it?
- What is the core action?
- Which information must be immediately visible?
- Which existing components or shells should be reused?

If the repository already has nearby pages, align with them before adding new patterns.

## 2. Pick A Visual Direction

Choose a specific direction instead of defaulting to generic SaaS UI.

Examples:

- Operational command center
- Editorial product surface
- Dense admin workspace
- Calm settings and configuration view
- High-contrast marketing landing page

Lock in:

- Typography tone
- Density
- Card and panel treatment
- Accent color strategy
- Background treatment
- Motion level

## 3. Design The Information Hierarchy

Start with sections, not decoration.

Typical order:

1. Primary page heading and context
2. Primary action area
3. High-value summaries or status
4. Detailed panels, tables, feeds, or forms
5. Secondary controls and metadata

At this stage, ask whether the user can understand the page in five seconds without reading every word.

## 4. Implement Reusable Structure

Split when reuse or readability benefits are obvious:

- Page shell
- Hero or header block
- Summary cards
- Tables or lists
- Filter bars
- Detail drawers or side panels
- Empty/loading/error state components

Do not split so aggressively that the feature becomes impossible to follow.

## 5. Fill Out Product States

Every serious page should account for:

- Loading
- Empty
- Error
- Partial data
- Overflowing content
- Narrow screens
- Hover/focus/active states for interactive controls

If the user asked for a form or workflow, also include:

- Validation messaging
- Disabled submit state
- Success state

## 6. Polish Deliberately

Refine only after the structure works:

- Tighten spacing rhythm
- Normalize border radii and shadows
- Improve text contrast
- Align visual weight across sections
- Add restrained motion where it clarifies interaction

Use boldness with discipline. Distinctive is good; chaotic is not.

## 7. Verify Like An Engineer

Before finishing:

- Run available build or test commands
- Check for obvious TypeScript issues
- Scan for layout breakage in the code structure
- Ensure component APIs are understandable
- Remove dead scaffolding

The goal is not just a nice screenshot. The goal is code another engineer can safely extend.
