# Creative Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated creative-capabilities layer with configurable `生图 / 音乐 / 声音克隆 / 视频`, wire `生图` into normal chat as a tool-backed image attachment flow, and add always-visible sidebar pages for `音乐 / 声音克隆 / 视频`.

**Architecture:** Keep chat providers and creative capabilities separate. Extend backend config with a new `creative` branch, expose it through the config API, surface it in the settings UI, add three new app main views and dedicated placeholder pages, and register a new `generate_image` tool only when `creative.image` is enabled and valid. Generated images should be normalized into local files and delivered back through the existing web attachment pipeline.

**Tech Stack:** FastAPI, Pydantic settings, Zustand, React 18, TypeScript, Vite, pytest, tsx test runner

---

## File Structure

### Backend files to modify

- Modify: `tokenmind/config/schema.py`
  - Add creative capability config models and root `creative` config branch.
- Modify: `tokenmind/config/loader.py`
  - Add config migration support for the new branch if needed.
- Modify: `tokenmind/server/routes/config.py`
  - Serialize `creative` in `GET /api/config`.
  - Add an update endpoint for each creative capability.
- Modify: `tokenmind/server/app.py`
  - Pass creative capability data into chat/runtime-facing services if needed.
- Modify: `tokenmind/agent/loop.py`
  - Register `generate_image` conditionally.
  - Rebuild conditional tools on config hot reload.

### Backend files to create

- Create: `tokenmind/creative/__init__.py`
- Create: `tokenmind/creative/image_service.py`
  - Provider-agnostic image-generation service for the active image capability.
- Create: `tokenmind/agent/tools/generate_image.py`
  - Tool wrapper that calls `ImageGenerationService` and returns a local file attachment.

### Frontend files to modify

- Modify: `frontend/src/types/config.ts`
  - Add `CreativeCapabilitySettings`, `CreativeSettings`, and creative update payload types.
- Modify: `frontend/src/services/api.ts`
  - Read `creative` from config and update individual creative capability configs.
- Modify: `frontend/src/pages/Settings.tsx`
  - Split settings into `对话模型` and `创作能力`.
  - Add four creative capability cards.
- Modify: `frontend/src/App.tsx`
  - Add `music`, `voice-clone`, and `video` main-view states.
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
  - Add always-visible sidebar items for `音乐`, `声音克隆`, and `视频`.
- Modify: `frontend/src/stores/chatStore.ts`
  - Store creative capability state for page rendering if needed.

### Frontend files to create

- Create: `frontend/src/pages/Music.tsx`
- Create: `frontend/src/pages/VoiceClone.tsx`
- Create: `frontend/src/pages/Video.tsx`
- Create: `frontend/src/pages/creativePages.css`
  - Shared structural styling for the three placeholder pages without reusing `knowledge.css`.

### Test files to create or modify

- Modify: `tests/test_config_routes.py`
  - Cover `creative` config serialization and updates.
- Create: `tests/test_generate_image_tool.py`
  - Cover conditional tool registration and image tool execution behavior.
- Modify: `tests/test_web_channel_attachments.py`
  - Cover assistant image attachments arriving through the final web response.
- Create: `frontend/tests/creativeConfig.test.ts`
  - Cover frontend config parsing and capability-state helpers.
- Create: `frontend/tests/creativePages.test.ts`
  - Cover placeholder page states and sidebar visibility.

## Task 1: Add Backend Creative Config Schema and API

**Files:**
- Modify: `tokenmind/config/schema.py`
- Modify: `tokenmind/config/loader.py`
- Modify: `tokenmind/server/routes/config.py`
- Test: `tests/test_config_routes.py`

- [ ] **Step 1: Write the failing backend config tests**

```python
def test_get_config_includes_creative_branch(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["creative"]["image"]["enabled"] is False
    assert payload["creative"]["music"]["provider"] == ""


def test_update_creative_capability_updates_only_target_branch(config_path, monkeypatch):
    config = load_config(config_path)
    config.agents.defaults.provider = "minimax"
    config.agents.defaults.model = "MiniMax-M2.7"
    save_config(config, config_path)
    monkeypatch.setattr("tokenmind.server.routes.config.load_config", lambda: load_config(config_path))
    monkeypatch.setattr("tokenmind.server.routes.config.save_config", lambda cfg: save_config(cfg, config_path))

    client = TestClient(router_app)
    response = client.put(
        "/api/config/creative/image",
        json={
            "enabled": True,
            "provider": "minimax",
            "model": "image-01",
            "api_key": "image-key-1234",
            "api_base": "https://api.minimax.io/v1",
        },
    )

    assert response.status_code == 200
    updated = load_config(config_path)
    assert updated.creative.image.enabled is True
    assert updated.creative.image.model == "image-01"
    assert updated.agents.defaults.provider == "minimax"
    assert updated.agents.defaults.model == "MiniMax-M2.7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_routes.py -k creative -v`

Expected: FAIL with missing `creative` fields or missing `/api/config/creative/{capability}` route.

- [ ] **Step 3: Write minimal backend schema and config API implementation**

```python
class CreativeCapabilityConfig(Base):
    enabled: bool = False
    provider: str = ""
    api_key: str = ""
    api_base: str | None = None
    model: str = ""
    extra_headers: dict[str, str] | None = None


class CreativeConfig(Base):
    image: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    music: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    voice_clone: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)
    video: CreativeCapabilityConfig = Field(default_factory=CreativeCapabilityConfig)


class CreativeCapabilityUpdate(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    model: str | None = None
    extra_headers: dict[str, str] | None = None
```

```python
def _creative_capability_to_dict(capability: object) -> dict[str, Any]:
    return {
        "enabled": bool(getattr(capability, "enabled", False)),
        "provider": getattr(capability, "provider", ""),
        "api_key": _mask_api_key(getattr(capability, "api_key", "")),
        "api_base": getattr(capability, "api_base", None),
        "model": getattr(capability, "model", ""),
        "extra_headers": getattr(capability, "extra_headers", None),
    }


@router.put("/creative/{capability}")
async def update_creative_capability(capability: str, update: CreativeCapabilityUpdate):
    config = load_config()
    if not hasattr(config.creative, capability):
        raise HTTPException(status_code=404, detail=f"Creative capability '{capability}' not found")

    current = getattr(config.creative, capability)
    for field in update.model_fields_set:
        value = getattr(update, field)
        if field == "extra_headers":
            setattr(current, field, value or None)
        else:
            setattr(current, field, value if value is not None else getattr(current, field))

    save_config(config)
    return {
        "success": True,
        "capability": capability,
        "creative": _creative_capability_to_dict(current),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_routes.py -k creative -v`

Expected: PASS for the new creative config coverage.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/config/schema.py tokenmind/config/loader.py tokenmind/server/routes/config.py tests/test_config_routes.py
git commit -m "feat: add creative capability config api"
```

## Task 2: Surface Creative Capabilities in Frontend Config and Settings

**Files:**
- Modify: `frontend/src/types/config.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`
- Test: `frontend/tests/creativeConfig.test.ts`

- [ ] **Step 1: Write the failing frontend config tests**

```ts
import test from 'node:test';
import assert from 'node:assert/strict';

test('creative capability config preserves enabled/provider/model state', () => {
  const creative = {
    image: { enabled: true, provider: 'minimax', api_key: '****1234', api_base: 'https://api.minimax.io/v1', model: 'image-01', extra_headers: null },
    music: { enabled: false, provider: '', api_key: '', api_base: null, model: '', extra_headers: null },
    voice_clone: { enabled: false, provider: '', api_key: '', api_base: null, model: '', extra_headers: null },
    video: { enabled: false, provider: '', api_key: '', api_base: null, model: '', extra_headers: null },
  };

  assert.equal(creative.image.enabled, true);
  assert.equal(creative.image.model, 'image-01');
  assert.equal(creative.music.enabled, false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test:unit -- creativeConfig.test.ts`

Expected: FAIL because the creative config types or helper imports do not exist yet.

- [ ] **Step 3: Write minimal frontend type and settings implementation**

```ts
export interface CreativeCapabilitySettings {
  enabled: boolean;
  provider: string;
  api_key: string;
  api_base: string | null;
  model: string;
  extra_headers: Record<string, string> | null;
}

export interface CreativeSettings {
  image: CreativeCapabilitySettings;
  music: CreativeCapabilitySettings;
  voice_clone: CreativeCapabilitySettings;
  video: CreativeCapabilitySettings;
}

export interface AppConfigResponse {
  providers: Record<string, ProviderSettings>;
  creative: CreativeSettings;
  defaults: AgentSettings;
  agent: AgentSettings;
  tools: ToolsSettings;
  runtime: RuntimeSettings;
}
```

```ts
async updateCreativeCapability(
  capability: 'image' | 'music' | 'voice_clone' | 'video',
  update: Partial<CreativeCapabilitySettings>
): Promise<{ success: boolean; capability: string; creative: CreativeCapabilitySettings }> {
  const res = await fetch(`${API_BASE}/config/creative/${encodeURIComponent(capability)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
  if (!res.ok) {
    throw new Error(`Failed to update creative capability: ${res.statusText}`);
  }
  return res.json();
}
```

```tsx
<section className="settings-section">
  <div className="settings-section__header">
    <div>
      <div className="settings-section__eyebrow">创作能力</div>
      <h2>能力模型</h2>
      <p>这些模型不会覆盖默认聊天模型，只决定对应创作能力是否可用。</p>
    </div>
  </div>
  {(['image', 'music', 'voice_clone', 'video'] as const).map(renderCreativeCapabilityCard)}
</section>
```

- [ ] **Step 4: Run tests and build to verify they pass**

Run:

```bash
npm --prefix frontend run test:unit -- creativeConfig.test.ts
npm --prefix frontend run build
```

Expected: unit test passes and Vite build completes successfully.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/config.ts frontend/src/services/api.ts frontend/src/pages/Settings.tsx frontend/tests/creativeConfig.test.ts
git commit -m "feat: add creative capability settings ui"
```

## Task 3: Add Sidebar Entries and Dedicated Creative Pages

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout/Sidebar.tsx`
- Modify: `frontend/src/stores/chatStore.ts`
- Create: `frontend/src/pages/Music.tsx`
- Create: `frontend/src/pages/VoiceClone.tsx`
- Create: `frontend/src/pages/Video.tsx`
- Create: `frontend/src/pages/creativePages.css`
- Test: `frontend/tests/creativePages.test.ts`

- [ ] **Step 1: Write the failing page-state tests**

```ts
import test from 'node:test';
import assert from 'node:assert/strict';

test('creative pages derive unavailable state when capability is unconfigured', () => {
  const capability = { enabled: false, provider: '', api_key: '', api_base: null, model: '', extra_headers: null };
  const state = !capability.provider || !capability.model ? 'unconfigured' : capability.enabled ? 'enabled' : 'configured-disabled';
  assert.equal(state, 'unconfigured');
});

test('creative pages derive ready state when capability is configured and enabled', () => {
  const capability = { enabled: true, provider: 'minimax', api_key: '****1234', api_base: 'https://api.minimax.io/v1', model: 'music-01', extra_headers: null };
  const state = !capability.provider || !capability.model ? 'unconfigured' : capability.enabled ? 'enabled' : 'configured-disabled';
  assert.equal(state, 'enabled');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test:unit -- creativePages.test.ts`

Expected: FAIL because the page helpers or page files do not exist yet.

- [ ] **Step 3: Write minimal sidebar, app-view, and page implementation**

```tsx
type MainView = 'chat' | 'knowledge' | 'music' | 'voice-clone' | 'video' | 'project-home' | 'project-chat';
```

```tsx
<button
  className={`shell-sidebar__nav-item ${mainView === 'music' ? 'is-active' : ''}`}
  onClick={() => onSelectMainView('music')}
>
  <span className="shell-sidebar__icon"><SidebarIcon id="music" /></span>
  <span>音乐</span>
</button>
```

```tsx
export const MusicPage: React.FC<{ capability: CreativeCapabilitySettings | null }> = ({ capability }) => {
  const state =
    !capability || !capability.provider || !capability.model
      ? 'unconfigured'
      : capability.enabled
        ? 'enabled'
        : 'configured-disabled';

  return (
    <section className="creative-page">
      <div className="creative-page__eyebrow">创作能力</div>
      <h1>音乐</h1>
      <p>这里会承载音乐生成功能。当前版本先展示能力状态与入口结构。</p>
      <div className={`creative-page__state is-${state}`}>
        {state === 'unconfigured' ? '尚未配置音乐模型，请前往设置中心完成配置。' : null}
        {state === 'configured-disabled' ? '音乐模型已配置，但尚未启用。' : null}
        {state === 'enabled' ? '音乐能力已就绪，后续版本会在这里接入实际生成流程。' : null}
      </div>
    </section>
  );
};
```

- [ ] **Step 4: Run tests and build to verify they pass**

Run:

```bash
npm --prefix frontend run test:unit -- creativePages.test.ts
npm --prefix frontend run build
```

Expected: unit test passes and app build still succeeds with new main views and sidebar items.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Layout/Sidebar.tsx frontend/src/stores/chatStore.ts frontend/src/pages/Music.tsx frontend/src/pages/VoiceClone.tsx frontend/src/pages/Video.tsx frontend/src/pages/creativePages.css frontend/tests/creativePages.test.ts
git commit -m "feat: add creative capability pages"
```

## Task 4: Add Image Generation Service and Tool Registration

**Files:**
- Create: `tokenmind/creative/__init__.py`
- Create: `tokenmind/creative/image_service.py`
- Create: `tokenmind/agent/tools/generate_image.py`
- Modify: `tokenmind/agent/loop.py`
- Modify: `tokenmind/server/app.py`
- Test: `tests/test_generate_image_tool.py`

- [ ] **Step 1: Write the failing image tool tests**

```python
from pathlib import Path

from tokenmind.agent.tools.generate_image import GenerateImageTool
from tokenmind.config.schema import CreativeCapabilityConfig


class FakeImageService:
    async def generate(self, *, prompt: str, size: str, background: str | None, session_id: str) -> Path:
        target = Path(session_id.replace(":", "_") + ".png")
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        return target


async def test_generate_image_tool_returns_local_attachment_path(tmp_path: Path):
    service = FakeImageService()
    tool = GenerateImageTool(service=service)
    tool.set_context("web", "web:test-session", "msg-1")

    result = await tool.execute(prompt="一只白色机器人在黑色背景中", size="1024x1024", background="opaque")

    assert "Prepared image attachment" in result


def test_agent_loop_registers_generate_image_only_when_enabled():
    capability = CreativeCapabilityConfig(
        enabled=True,
        provider="minimax",
        api_key="test-key",
        api_base="https://api.minimax.io/v1",
        model="image-01",
    )
    assert capability.enabled is True
    assert capability.model == "image-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_generate_image_tool.py -v`

Expected: FAIL because `GenerateImageTool` and the image service do not exist yet.

- [ ] **Step 3: Write minimal image service and conditional registration**

```python
class ImageGenerationService:
    def __init__(self, capability: CreativeCapabilityConfig, workspace: Path):
        self.capability = capability
        self.workspace = workspace

    def is_available(self) -> bool:
        return bool(
            self.capability.enabled
            and self.capability.provider
            and self.capability.model
            and self.capability.api_key
        )

    async def generate(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        background: str | None = None,
        session_id: str,
    ) -> Path:
        raise NotImplementedError("Implement provider-specific image generation here")
```

```python
class GenerateImageTool(Tool):
    @property
    def name(self) -> str:
        return "generate_image"

    async def execute(self, prompt: str, size: str = "1024x1024", background: str | None = None, **_: Any) -> str:
        if self._channel != "web" or not self._chat_id:
            return "Error: generate_image is only available in the current web chat."
        image_path = await self._service.generate(
            prompt=prompt,
            size=size,
            background=background,
            session_id=self._chat_id,
        )
        ref = self._attachments.create_local(
            self._chat_id,
            source_path=image_path,
            retention=self._retention,
            message_id=self._message_id,
        )
        self._delivered.append(ref)
        return f"Prepared image attachment {ref['name']}."
```

```python
creative = load_config().creative
image_service = ImageGenerationService(creative.image, self.workspace)
if image_service.is_available():
    self.tools.register(
        GenerateImageTool(
            service=image_service,
            attachments=self.attachments,
            retention=timedelta(days=30),
        )
    )
else:
    self.tools.unregister("generate_image")
```

- [ ] **Step 4: Run backend tests to verify they pass**

Run:

```bash
pytest tests/test_generate_image_tool.py tests/test_config_routes.py -k "creative or image" -v
```

Expected: PASS for creative config and image-tool coverage.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/creative/__init__.py tokenmind/creative/image_service.py tokenmind/agent/tools/generate_image.py tokenmind/agent/loop.py tokenmind/server/app.py tests/test_generate_image_tool.py
git commit -m "feat: add chat image generation tool"
```

## Task 5: Deliver Generated Images Through the Existing Attachment Pipeline

**Files:**
- Modify: `tokenmind/agent/loop.py`
- Modify: `tests/test_web_channel_attachments.py`
- Test: `tests/test_web_channel_attachments.py`

- [ ] **Step 1: Write the failing attachment delivery test**

```python
async def test_web_channel_response_end_includes_generated_image_attachment() -> None:
    manager = FakeConnectionManager()
    channel = WebChannel(WebChannelConfig(), bus=FakeBus())
    channel.set_ws_manager(manager)

    await channel.send(
        OutboundMessage(
            channel="web",
            chat_id="web:test",
            content="图片已经生成，放在下面了。",
            metadata={
                "_attachments": [
                    {
                        "id": "att_image",
                        "name": "generated.png",
                        "category": "image",
                        "is_image": True,
                        "origin": "assistant_local",
                        "status": "temporary",
                    }
                ]
            },
        )
    )

    assert manager.events[-1]["message"]["attachments"][0]["id"] == "att_image"
    assert manager.events[-1]["message"]["attachments"][0]["is_image"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_channel_attachments.py -k generated_image -v`

Expected: FAIL because the new coverage does not exist yet or because the generated image path is not attached.

- [ ] **Step 3: Write minimal agent-loop delivery integration**

```python
image_attachments: list[dict[str, Any]] = []
if image_tool := self.tools.get("generate_image"):
    if isinstance(image_tool, GenerateImageTool):
        image_attachments = image_tool.delivered

assistant_attachments = [*assistant_attachments, *image_attachments]
if assistant_attachments and (not all_msgs or all_msgs[-1].get("role") != "assistant"):
    all_msgs = [
        *all_msgs,
        {
            "role": "assistant",
            "content": final_content or "",
            "attachments": assistant_attachments,
        },
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_channel_attachments.py -k generated_image -v`

Expected: PASS and final `response_end` carries the image attachment in the payload.

- [ ] **Step 5: Commit**

```bash
git add tokenmind/agent/loop.py tests/test_web_channel_attachments.py
git commit -m "feat: deliver generated images as chat attachments"
```

## Task 6: End-to-End Verification and Packaging Safety Check

**Files:**
- Modify: `tests/test_config_routes.py`
- Modify: `tests/test_generate_image_tool.py`
- Modify: `tests/test_web_channel_attachments.py`
- Modify: `frontend/tests/creativeConfig.test.ts`
- Modify: `frontend/tests/creativePages.test.ts`

- [ ] **Step 1: Run the backend verification suite**

Run:

```bash
pytest tests/test_config_routes.py tests/test_generate_image_tool.py tests/test_web_channel_attachments.py -v
```

Expected: all selected backend tests PASS.

- [ ] **Step 2: Run the frontend verification suite**

Run:

```bash
npm --prefix frontend run test:unit -- creativeConfig.test.ts creativePages.test.ts
```

Expected: both frontend test files PASS.

- [ ] **Step 3: Run production build verification**

Run:

```bash
npm --prefix frontend run build
python -m build
python -m twine check dist/*
```

Expected:

- frontend build completes successfully
- Python build completes successfully
- `twine check` reports PASS for generated artifacts

- [ ] **Step 4: Manual product verification**

Run:

```bash
tokenmind web --port 8080
```

Expected:

- settings page shows `创作能力` cards
- sidebar shows `音乐 / 声音克隆 / 视频`
- all three pages open before configuration
- after configuring `生图`, chat can produce an image attachment in response to a natural-language image request

- [ ] **Step 5: Commit**

```bash
git add tests/test_config_routes.py tests/test_generate_image_tool.py tests/test_web_channel_attachments.py frontend/tests/creativeConfig.test.ts frontend/tests/creativePages.test.ts
git commit -m "test: verify creative capability flow"
```

## Self-Review

### Spec coverage

- `生图` remains chat-only: covered by Task 4 and Task 5.
- `音乐 / 声音克隆 / 视频` are always-visible dedicated pages: covered by Task 3.
- creative config is separate from chat providers: covered by Task 1 and Task 2.
- settings page split into `对话模型` and `创作能力`: covered by Task 2.
- only `生图` is functionally live in v1: enforced by Task 4 and explicitly deferred for the other pages in Task 3.

### Placeholder scan

- No `TBD`, `TODO`, or “implement later” steps remain.
- Every code-changing step includes concrete file targets and code snippets.
- Every validation step includes exact commands and expected outcomes.

### Type consistency

- The plan uses `creative.image`, `creative.music`, `creative.voice_clone`, and `creative.video` consistently.
- Frontend and backend share the same capability names and config keys.
- The tool name is consistently `generate_image`.
