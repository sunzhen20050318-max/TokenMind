# TokenMind Creative Capabilities Design

## Summary

This spec adds a first-class creative-capabilities layer to `TokenMind`.

The product goal is to let users configure more than one kind of AI model inside the app, without forcing every capability through the existing chat-model provider flow.

The first release introduces four creative capability slots:

1. `生图`
2. `音乐`
3. `声音克隆`
4. `视频`

The behavior is intentionally split:

1. `生图` is available inside the normal chat experience and can be invoked during a conversation
2. `音乐`
3. `声音克隆`
4. `视频`

each get their own persistent left-sidebar entry and their own dedicated page

In v1, only `生图` is fully functional.

The other three pages and their settings should still exist, always remain visible in navigation, and clearly reflect whether the related capability has been configured. They should not execute real generation jobs yet.

## Goals

- Add a dedicated creative-capabilities configuration layer that does not interfere with chat-model defaults
- Let users configure separate model credentials and settings for:
  - image generation
  - music generation
  - voice cloning
  - video generation
- Keep `生图` as an in-chat capability rather than a separate navigation page
- Add three new persistent left-sidebar entries:
  - `音乐`
  - `声音克隆`
  - `视频`
- Add one dedicated page for each of those three entries
- Keep those three entries visible even when the user has not configured the corresponding model yet
- Make the three dedicated pages usable as status surfaces from day one, even before their actual generation workflows are implemented
- Let chat replies return generated images through the existing web attachment pipeline

## Non-Goals

- Do not make `音乐`, `声音克隆`, or `视频` execute real generation requests in v1
- Do not add a separate left-sidebar page for `生图`
- Do not merge creative capability configuration into the current chat `providers` structure
- Do not redesign the existing `知识库` page and reuse it as the visual template for the three creative pages
- Do not add batch generation, reference-image editing, seeds, negative prompts, job queues, or asset libraries in v1
- Do not add project-scoped creative settings in v1

## Problem Statement

Today `TokenMind` has one effective model configuration surface centered around chat providers.

That structure works for normal conversation models, but it is the wrong abstraction for capability-specific generation tasks:

- a user may want one provider for chat and a different provider for image generation
- enabling a creative model must not accidentally change the active default chat model
- music, voice, and video are not normal chat providers and should not be treated as such in navigation or configuration

The app also currently lacks durable product surfaces for non-chat creative work. The sidebar contains `知识库` and `项目`, but there is no dedicated place for users to see whether music, voice, or video generation is configured and available.

## Product Direction

`TokenMind` should separate:

1. `对话模型`
2. `创作能力模型`

These are different product layers with different runtime behavior.

### Chat Layer

The chat layer continues to use the existing provider/default-model system:

- provider registry
- default chat model
- reasoning effort
- chat runtime selection

### Creative Capability Layer

The creative layer becomes capability-oriented rather than provider-oriented.

That means the product is configured in terms of:

- what the user wants to do
- which model powers that capability
- whether that capability is enabled

instead of trying to make every capability look like a chat provider.

This keeps the chat runtime stable and gives the UI room to grow into more creative workflows later.

## Confirmed Information Architecture

The final left-sidebar top-level order should become:

1. `知识库`
2. `音乐`
3. `声音克隆`
4. `视频`
5. `项目`

Important rules:

- `音乐`, `声音克隆`, and `视频` are new top-level entries
- `生图` is not a sidebar page in v1
- the three new entries always appear even when their capabilities are not configured
- the three new entries always open a page
- those pages should show consistent structure in both configured and unconfigured states
- those pages must not simply copy the current `知识库` layout
- detailed visual design for those pages will be specified later by the user

## Primary User Flows

### Flow 1: Configure a creative capability

1. user opens `设置中心`
2. user enters the `模型` section
3. user finds the `创作能力` group
4. user opens one capability card such as `生图`
5. user enters provider, model, API key, API base, optional headers, and enable state
6. user saves
7. the app updates that capability's status immediately

### Flow 2: Use image generation in chat

1. user configures and enables `生图`
2. user starts a normal chat conversation
3. user asks for an image in natural language
4. the assistant receives a `generate_image` tool because the capability is enabled
5. the tool generates an image through the configured provider
6. the image is returned to the chat as an assistant attachment
7. the chat bubble shows normal assistant text plus an inline image attachment card

### Flow 3: Open a non-configured creative page

1. user clicks `音乐`, `声音克隆`, or `视频`
2. the app opens that dedicated page even if no model is configured
3. the page clearly states that the capability is not available yet
4. the page points the user to `设置中心 -> 模型 -> 创作能力`

### Flow 4: Open a configured but not-yet-implemented creative page

1. user configures and enables `音乐`, `声音克隆`, or `视频`
2. user opens that page from the sidebar
3. the page shows that the capability is configured and ready
4. the page still remains a placeholder experience in v1 because execution is out of scope for this iteration

## Configuration Model

The backend should add a new top-level configuration branch:

- `creative`

This branch should be completely separate from the existing chat-provider configuration.

### Shape

The first release uses four capability slots:

- `creative.image`
- `creative.music`
- `creative.voice_clone`
- `creative.video`

Each capability uses the same base schema:

- `enabled: bool`
- `provider: str`
- `api_key: str`
- `api_base: str | null`
- `model: str`
- `extra_headers: dict[str, str] | null`

### Why This Shape

This structure is intentionally capability-first.

It avoids several product and implementation problems:

- changing a creative model cannot accidentally switch the active chat model
- the settings UI can render one reusable form/card for every creative capability
- future capability-specific settings can be added locally without polluting the chat provider schema

## Settings Page Design

The current `模型` settings section should be split into two product groups:

### 1. 对话模型

This is the current provider configuration area and should largely remain as-is:

- provider cards
- masked API keys
- chat default model
- active provider/default selection behavior

### 2. 创作能力

Add a new block below the chat-model area with four capability cards:

- `生图`
- `音乐`
- `声音克隆`
- `视频`

Each card should expose:

- enabled switch
- provider
- model
- API key
- API base
- extra headers

Each card should also show a status summary at the top:

- `未配置`
- `已配置但未启用`
- `已启用`

### UX Rules

- configuration for `音乐`, `声音克隆`, and `视频` lives only in `设置中心`
- their dedicated pages should read and reflect the saved state, but should not own secrets or direct credential editing in v1
- `生图` configuration lives in the same `创作能力` group and controls whether the chat runtime registers the image-generation tool

## Sidebar and App-Shell Changes

### Sidebar

Extend the existing sidebar navigation with three new top-level items:

- `音乐`
- `声音克隆`
- `视频`

These should behave like first-class main views rather than modal shortcuts.

### App View Model

Add three new main view states:

- `music`
- `voice-clone`
- `video`

These should sit alongside the existing views such as:

- `chat`
- `knowledge`
- `project-home`
- `project-chat`

### Dedicated Pages

Add one page component per creative surface:

- `MusicPage`
- `VoiceClonePage`
- `VideoPage`

These pages should:

- read creative capability status from backend config
- render stable empty/disabled/ready states
- not depend on hidden feature flags

The page visuals should remain structurally separate from `KnowledgePage` because the user explicitly does not want those pages to inherit the current knowledge-base design language.

## Image Generation Runtime Design

### Trigger Model

`生图` should be invoked through normal natural-language chat, not through:

- a dedicated sidebar page
- a slash command
- a special input button in v1

The user should simply ask for an image in the conversation.

### Tool Registration Rule

Register a `generate_image` tool only when `creative.image` is both:

- configured enough to run
- enabled

If `creative.image` is disabled or incomplete, the chat runtime should not expose the tool to the model.

### Recommended Tool Shape

The first version of `generate_image` should stay intentionally small.

Recommended inputs:

- `prompt`
- `size`
- `background`

Do not add advanced controls yet such as:

- reference images
- negative prompts
- seed control
- edit or inpaint flows
- multi-image batches

### Backend Service Boundary

Do not push image generation into the generic chat-provider `chat()` path.

Instead add a dedicated image-generation service, for example:

- `tokenmind/creative/image_service.py`

Responsibilities:

- validate active image capability config
- call the configured image provider endpoint
- normalize the generated image into a local file
- return a local file path or normalized artifact record

This should then flow through the existing assistant attachment delivery system.

## Image Delivery in Chat

The generated image should return through the current web attachment pipeline rather than through a custom frontend-only shortcut.

Recommended flow:

1. assistant decides to call `generate_image`
2. backend image-generation service creates or downloads the image artifact
3. the assistant reply attaches that image through the same message-bound attachment system already used for assistant-delivered files
4. the frontend renders the image preview card directly under the assistant response text

This keeps the user experience coherent:

- one assistant turn
- one text response
- one inline image artifact

instead of splitting image delivery into detached system events.

## Creative Pages in v1

### Shared Product Rules

The first version of `音乐`, `声音克隆`, and `视频` pages should all support the same three product states:

1. `未配置`
2. `已配置但未启用`
3. `已启用`

### Unconfigured State

Show:

- capability title
- short explanation
- unavailable status
- action hint pointing to `设置中心 -> 模型 -> 创作能力`

### Configured But Disabled State

Show:

- capability title
- detected provider/model summary
- clear note that the capability is configured but not enabled

### Enabled State

Show:

- capability title
- configured provider/model summary
- ready-state copy
- placeholder message explaining that real generation workflow will arrive in a later iteration

The exact layout and visual treatment of these pages will be specified later and should therefore remain implementation-light in this design.

## Backend API Surface

### Config API

Extend the existing config response to include creative capability data.

Recommended additions:

- `creative` block in `GET /api/config`
- creative update endpoint support in the config router

The update surface can be either:

- `PUT /api/config/creative/{capability}`

or a partial update endpoint under the broader config router

as long as the frontend can save each capability independently.

### Chat Runtime

When building the tool registry for web chat:

- inspect `creative.image`
- register `generate_image` only when usable

No runtime execution support is required yet for:

- `creative.music`
- `creative.voice_clone`
- `creative.video`

## Frontend Data Model Changes

The frontend config types should add a `creative` branch mirroring backend shape.

Recommended interfaces:

- `CreativeCapabilitySettings`
- `CreativeSettings`

These should be read anywhere that needs status reflection:

- settings page
- sidebar-linked creative pages
- chat runtime capability indicators if needed later

## Error Handling

### Image Generation

If the active image capability is misconfigured or fails:

- the user should receive a normal assistant error response in chat
- the assistant should not emit a broken or empty attachment card

### Creative Pages

If capability config fails to load:

- the page should show a standard fetch-error state
- navigation should remain intact

### Settings Save

If saving a creative capability fails:

- the current form should remain open
- the page should show an inline error notice
- no partial optimistic state should overwrite the last confirmed config

## Testing Strategy

### Backend Tests

Add focused tests for:

- creative config serialization in `GET /api/config`
- creative capability update endpoint behavior
- `generate_image` tool registration only when `creative.image` is enabled and valid
- image-generation service error handling
- image generation delivering assistant attachments into the existing web response pipeline

### Frontend Tests

Add focused coverage for:

- settings page rendering the new `创作能力` block
- saving one capability without mutating chat defaults
- sidebar rendering `音乐`, `声音克隆`, and `视频`
- dedicated pages showing correct state for:
  - unconfigured
  - configured but disabled
  - enabled

### Product Verification

Manual checks for v1:

1. open settings and configure `生图`
2. confirm normal chat default model is unchanged
3. ask for an image in chat
4. confirm assistant returns text plus an image attachment
5. open `音乐`, `声音克隆`, and `视频` pages before configuration
6. confirm all three pages are visible and show unavailable state
7. configure one of those non-image capabilities
8. confirm its page reflects configured state without pretending to execute jobs

## Rollout Order

Implement in this order:

1. add backend creative config schema and persistence
2. extend config API and frontend config types
3. split the settings `模型` page into `对话模型` and `创作能力`
4. add sidebar entries and new main-view pages for `音乐`, `声音克隆`, and `视频`
5. add `generate_image` service and tool
6. wire generated images into the existing assistant attachment flow
7. polish page states and copy

This order establishes the product structure first, then the real in-chat capability.

## Recommendation

Build creative capabilities as a dedicated product layer separate from chat providers.

The right v1 is:

- three always-visible dedicated sidebar pages:
  - `音乐`
  - `声音克隆`
  - `视频`
- one settings-page capability group for:
  - `生图`
  - `音乐`
  - `声音克隆`
  - `视频`
- one fully functional in-chat `生图` capability
- three non-functional but state-aware creative pages

Do not merge these capabilities into the existing chat-provider default-model system.
Do not create a separate sidebar page for image generation in v1.
Do not pretend that music, voice clone, or video are functionally complete before their execution workflows are actually built.
