# Manus Shell Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the main frontend shell so the sidebar, idle homepage, active chat transition, and settings modal feel Manus-inspired while preserving `SUN-AGENT` functionality.

**Architecture:** Keep the existing React + Zustand app structure and modal flows, but refactor the shell into a clearer layout system. The work is split into a sidebar/navigation task, a launch-state/chat-state task, a settings-shell task, and a final polish/verification pass so each change can be tested and reviewed independently.

**Tech Stack:** React 18, TypeScript, Vite, CSS, Zustand

---

## File Map

- Modify: `D:\project\sun-agent\frontend\src\App.tsx`
  - Drive shell-level state and make room for a Manus-style persistent sidebar plus content stage.
- Modify: `D:\project\sun-agent\frontend\src\app.css`
  - Establish shell proportions, spacing, and content-stage rules.
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`
  - Reorganize sidebar into brand block, primary action, primary entries, conversation section, and bottom settings anchor.
- Create: `D:\project\sun-agent\frontend\src\components\Layout\sidebar.css`
  - Hold the new sidebar visual system instead of piling more inline styles into `Sidebar.tsx`.
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Header.tsx`
  - Reduce visual weight and align the header with the new shell.
- Create: `D:\project\sun-agent\frontend\src\components\Layout\header.css`
  - Move the header toward a calmer Manus-like tone.
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\ChatWindow.tsx`
  - Introduce the Manus-like launch state and active chat state transition.
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\chatWindow.css`
  - Replace the current empty-state card grid layout with a centered launchpad and transition rules.
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx`
  - Add shell-aware class hooks so the composer can render differently in centered and bottom-docked states.
- Create: `D:\project\sun-agent\frontend\src\components\Chat\inputArea.css`
  - Define Manus-inspired composer chrome, chip layout, and state transitions.
- Modify: `D:\project\sun-agent\frontend\src\pages\Settings.tsx`
  - Reshape the settings modal into a stronger left-nav/right-content structure without losing current capabilities.
- Modify: `D:\project\sun-agent\frontend\src\pages\settings.css`
  - Retone spacing, navigation, panel density, and section presentation to match the new shell.
- Modify: `D:\project\sun-agent\frontend\src\pages\Memory.tsx`
- Modify: `D:\project\sun-agent\frontend\src\pages\Tasks.tsx`
- Modify: `D:\project\sun-agent\frontend\src\pages\Storage.tsx`
  - Ensure modal headers, close affordances, and shell framing remain visually coherent after the settings redesign.

## Task 1: Build the Sidebar Shell

**Files:**
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`
- Create: `D:\project\sun-agent\frontend\src\components\Layout\sidebar.css`
- Modify: `D:\project\sun-agent\frontend\src\App.tsx`
- Modify: `D:\project\sun-agent\frontend\src\app.css`
- Test: `D:\project\sun-agent\frontend\package.json`

- [ ] **Step 1: Add the stylesheet import and structural class hooks first**

```tsx
// D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx
import './sidebar.css';

const PRIMARY_NAV = [
  { id: 'chat', label: '对话', icon: 'chat' },
  { id: 'memory', label: '记忆中心', icon: 'memory' },
  { id: 'tasks', label: '定时任务', icon: 'tasks' },
  { id: 'storage', label: '文件中心', icon: 'storage' },
] as const;
```

- [ ] **Step 2: Run the frontend build to verify the new stylesheet dependency fails before the CSS file exists**

Run: `npm run build`

Expected: FAIL with an import resolution error for `./sidebar.css`

- [ ] **Step 3: Add the minimal sidebar CSS file and shell lane rules**

```css
/* D:\project\sun-agent\frontend\src\components\Layout\sidebar.css */
.shell-sidebar {
  width: 300px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #18181a;
  border-right: 1px solid #26262b;
}

.shell-sidebar__brand,
.shell-sidebar__footer {
  padding: 18px 16px;
}

.shell-sidebar__nav,
.shell-sidebar__sessions {
  padding: 0 10px;
}
```

- [ ] **Step 4: Rewrite `Sidebar.tsx` into the Manus-like structure**

```tsx
return (
  <aside className="shell-sidebar">
    <div className="shell-sidebar__brand">{/* brand row */}</div>
    <div className="shell-sidebar__primary">{/* new conversation */}</div>
    <nav className="shell-sidebar__nav">{/* primary entries */}</nav>
    <section className="shell-sidebar__sessions">{/* search + session list */}</section>
    <div className="shell-sidebar__footer">{/* bottom settings anchor */}</div>
  </aside>
);
```

- [ ] **Step 5: Update `App.tsx` and `app.css` so the shell expects the new sidebar proportions**

```css
/* D:\project\sun-agent\frontend\src\app.css */
.app-main {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  flex: 1;
  min-height: 0;
}

.app-main__content {
  min-width: 0;
  min-height: 0;
  background: #1f1f22;
}
```

- [ ] **Step 6: Run the frontend build to verify the sidebar shell compiles**

Run: `npm run build`

Expected: PASS

- [ ] **Step 7: Commit the sidebar shell pass**

```bash
git add frontend/src/components/Layout/Sidebar.tsx frontend/src/components/Layout/sidebar.css frontend/src/App.tsx frontend/src/app.css
git commit -m "feat: reshape app shell sidebar"
```

## Task 2: Rebuild the Launch State and Composer Transition

**Files:**
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\ChatWindow.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\chatWindow.css`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx`
- Create: `D:\project\sun-agent\frontend\src\components\Chat\inputArea.css`
- Test: `D:\project\sun-agent\frontend\package.json`

- [ ] **Step 1: Add a shell-state flag to `ChatWindow.tsx` and wire the future composer mode**

```tsx
const hasConversation = visibleMessages.length > 0;
const shellMode = hasConversation ? 'active' : 'launch';
```

- [ ] **Step 2: Run the frontend build to confirm the new composer mode prop fails before `InputArea` supports it**

Run: `npm run build`

Expected: FAIL with a TypeScript prop mismatch for `composerMode`

- [ ] **Step 3: Extend `InputArea.tsx` with a `composerMode` prop and stylesheet import**

```tsx
// D:\project\sun-agent\frontend\src\components\Chat\InputArea.tsx
import './inputArea.css';

interface InputAreaProps {
  composerMode?: 'launch' | 'active';
}
```

- [ ] **Step 4: Create the composer stylesheet and centered launch-state chrome**

```css
/* D:\project\sun-agent\frontend\src\components\Chat\inputArea.css */
.composer {
  width: min(760px, 100%);
  border: 1px solid #3a3a3f;
  border-radius: 24px;
  background: #2b2b2f;
}

.composer--launch {
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.24);
}

.composer--active {
  width: 100%;
  max-width: none;
}
```

- [ ] **Step 5: Replace the empty-state card wall with a centered Manus-style launchpad**

```tsx
{!hasConversation ? (
  <section className="chat-launch">
    <h1 className="chat-launch__title">我能为你做什么？</h1>
    <InputArea composerMode="launch" ... />
    <div className="chat-launch__chips">{/* starter prompts */}</div>
  </section>
) : (
  <section className="chat-thread">
    {/* messages */}
    <InputArea composerMode="active" ... />
  </section>
)}
```

- [ ] **Step 6: Add the transition rules in `chatWindow.css`**

```css
.chat-launch {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

.chat-thread {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
```

- [ ] **Step 7: Run the frontend build to verify the launch-to-chat transition compiles**

Run: `npm run build`

Expected: PASS

- [ ] **Step 8: Commit the launch-state transition**

```bash
git add frontend/src/components/Chat/ChatWindow.tsx frontend/src/components/Chat/chatWindow.css frontend/src/components/Chat/InputArea.tsx frontend/src/components/Chat/inputArea.css
git commit -m "feat: add Manus-style launch state"
```

## Task 3: Quiet the Header and Harmonize the Shell

**Files:**
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Header.tsx`
- Create: `D:\project\sun-agent\frontend\src\components\Layout\header.css`
- Modify: `D:\project\sun-agent\frontend\src\app.css`
- Test: `D:\project\sun-agent\frontend\package.json`

- [ ] **Step 1: Move the header off inline styles and into a dedicated stylesheet**

```tsx
// D:\project\sun-agent\frontend\src\components\Layout\Header.tsx
import './header.css';

return (
  <header className="shell-header">
    <div className="shell-header__brand">{/* title + session meta */}</div>
    <div className="shell-header__status">{/* model + connection */}</div>
  </header>
);
```

- [ ] **Step 2: Run the frontend build to verify it fails before `header.css` exists**

Run: `npm run build`

Expected: FAIL with an import resolution error for `./header.css`

- [ ] **Step 3: Create the calmer Manus-like header stylesheet**

```css
/* D:\project\sun-agent\frontend\src\components\Layout\header.css */
.shell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px 10px;
  background: transparent;
  border-bottom: none;
}

.shell-header__status {
  color: #9a9aa2;
  font-size: 12px;
}
```

- [ ] **Step 4: Tighten shell spacing so the header stops competing with the launch area**

```css
/* D:\project\sun-agent\frontend\src\app.css */
.app-shell {
  background: #1f1f22;
}

.app-main__content {
  display: flex;
  flex-direction: column;
}
```

- [ ] **Step 5: Run the frontend build to verify the shell still compiles cleanly**

Run: `npm run build`

Expected: PASS

- [ ] **Step 6: Commit the header polish**

```bash
git add frontend/src/components/Layout/Header.tsx frontend/src/components/Layout/header.css frontend/src/app.css
git commit -m "style: quiet header chrome"
```

## Task 4: Rebuild the Settings Modal into a Manus-Like Panel

**Files:**
- Modify: `D:\project\sun-agent\frontend\src\pages\Settings.tsx`
- Modify: `D:\project\sun-agent\frontend\src\pages\settings.css`
- Test: `D:\project\sun-agent\frontend\package.json`

- [ ] **Step 1: Refactor the settings JSX into a stronger two-pane structure**

```tsx
return (
  <div className="settings-overlay">
    <div className="settings-modal settings-modal--manus">
      <aside className="settings-rail">{/* left nav */}</aside>
      <section className="settings-stage">{/* right content */}</section>
    </div>
  </div>
);
```

- [ ] **Step 2: Run the frontend build to capture any class/structure breakage before the CSS rewrite**

Run: `npm run build`

Expected: PASS or minor TypeScript fixes only; no backend changes required

- [ ] **Step 3: Rewrite the settings CSS around a Manus-style rail and content stage**

```css
.settings-modal--manus {
  width: min(1460px, 100%);
  height: min(940px, calc(100vh - 24px));
  grid-template-columns: 268px minmax(0, 1fr);
  background: #242427;
}

.settings-rail {
  padding: 18px 14px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  background: #27272a;
}

.settings-stage {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
```

- [ ] **Step 4: Retone the model and MCP areas so they read as lists and rows instead of bulky cards**

```css
.settings-provider-card,
.settings-list-item,
.settings-panel {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
```

- [ ] **Step 5: Run the frontend build to verify the settings shell compiles**

Run: `npm run build`

Expected: PASS

- [ ] **Step 6: Commit the settings redesign**

```bash
git add frontend/src/pages/Settings.tsx frontend/src/pages/settings.css
git commit -m "style: redesign settings center shell"
```

## Task 5: Align Modal Chrome and Perform Final Verification

**Files:**
- Modify: `D:\project\sun-agent\frontend\src\pages\Memory.tsx`
- Modify: `D:\project\sun-agent\frontend\src\pages\Tasks.tsx`
- Modify: `D:\project\sun-agent\frontend\src\pages\Storage.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Layout\Sidebar.tsx`
- Modify: `D:\project\sun-agent\frontend\src\components\Chat\ChatWindow.tsx`
- Test: `D:\project\sun-agent\frontend\package.json`

- [ ] **Step 1: Normalize top-level modal headers and close actions so they match the new shell**

```tsx
<header className="memory-header">
  <div>
    <div className="memory-kicker">memory center</div>
    <h2>记忆中心</h2>
  </div>
  <button className="memory-close" type="button">关闭</button>
</header>
```

- [ ] **Step 2: Recheck the sidebar and launch-state copy density after the shell changes**

```tsx
// keep starter prompts concise and chip-like
const STARTER_CARDS = STARTER_CARDS.map((card) => ({
  ...card,
  description: card.description,
}));
```

- [ ] **Step 3: Run the production build**

Run: `npm run build`

Expected: PASS

- [ ] **Step 4: Run manual verification in dev mode**

Run: `npm run dev`

Expected:
- the sidebar shows the new brand / primary action / primary entries / conversations / bottom settings layout
- a new empty conversation shows the centered launch state
- sending the first message shifts the composer to the bottom
- memory, tasks, storage, and settings still open and close correctly
- settings navigation remains scrollable and coherent

- [ ] **Step 5: Commit the final shell polish**

```bash
git add frontend/src/pages/Memory.tsx frontend/src/pages/Tasks.tsx frontend/src/pages/Storage.tsx frontend/src/components/Layout/Sidebar.tsx frontend/src/components/Chat/ChatWindow.tsx
git commit -m "style: align shell modals and launch flow"
```

## Self-Review

### Spec Coverage

- Sidebar structure: covered by Task 1
- Idle homepage and active chat transition: covered by Task 2
- Reduced header weight: covered by Task 3
- Manus-style settings shell: covered by Task 4
- Final coherence across modals and shell: covered by Task 5

No spec sections are currently unassigned.

### Placeholder Scan

- No `TODO`, `TBD`, or deferred implementation markers remain in the plan
- All tasks include exact file paths
- Each task includes exact commands
- Each code-edit step includes concrete code snippets

### Type Consistency

- Sidebar entry naming stays consistent: `Chat`, `Memory Center`, `Scheduled Tasks`, `File Center`, `Settings`
- Composer mode naming stays consistent: `launch` and `active`
- Settings shell naming stays consistent: `settings-rail` and `settings-stage`
