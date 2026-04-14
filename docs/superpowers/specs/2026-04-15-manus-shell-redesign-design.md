# Manus-Inspired Shell Redesign

## Summary

This spec redesigns the frontend shell of `SUN-AGENT` to feel closer to the Manus interface style shown in the user-provided references, while preserving the product's existing capabilities and local-first workflow.

The redesign covers three connected surfaces:

1. The persistent left sidebar on the main app shell
2. The empty-state / pre-conversation homepage composition
3. The settings center visual structure and information hierarchy

The goal is not a pixel-copy of Manus. The goal is to adopt the same interaction grammar:

- a narrow, always-visible dark sidebar
- one dominant primary action at the top
- a small set of clearly grouped persistent navigation entries
- a centered composition before conversation begins
- a natural transition from "launch state" into "chat state"
- a settings experience organized as a left navigation rail plus right content pane

The redesign keeps `SUN-AGENT`'s existing features and terminology where practical, while reducing current visual fragmentation and making the app feel more intentional and product-shaped.

## Goals

- Make the sidebar structure feel closer to Manus without removing `SUN-AGENT` functionality
- Keep major product areas visible and easy to reach
- Turn the homepage empty state into a centered launchpad instead of a sparse blank screen
- Move the input box to the center before a conversation begins, then transition it toward the bottom once chatting starts
- Redesign settings to feel calmer, clearer, and more premium, using a Manus-like navigation/content split
- Preserve the current black/white/gray visual language of the product

## Non-Goals

- Do not clone Manus branding, copy, or product semantics one-to-one
- Do not change backend APIs or core feature behavior for settings, sessions, memory, tasks, or storage
- Do not hide the app's existing major surfaces behind deep menus
- Do not introduce a new bottom utility toolbar like Manus
- Do not redesign every modal in this phase; only the main shell and settings are in scope

## Current Context

The current frontend already includes:

- a persistent sidebar
- a top header
- a chat surface with empty state and conversation state
- dedicated modals for memory, settings, tasks, and storage

The current shell works functionally but feels more like a collection of product additions than a unified layout system. The sidebar uses stacked utility buttons and a separate session list, the homepage empty state is visually under-composed, and the settings center is feature-rich but still reads more like a parameter dashboard than a calm system panel.

Recent work has added:

- memory center
- file center
- scheduled tasks
- MCP management
- improved tool timeline and markdown rendering

This redesign should unify those features under a clearer shell rather than replacing them.

## Proposed Approach

### Option A: Visual Reskin Only

Keep the current sidebar and settings structure but change colors, spacing, and panel styles to resemble Manus.

Pros:

- lowest implementation risk
- minimal layout regression risk

Cons:

- would feel like a skin rather than a structural improvement
- would not achieve the requested Manus-style entry hierarchy

### Option B: Manus-Inspired Shell Reorganization

Reorganize the sidebar, empty state, and settings structure to follow Manus-style layout logic while preserving `SUN-AGENT` feature surfaces and labels.

Pros:

- delivers the biggest improvement in perceived product quality
- matches the user's request closely
- preserves current functionality

Cons:

- touches multiple frontend layout files
- requires careful handling of state transitions between idle and active conversation modes

### Option C: Full App-Shell Overhaul

Rebuild the entire main app frame and related modals around a new product shell, including deeper changes to header, navigation, and content routing.

Pros:

- highest visual transformation

Cons:

- too large for this phase
- higher regression risk
- would likely over-disrupt already-working product flows

### Recommendation

Use **Option B**.

It gives the product the Manus-like structure the user wants without forcing a full application rewrite or destabilizing the current feature set.

## Information Architecture

### Main Shell

The left sidebar becomes the stable shell anchor and follows this order:

1. Brand area
2. Primary action button: `New Conversation`
3. Persistent primary entry group
4. Conversation list section
5. Bottom anchored `Settings`

### Primary Entry Group

The sidebar's main entries become:

- `Chat`
- `Memory Center`
- `Scheduled Tasks`
- `File Center`

These entries remain visible at all times. They are not tab replacements for the conversation list.

### Conversation List

Conversation history remains permanently visible in the sidebar below the primary entry group. This follows the Manus pattern more closely: top-level actions and the list area coexist rather than replace one another.

### Settings Entry

`Settings` moves to the bottom anchor area of the sidebar. It remains an obvious entry, but stops competing visually with the primary workflow actions.

## Layout Design

### Sidebar

The sidebar should shift toward a Manus-like composition:

- narrower and denser than the current sidebar
- stronger top brand block
- one dominant top button
- lighter icon + label rows for persistent entries
- section labels for the conversation list area
- a quieter, anchored system action at the bottom

Stylistic rules:

- dark charcoal background, not pure black
- subtle border separation from the main content
- softer but tighter radius language
- less button-stack feeling
- stronger text hierarchy between primary actions, section labels, and conversation rows

The bottom tools row from Manus is explicitly out of scope and will not be reproduced.

### Header

The existing top header should visually step back. In the Manus references, the center of the page is the primary focus, not the header chrome.

The header may remain functionally present, but should become quieter:

- smaller visual weight
- less border emphasis
- less dense utility feel

### Main Content: Idle State

Before a conversation begins, the main content becomes a centered launch state.

Composition:

- central title
- centered input area
- lightweight preset capability chips under the input

The current preset capability entries should remain, but be restyled from heavier feature blocks into lighter Manus-like chips or rounded prompt shortcuts.

The launch state should feel vertically centered but slightly elevated, with generous negative space.

### Main Content: Active Conversation State

Once the user sends a message or a conversation already contains messages:

- the centered launch composition fades or collapses away
- the input area transitions toward the bottom
- the chat history becomes the dominant content region

This should feel like a natural state transition in one layout, not a hard route change.

### Input Transition

The input box should be the anchor of the transition:

- idle state: centered
- active state: bottom aligned

The motion should be smooth and restrained, relying on transform, opacity, spacing, and layout interpolation rather than dramatic animation.

## Settings Center Design

The settings center should keep its current functional grouping but adopt a clearer Manus-like structure:

- large dark modal panel
- left navigation rail
- right content pane
- calmer content density
- clearer section headers
- reduced visual noise

### Left Navigation

The left side becomes a real navigation rail with the existing main sections:

- `Models`
- `Agent`
- `Tools`
- `MCP`
- `Runtime`

These remain the core sections, but the visual treatment should shift closer to Manus:

- compact rows
- clearer active state
- less card-like navigation treatment

### Right Content Pane

The content pane should focus on one section at a time, with:

- stronger section titles
- shorter supporting copy
- more consistent field group spacing
- calmer panels and rows

The intention is to move from "dense control panel" toward "system settings surface."

### Models and MCP

These sections keep their existing capabilities, but the visual treatment becomes more list-driven and structured:

- better separation between overview and editing flows
- less oversized card weight
- more consistent form rhythm

The provider editor drawer can remain if it still supports the cleanest editing flow.

## Interaction Rules

### Entry Behavior

- `New Conversation` creates a new session and returns focus to the main content input
- `Chat` focuses the primary chat workflow and conversation list
- `Memory Center` opens its modal
- `Scheduled Tasks` opens its modal
- `File Center` opens its modal
- `Settings` opens the settings modal from the bottom anchor area

### Empty State Logic

If the current session has no messages:

- show the launch-state layout
- keep the input centered
- keep preset prompt chips visible

If the session has messages:

- show normal chat state
- move input to the bottom
- hide or collapse the launch-only helper content

### Conversation List Presence

Conversation history stays visible in the sidebar in both idle and active states.

## Motion and Visual Tone

Motion should support clarity rather than novelty.

Use:

- input position interpolation between idle and active states
- subtle opacity and translate transitions for hero text and preset chips
- restrained hover states in sidebar and settings navigation

Avoid:

- springy or playful motion
- bright accent colors
- heavy glassmorphism
- gradients that break the current black/gray product language

The final tone should read as:

- calm
- premium
- dense enough to feel serious
- minimal without feeling empty

## Responsive Behavior

Desktop is the priority, but narrow screens should still remain coherent.

Rules:

- sidebar can collapse earlier on small widths if needed, but the default desktop layout should stay Manus-like
- centered input width should shrink gracefully on smaller screens
- preset chips should wrap cleanly
- settings modal should compress into a narrower two-pane or stacked layout depending on available width

## Data Flow and Logic Impact

This redesign is intended to be primarily frontend-only.

Expected logic impact:

- derive idle vs active conversation from current session message count
- keep current modal open/close patterns for memory, tasks, storage, and settings
- preserve current session creation, search, rename, and delete behavior unless layout simplification requires minor UI adjustments

No backend API changes are required for this redesign.

## Error Handling and States

The redesigned shell must preserve and visually support these states:

- no session selected
- newly created empty session
- no conversations found in search
- settings loading / error notice
- empty conversation list
- modal loading and refresh states

The empty launch state should not appear broken if no providers are configured; it should remain calm and usable.

## Implementation Boundaries

This phase includes:

- sidebar structural redesign
- homepage idle/active composition redesign
- settings modal structural redesign

This phase excludes:

- redesign of tasks, memory, or storage internals beyond what is required for consistent modal framing
- backend API changes
- major feature rewording
- Manus bottom utility bar

## Testing Strategy

Frontend verification should include:

- `npm run build`
- manual verification of desktop layout
- idle-state to active-state transition
- new session creation
- opening memory, tasks, storage, and settings from the redesigned shell
- settings navigation and provider editor flow

Visual checks should confirm:

- sidebar remains stable with many conversations
- launch-state input and prompt chips stay centered before first message
- input transitions cleanly to bottom after conversation begins
- settings modal feels structurally coherent and fully scrollable

## Acceptance Criteria

The redesign is complete when:

- the sidebar visibly follows the Manus-like structure requested by the user
- `New Conversation` is the dominant top action
- primary entries and conversation list are both always visible
- `Settings` is bottom-anchored and remains a clear entry
- the homepage idle state uses a centered input with preset prompts below it
- starting a conversation transitions the input toward the bottom naturally
- the settings center adopts a Manus-like left-nav/right-content structure
- existing functionality remains available without backend changes
