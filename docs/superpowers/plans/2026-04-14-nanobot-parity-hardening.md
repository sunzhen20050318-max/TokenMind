# Nanobot Parity Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `sun-agent` closer to the most valuable April 2026 `nanobot` hardening work by tightening OpenRouter Claude prompt caching, strengthening long-running runtime behavior, and adding backward-compatible Jinja2-driven response/memory templates.

**Architecture:** Keep the rollout in three isolated slices. First constrain provider-side prompt caching to the exact OpenRouter Claude cases that benefit from it. Next replace the agent loop's global serialization with session-scoped concurrency primitives and harden shared retry/background-task behavior. Finally add optional Jinja2 templating around response post-processing and memory consolidation without changing default behavior when templates are absent.

**Tech Stack:** Python 3.11+, pytest, asyncio, Jinja2, existing provider/session/runtime stack

---

### Task 1: OpenRouter Claude-Only Prompt Caching

**Files:**
- Modify: `D:\project\sun-agent\tests\test_openai_compat_provider.py`
- Modify: `D:\project\sun-agent\sun_agent\providers\registry.py`
- Modify: `D:\project\sun-agent\sun_agent\providers\openai_compat_provider.py`

- [ ] **Step 1: Write the failing provider tests**

Add tests that prove `OpenRouter` only applies `cache_control` for Claude-family models and leaves non-Claude models untouched.

- [ ] **Step 2: Run the provider tests to verify failure**

Run: `pytest D:\project\sun-agent\tests\test_openai_compat_provider.py -q`
Expected: FAIL on the new Claude/non-Claude caching assertions.

- [ ] **Step 3: Implement the minimal provider gating**

Add model-aware prompt-caching support metadata in the provider spec / provider implementation so `OpenRouter` only injects `cache_control` for Claude models while Anthropic retains full support.

- [ ] **Step 4: Re-run the provider tests**

Run: `pytest D:\project\sun-agent\tests\test_openai_compat_provider.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add D:/project/sun-agent/tests/test_openai_compat_provider.py D:/project/sun-agent/sun_agent/providers/registry.py D:/project/sun-agent/sun_agent/providers/openai_compat_provider.py
git commit -m "fix: scope openrouter prompt caching to claude models"
```

### Task 2: Long-Running Runtime Hardening

**Files:**
- Modify: `D:\project\sun-agent\tests\test_task_cancel.py`
- Modify: `D:\project\sun-agent\tests\test_provider_retry.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\loop.py`
- Modify: `D:\project\sun-agent\sun_agent\providers\base.py`

- [ ] **Step 1: Write failing runtime tests**

Add tests that prove:
- different sessions can dispatch concurrently
- same session still serializes
- background task tracking does not raise when tasks complete out of order
- retry logic honors structured provider status/error markers before falling back to string matching

- [ ] **Step 2: Run the focused runtime tests to verify failure**

Run: `pytest D:\project\sun-agent\tests\test_task_cancel.py D:\project\sun-agent\tests\test_provider_retry.py -q`
Expected: FAIL on the new session-concurrency / retry-shape assertions.

- [ ] **Step 3: Implement session-scoped locking and safer background tracking**

Replace the single `_processing_lock` with per-session locks, ensure they are cleaned up safely, and make `_schedule_background()` resilient when callbacks fire after prior list mutation.

- [ ] **Step 4: Implement retry hardening**

Teach `LLMProvider.chat_with_retry()` to look for structured transient indicators on provider responses / exceptions first, then fall back to existing marker matching. Keep current image fallback behavior intact.

- [ ] **Step 5: Re-run the focused runtime tests**

Run: `pytest D:\project\sun-agent\tests\test_task_cancel.py D:\project\sun-agent\tests\test_provider_retry.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add D:/project/sun-agent/tests/test_task_cancel.py D:/project/sun-agent/tests/test_provider_retry.py D:/project/sun-agent/sun_agent/agent/loop.py D:/project/sun-agent/sun_agent/providers/base.py
git commit -m "refactor: harden long-running runtime behavior"
```

### Task 3: Backward-Compatible Jinja2 Response and Memory Templates

**Files:**
- Modify: `D:\project\sun-agent\pyproject.toml`
- Create: `D:\project\sun-agent\sun_agent\templates_engine.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\memory.py`
- Modify: `D:\project\sun-agent\sun_agent\agent\loop.py`
- Modify: `D:\project\sun-agent\sun_agent\config\schema.py`
- Modify: `D:\project\sun-agent\sun_agent\server\routes\config.py`
- Create: `D:\project\sun-agent\tests\test_templates_engine.py`
- Modify: `D:\project\sun-agent\tests\test_memory_consolidation_types.py`

- [ ] **Step 1: Write failing template tests**

Add tests for:
- default no-template behavior remains unchanged
- response templates can render a final assistant response with runtime-safe variables
- memory consolidation prompt/template generation can be overridden without breaking `save_memory` tool flow

- [ ] **Step 2: Run the focused template tests to verify failure**

Run: `pytest D:\project\sun-agent\tests\test_templates_engine.py D:\project\sun-agent\tests\test_memory_consolidation_types.py -q`
Expected: FAIL because the template engine/config does not exist yet.

- [ ] **Step 3: Add the minimal template engine**

Introduce a small Jinja2 wrapper with safe defaults, explicit context values, and a no-template fast path.

- [ ] **Step 4: Thread template support into response and memory flows**

Use the template engine only when configured. Preserve the current output path when no template is set so existing users get identical behavior.

- [ ] **Step 5: Re-run the focused template tests**

Run: `pytest D:\project\sun-agent\tests\test_templates_engine.py D:\project\sun-agent\tests\test_memory_consolidation_types.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add D:/project/sun-agent/pyproject.toml D:/project/sun-agent/sun_agent/templates_engine.py D:/project/sun-agent/sun_agent/agent/memory.py D:/project/sun-agent/sun_agent/agent/loop.py D:/project/sun-agent/sun_agent/config/schema.py D:/project/sun-agent/sun_agent/server/routes/config.py D:/project/sun-agent/tests/test_templates_engine.py D:/project/sun-agent/tests/test_memory_consolidation_types.py
git commit -m "feat: add optional jinja2 templates"
```

### Task 4: Regression Verification and Gap Summary

**Files:**
- Modify: `D:\project\sun-agent\README.md` (only if new config surface needs documentation)

- [ ] **Step 1: Run focused regressions**

Run: `pytest D:\project\sun-agent\tests\test_openai_compat_provider.py D:\project\sun-agent\tests\test_task_cancel.py D:\project\sun-agent\tests\test_provider_retry.py D:\project\sun-agent\tests\test_memory_consolidation_types.py D:\project\sun-agent\tests\test_exec_approval.py -q`
Expected: PASS

- [ ] **Step 2: Run broader safety regression**

Run: `pytest -q --ignore=D:\project\sun-agent\tests\test_matrix_channel.py`
Expected: PASS

- [ ] **Step 3: Run syntax / build checks**

Run: `python -m compileall D:\project\sun-agent\sun_agent D:\project\sun-agent\tests`
Expected: PASS

- [ ] **Step 4: Update docs if needed**

Only document new config/template knobs if we actually expose them in user-facing settings or config.

- [ ] **Step 5: Final commit**

```bash
git add D:/project/sun-agent/README.md
git commit -m "docs: document runtime hardening and template options"
```
