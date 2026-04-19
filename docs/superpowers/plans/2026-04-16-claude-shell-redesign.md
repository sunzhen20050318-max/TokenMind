# Claude Shell Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the main `TokenMind` shell so the idle homepage and active conversation layout feel closer to Claude while preserving `TokenMind`'s own sidebar destinations, execution timeline, and chat capabilities.

**Architecture:** Keep the existing React + Zustand data flow, but refactor the shell into a quieter Claude-like left rail, a centered idle composer stack, and a fixed-width active reading column. The key structural rule is that messages, timeline, and bottom composer must all obey one shared centered conversation lane.

**Tech Stack:** React 18, TypeScript, Zustand, Vite, CSS

---

## File Map

- Modify: `D:\project\TokenMind\frontend\src\App.tsx`
  - Keep the shell composition stable while allowing the content area to feel more Claude-like.
- Modify: `D:\project\TokenMind\frontend\src\app.css`
  - Tune overall shell proportions and content-stage spacing.
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\Sidebar.tsx`
  - Keep `TokenMind` destinations but reduce weight and density toward a quieter Claude-like rail.
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\sidebar.css`
  - Retune left rail density, action hierarchy, and list feel.
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\Header.tsx`
  - Keep a very light top strip for current session/model info.
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\header.css`
  - Lower chrome intensity and tighten the header.
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ChatWindow.tsx`
  - Rebuild idle state and active conversation lane rules.
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\chatWindow.css`
  - Add Claude-like empty-state spacing and centered active column layout.
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\InputArea.tsx`
  - Keep upload/stop/send capabilities while making the composer feel lower-profile and Claude-like.
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\inputArea.css`
  - Style idle and active composers to match the new shell.
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\MessageBubble.tsx`
  - Align bubbles to a shared fixed-width conversation lane.
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ToolIndicator.tsx`
  - Force execution timeline width to match the conversation lane.

## Task 1: Rebuild the Left Rail Tone

**Files:**
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\Sidebar.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\sidebar.css`
- Modify: `D:\project\TokenMind\frontend\src\app.css`
- Test: `D:\project\TokenMind\frontend\package.json`

- [ ] **Step 1: Keep the existing sidebar destinations but strip away the current Manus-like heaviness**

Target structure:

```tsx
<aside className="shell-sidebar">
  <div className="shell-sidebar__brand">...</div>
  <button className="shell-sidebar__primary">新建对话</button>
  <nav className="shell-sidebar__nav">...</nav>
  <section className="shell-sidebar__sessions">...</section>
  <div className="shell-sidebar__footer">...</div>
</aside>
```

- [ ] **Step 2: Make the rail calmer and narrower in feel via CSS rather than removing content**

Target CSS direction:

```css
.shell-sidebar {
  width: 282px;
  background: linear-gradient(180deg, #1c1b19 0%, #181715 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.05);
}

.shell-sidebar__primary {
  padding: 11px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.04);
}

.shell-sidebar__nav-item {
  padding: 9px 10px;
  border-radius: 12px;
}
```

- [ ] **Step 3: Tighten conversation list density so it reads more like Claude history than app control cards**

Target CSS direction:

```css
.shell-sidebar__session {
  padding: 10px 10px 9px;
  border-radius: 12px;
}

.shell-sidebar__session-title {
  font-size: 13px;
  line-height: 1.35;
}
```

- [ ] **Step 4: Run the frontend build to verify the rail compiles**

Run: `npm run build`
Expected: PASS

## Task 2: Rebuild the Idle Homepage into a Claude-Like Center Stack

**Files:**
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ChatWindow.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\chatWindow.css`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\InputArea.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\inputArea.css`
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\Header.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\header.css`
- Test: `D:\project\TokenMind\frontend\package.json`

- [ ] **Step 1: Replace the current Manus-like launchpad copy with a quieter centered greeting stack**

Target JSX shape:

```tsx
{!hasConversation ? (
  <section className="chat-launch">
    <h1 className="chat-launch__title">Good afternoon...</h1>
    <div className="chat-launch__composer">
      <InputArea composerMode="launch" ... />
    </div>
    <div className="chat-launch__chips">...</div>
  </section>
) : (
  ...
)}
```

- [ ] **Step 2: Remove the extra hero-style paragraph or reduce it to a much smaller helper line**

Target behavior:

- one dominant greeting line
- no large explanatory paragraph competing with the composer
- prompt chips directly under the composer

- [ ] **Step 3: Restyle the launch composer to be wider, flatter, and lower-profile**

Target CSS direction:

```css
.composer--launch .composer__surface {
  min-height: 88px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.045);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.14);
}

.chat-composer-dock.is-launch {
  top: 52%;
  width: min(680px, calc(100% - 72px));
}
```

- [ ] **Step 4: Restyle suggestion chips so they feel like Claude prompt pills, not feature cards**

Target CSS direction:

```css
.chat-launch__chip {
  padding: 9px 12px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.025);
}
```

- [ ] **Step 5: Quiet the top header further so the centered launch stack remains the focal point**

Target CSS direction:

```css
.shell-header {
  padding: 10px 26px 0;
}

.shell-header__model,
.shell-header__session,
.shell-header__status {
  font-size: 12px;
}
```

- [ ] **Step 6: Run the frontend build to verify the idle-state redesign compiles**

Run: `npm run build`
Expected: PASS

## Task 3: Rebuild the Active Conversation into a Fixed Reading Column

**Files:**
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ChatWindow.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\chatWindow.css`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\MessageBubble.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ToolIndicator.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\inputArea.css`
- Test: `D:\project\TokenMind\frontend\package.json`

- [ ] **Step 1: Introduce one shared centered conversation lane in the active state**

Target CSS direction:

```css
.chat-thread {
  width: min(820px, calc(100% - 48px));
  margin: 0 auto;
}

.chat-composer-dock.is-active {
  width: min(820px, calc(100% - 48px));
}
```

- [ ] **Step 2: Make user and assistant messages obey that same lane instead of arbitrary max-widths**

Target JSX/CSS direction:

```tsx
<div className={`message-row ${isUser ? 'is-user' : 'is-assistant'}`}>
  <div className="message-row__lane">
    ...
    <div className={`message-bubble ${isUser ? 'is-user' : 'is-assistant'}`}>...</div>
  </div>
</div>
```

```css
.message-row__lane {
  width: 100%;
}

.message-bubble {
  max-width: 72%;
}
```

- [ ] **Step 3: Keep the timeline but force it to align to the same lane width as its parent user turn**

Target behavior:

- no separate hard-coded width math like `calc(70% - 52px)`
- timeline uses the same wrapper width as the message lane
- timeline visually reads as part of the same turn

- [ ] **Step 4: Restyle the active composer so it feels attached to the same fixed reading column**

Target CSS direction:

```css
.composer--active .composer__surface {
  min-height: 82px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.04);
}
```

- [ ] **Step 5: Run the frontend build to verify the active conversation redesign compiles**

Run: `npm run build`
Expected: PASS

## Task 4: Final Polish and Verification

**Files:**
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ChatWindow.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\MessageBubble.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Chat\ToolIndicator.tsx`
- Modify: `D:\project\TokenMind\frontend\src\components\Layout\Sidebar.tsx`
- Test: `D:\project\TokenMind\frontend\package.json`

- [ ] **Step 1: Recheck copy density so the layout stays calm**

Targets:

- no oversized launch copy
- no over-explained helper text
- no loud sidebar labels

- [ ] **Step 2: Recheck state handling for these flows**

Manual logic checklist:

- empty session still shows idle state
- first sent message switches into active layout
- timeline still appears under a user turn
- upload controls still render
- stop button still renders while streaming

- [ ] **Step 3: Run the final frontend build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 4: Review the implementation against the spec**

Checklist:

- idle state is closer to Claude than Manus
- active chat uses a centered fixed reading column
- message bubbles share a consistent width system
- execution timeline width matches the same lane
- sidebar keeps `TokenMind` destinations while feeling quieter

## Self-Review

### Spec Coverage

- quieter Claude-like sidebar tone: covered by Task 1
- centered idle greeting/composer/pills: covered by Task 2
- fixed-width active conversation column: covered by Task 3
- timeline alignment with message lane: covered by Task 3
- final state review and polish: covered by Task 4

### Placeholder Scan

- no `TODO`, `TBD`, or unresolved placeholders remain
- all tasks list exact files
- all verification steps specify commands and expected results

### Type Consistency

- the plan consistently uses `launch` and `active` composer modes
- the shared width system is consistently described as one conversation lane
- the execution timeline is always defined as part of the same user-turn lane
