# TokenMind Project Entry Refinement Design

## Summary

This spec refines the already-approved `项目` feature so the in-project experience feels closer to the ChatGPT reference pattern.

The current implementation introduces a dedicated project home page, but its layout is still too much like a generic empty-state workspace. The next iteration should make project entry feel like a lightweight project-scoped chat launcher:

1. the project name is the primary header
2. a chat input appears immediately below the project name
3. the project's conversation list appears directly below that input
4. sending the first message creates a new project session and immediately opens that session's normal chat page

At the same time, the sidebar's `项目` dropdown should stop looking like another stack of full-size nav buttons. It should read visually as a project directory with clearer hierarchy.

## Goals

- Make entering a project feel like entering a project-scoped chat launcher
- Put the first-action input directly on the project entry page
- Keep project conversations visible directly under that input
- Keep the existing rule that project chats do not appear in the global recent list
- Make the sidebar project area visually distinct from first-level navigation
- Create a clearer hierarchy: app navigation -> project list -> project conversations

## Non-Goals

- Do not change backend project/session data rules
- Do not change how project sessions are stored
- Do not turn the project entry page into a full embedded chat timeline
- Do not add nested project folders
- Do not add project-specific settings, files, or knowledge scopes in this iteration

## Product Direction

Projects remain containers, not chats.

That means the project entry page is not itself a conversation. It is the surface where the user:

- recognizes which project they are inside
- starts a new project-scoped chat
- chooses from existing chats already inside that project

The actual chat experience still belongs to a specific session page.

## Primary User Flow

### Flow 1: Enter a project

1. user clicks a project name in the sidebar
2. the main area opens the project entry page
3. the top of the page shows the project name
4. a composer is visible immediately below
5. below the composer, the project's existing conversations are listed

### Flow 2: Start a new conversation from the project page

1. user types a message into the project page composer
2. the frontend creates a new session with that project's `project_id`
3. the first message is sent into that new session
4. the app immediately navigates into the full chat page for that new project session

### Flow 3: Return to the project page later

1. user clicks the project name again in the sidebar
2. the app opens the project entry page
3. the composer is ready for a new project-scoped chat
4. the existing project conversation list is still visible below it

## Project Entry Page Layout

The project entry page should no longer use a large boxed empty-state panel as the main visual element.

### Header

The top region should contain:

- a compact project icon
- the project name as the main title
- optional very light supporting copy only if needed

This header should be visually lighter and tighter than the current generic page shell.

### Composer

Immediately below the header, render a wide chat composer styled as a project-scoped entry input.

Requirements:

- use the same core composer language as chat input so the interaction is familiar
- visually frame it as the main action on the page
- placeholder text should indicate the user is starting a chat inside this project
- no detached `新聊天` hero button should compete with the composer

### Conversation List

Directly below the composer, render the conversations belonging to this project.

Each list item should include:

- title
- recent preview text when available
- updated date

The list should feel close to the screenshot reference: lighter rows, denser spacing, and clearly secondary to the composer.

### Empty State

When the project has no conversations:

- keep the header
- keep the composer
- replace the large empty card with a much lighter inline empty hint below the composer

The page should still feel immediately actionable, not empty.

## Interaction Rules

### Composer Submit

Submitting from the project entry composer should:

1. create a new project-scoped session
2. send the first message into that session
3. navigate directly into the normal chat view for that session

This should follow option `A` approved by the user.

### Clicking an Existing Project Conversation

Clicking a row in the project conversation list should open that session's normal chat page immediately.

### Returning From a Project Chat

The sidebar project name remains the way to return to the project entry page.

The project entry page is therefore the project's launcher surface, while the session page is the conversation surface.

## Sidebar Refinement

The current project dropdown looks too similar to first-level nav buttons. This makes the hierarchy unclear.

### Hierarchy Model

The sidebar should read as:

1. first-level app actions and destinations
2. second-level project directory
3. third-level project-local conversations only after entering a project

### Project Section Styling

The `项目` section should be rendered more like a directory tree than a nav stack.

Requirements:

- `新项目` should be a light secondary action, not a large primary-style button
- project names should be more compact than first-level nav items
- project rows should have clearer indentation and tighter spacing
- selected project row should use a distinct active treatment
- project rows should not reuse the exact shape, density, and border weight of normal nav buttons

### Visual Cues

Use a combination of:

- smaller row height
- subtler borders
- lighter hover treatment
- folder/project icon
- active left accent or active background

The result should make projects feel like a contained list, not repeated primary buttons.

## Visual Direction

This refinement should preserve the app's existing dark shell, but improve hierarchy.

### First-Level Navigation

Keep the current stronger button treatment for:

- `新建对话`
- `知识库`
- settings entry

### Second-Level Project Directory

Use a lighter, denser treatment for project names:

- smaller vertical rhythm
- less visual weight
- more directory-like grouping

### Project Entry Surface

The main area should feel more intentional and less empty:

- tighter spacing above the composer
- no oversized dead zone
- list visually anchored to the composer

## Data and Architecture Impact

No backend data model change is needed for this refinement.

This is primarily a frontend information-architecture and interaction refinement built on top of the existing project/session model.

Expected code impact:

- `ProjectHome` becomes a project entry launcher surface
- project entry composer submits into a freshly created project session
- sidebar project section gets a distinct visual language

## Testing Strategy

### Manual Product Checks

Required checks:

1. open a project and verify the project name shows at the top
2. verify a chat input is visible immediately on the project page
3. type and send a message from that input
4. verify a new project session is created
5. verify the app immediately enters that new session chat page
6. return to the project page and verify the new conversation appears in the list
7. verify project dropdown styling is visually distinct from first-level nav buttons

### Regression Checks

Also confirm:

1. global recent list still excludes project chats
2. opening an existing project conversation still shows full history
3. creating a normal non-project chat still works unchanged

## Recommendation

Refine projects into a two-surface model:

- project entry page for launching and browsing project chats
- normal session page for actual chat execution

Do not embed a full persistent chat timeline into the project entry page.
Do not keep the current oversized empty-state panel.
Do not style project names like first-level navigation buttons.
