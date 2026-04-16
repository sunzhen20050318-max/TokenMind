# Claude-Inspired Home and Conversation Shell Redesign

## Summary

This spec reshapes the main `SUN-AGENT` frontend shell so the product feels closer to the `claude.ai` references the user provided, while preserving `SUN-AGENT`'s existing product structure and capabilities.

This redesign replaces the previously approved Manus-style homepage direction for the main chat shell. The Manus-inspired work remains useful as a visual refinement baseline for modal chrome and general density, but the main shell should now follow a calmer Claude-like interaction model.

The redesign covers three connected surfaces:

1. the persistent left sidebar
2. the idle / pre-conversation homepage
3. the active conversation layout after messages exist

The goal is not to reproduce Claude verbatim. The goal is to adopt its layout grammar:

- a quieter, narrower left rail
- a very spacious, centered empty state
- a wide, low-profile composer centered on the page before a conversation starts
- lightweight suggestion pills below the composer
- a stable, fixed reading column once a conversation begins
- restrained conversation chrome with the content column doing most of the visual work

At the same time, `SUN-AGENT` keeps its own:

- product naming
- sidebar destinations
- task / memory / file / settings surfaces
- execution timeline
- current avatar / mark behavior during chat

## Goals

- Make the idle homepage feel closer to Claude than Manus
- Keep the sidebar content specific to `SUN-AGENT`
- Reduce the sense of dashboard chrome and increase calm whitespace
- Center the composer and preset prompt chips before a conversation begins
- Shift into a fixed-width reading layout after a conversation starts
- Make user and assistant bubbles obey one consistent message column width system
- Keep the execution timeline and force it to follow the same width as the message column
- Preserve existing functionality and backend behavior

## Non-Goals

- Do not copy Claude branding, labels, or icons
- Do not move product features into a Claude-like bottom icon strip
- Do not remove the execution timeline
- Do not redesign modal internals in this phase, except where small shell alignment is required
- Do not change backend APIs
- Do not change the current logo / mark placement rule during chat just to mimic Claude

## Current Context

The frontend currently sits between two visual directions:

- the shell and settings were recently being pushed toward a Manus-like structure
- the user now wants the main homepage and active conversation layout to feel closer to Claude

The existing implementation already has useful foundations:

- a persistent sidebar
- a launch-state versus active-chat-state split
- a bottom-docking composer transition
- lightweight chips below the composer
- a working execution timeline
- modal surfaces for memory, tasks, storage, and settings

What is not yet aligned with the Claude reference:

- the launch state still feels too productized and too "hero section" heavy
- the composer is larger and more elevated than Claude's
- conversation content is still not constrained to a clear, fixed reading column
- message bubbles and execution chain do not share one obvious layout system
- the sidebar still reads more like an app control panel than a quiet left rail

## Proposed Approaches

### Option A: Idle-State Only Redesign

Only change the no-conversation homepage to feel Claude-like, and leave the active conversation view mostly as-is.

Pros:

- smallest implementation risk
- quickest visual improvement

Cons:

- creates a mismatch between idle and active states
- would still leave the reading layout less polished than the reference

### Option B: Homepage + Conversation Column Redesign

Redesign both the idle homepage and the active conversation column so they share one Claude-like layout language, while keeping the `SUN-AGENT` sidebar content and timeline behavior.

Pros:

- most faithful to the user's request
- gives the product one coherent shell language
- fixes the bubble width and execution-chain width concerns together

Cons:

- touches the main chat layout more deeply
- requires careful handling of composer and timeline positioning

### Option C: Full Claude-Style Clone

Push the sidebar, homepage, and chat surfaces into a very close Claude copy.

Pros:

- strongest immediate resemblance

Cons:

- too derivative
- risks breaking product identity
- would likely force unnecessary structure changes that do not fit `SUN-AGENT`

### Recommendation

Use **Option B**.

It delivers the layout behavior the user actually wants:

- Claude-like idle state
- Claude-like active reading column
- fixed bubble width
- execution timeline aligned to that same column

without flattening `SUN-AGENT` into a clone.

## Information Architecture

### Sidebar

The sidebar remains persistent, but it should become quieter and more Claude-like in tone.

It should keep `SUN-AGENT`'s own product structure rather than Claude's literal menu labels.

Recommended order:

1. brand row
2. primary action: `新建对话`
3. lightweight core destinations
4. conversation list
5. bottom anchored settings entry

The main destinations remain:

- `对话`
- `记忆中心`
- `定时任务`
- `文件中心`

The conversation list remains always visible.

### Idle Homepage

Before the current session contains visible messages, the main stage becomes a spacious Claude-like empty state.

Structure:

1. one greeting / prompt line centered on the page
2. one wide, low-profile composer directly below it
3. a row of light suggestion pills below the composer

The greeting should feel calmer than the current "hero" treatment. It should not look like a marketing headline. It should feel like a quiet invitation to begin.

### Active Conversation View

Once the current session contains messages:

- the greeting and idle-only copy disappear
- the composer settles into the bottom region
- the chat thread becomes a centered fixed reading column

The main stage should feel much more editorial and much less dashboard-like.

## Layout Design

### Sidebar Tone

Compared with the current Manus-like version, the sidebar should move closer to Claude in these ways:

- less chunky primary rows
- slightly narrower feel
- quieter text hierarchy
- less "card button" feeling
- more list-like than panel-like

The top `新建对话` action should remain obvious, but it should not look like a loud call-to-action block.

The conversation list should become denser and more like a text history list.

### Idle-State Composition

The idle-state stage should be built around a single centered column.

Recommended visual proportions:

- greeting width: medium, not too wide
- composer width: wide enough to dominate the center, but shorter in height than today
- suggestion pills: compact and subtle

The visual center of gravity should be:

- lower than a traditional hero section
- higher than a bottom-docked chat layout
- almost exactly where Claude places the input stack

### Greeting

The greeting should be simpler than the current title/copy pair.

It should read more like:

- one single line
- a soft serif-like or elegant display feeling if the existing typography allows it
- enough size to anchor the stage, but not "product marketing" scale

The current extra explanatory paragraph should be removed from the idle center or reduced heavily. Claude's reference works because it is visually sparse.

### Composer

The composer should move toward a Claude-like shape:

- lower height
- broader width
- softer border and lower contrast fill
- more integrated control row

It should still preserve current capabilities:

- file upload
- stop generation
- text input

But the chrome should feel more minimal and less "tool dock."

### Suggestion Pills

The current feature chips can remain as concept shortcuts, but they should become lighter and smaller.

They should read as:

- suggestion prompts
- not feature cards
- not dashboard modules

The current categories are acceptable, but the visual treatment should be closer to Claude's understated pill row.

## Active Conversation Layout

### Reading Column

The active conversation area should move to a fixed content column centered in the available stage.

This is the key structural change.

The column should control:

- assistant message width
- user bubble width
- code blocks
- execution timeline width
- bottom composer width

That means the system stops feeling like each element chooses its own width.

### User and Assistant Bubble Rules

Messages should use one unified content grid:

- the overall conversation column is fixed-width and centered
- user bubbles stay aligned to the right within that column
- assistant responses stay aligned to the left / body flow within that same column
- neither side should expand arbitrarily beyond the column system

The user explicitly asked for the user and assistant bubbles to have fixed width behavior. The intended interpretation is:

- both participate in the same column width system
- the column width is stable
- the bubbles do not feel randomly narrow on some turns and very wide on others

This should be achieved through a shared message lane and bounded bubble max-widths derived from that lane.

### Execution Timeline

The execution timeline remains in the product.

New rule:

- it should always align to the same width as the message lane it belongs to

If a user turn has a timeline below it, the timeline should feel like part of the same conversation block, not a separate panel floating at a different width.

This is a major acceptance criterion for the redesign.

### Composer in Active State

The bottom composer should remain docked, but visually it should feel closer to Claude:

- broad and centered
- calmer contrast
- lower profile than the idle-state composer
- attached to the same reading system as the messages above

The transition from idle to active should still be natural and restrained.

## Motion and Transitions

Motion should stay subtle.

Use:

- opacity fades
- translate adjustments
- spacing interpolation
- mild dock transition for the composer

Avoid:

- heroic movement
- springy transformations
- exaggerated chip motion

The idle state should feel like it quietly resolves into the conversation state.

## Typography and Tone

The redesign should become calmer and more refined than the current Manus-like version.

Directional rules:

- darker, softer charcoal background
- lower contrast chrome
- more emphasis on text than on panels
- more whitespace around the central input stack
- less uppercase utility noise

The visual tone should be:

- quiet
- premium
- focused
- literary rather than dashboard-like

## Behavior Rules

### When No Visible Messages Exist

Show:

- Claude-like centered greeting
- centered composer
- suggestion pills under the composer

Hide:

- active conversation thread chrome

### When Visible Messages Exist

Show:

- centered reading column
- fixed-width message system
- fixed-width execution chain
- bottom composer

Hide:

- idle-only greeting
- idle-only suggestion presentation

### Sidebar Behavior

The sidebar remains persistent in both states and should not switch into a separate mode.

## Responsive Behavior

Desktop is the primary target.

On narrower screens:

- the centered column should shrink gracefully
- suggestion pills should wrap cleanly
- composer controls should compress without breaking upload / stop / send behavior
- the sidebar may keep the current responsive width adjustments already in place

No mobile-first shell redesign is required in this phase.

## Data Flow and Logic Impact

This redesign remains frontend-only in architecture.

Expected logic changes:

- use current visible-message presence as the idle/active switch
- constrain timeline rendering to the same layout lane as its parent message
- keep existing session creation and modal logic intact

No backend route or data contract changes are required.

## Error Handling and State Coverage

The redesign must still clearly support:

- empty conversation state
- active conversation state
- streaming state
- upload-in-progress state
- approval modal flow
- execution timeline rendering
- no conversations found in sidebar search

The quieter layout must not hide important system states.

## Acceptance Criteria

The redesign is complete when:

- the left sidebar still contains `SUN-AGENT`'s own destinations, but feels closer to Claude in tone and density
- the idle homepage is no longer a Manus-like launchpad and instead feels closer to Claude's centered greeting + composer stack
- the idle composer is centered and visually lower-profile
- lightweight prompt pills appear below the composer
- after conversation begins, the page resolves into a centered fixed-width reading column
- user and assistant messages follow one stable width system
- the execution timeline always matches the width of the message lane it belongs to
- the bottom composer aligns visually with that same conversation column
- existing capabilities remain intact

## Testing Strategy

Frontend verification should include:

- `npm run build`
- idle-state visual check
- active conversation visual check
- sidebar density and list behavior
- timeline alignment under a user turn
- long assistant response rendering with code blocks
- upload controls and stop button in the redesigned composer

Manual review should specifically check:

- that the idle state now reads closer to Claude than Manus
- that the active state feels editorial and centered
- that the execution timeline width issue is visibly resolved
