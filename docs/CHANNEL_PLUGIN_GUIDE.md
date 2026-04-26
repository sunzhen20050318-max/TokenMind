# Channel Plugin Guide

Build a custom TokenMind channel in three steps: subclass, package, install.

## How It Works

TokenMind discovers channel plugins via Python [entry points](https://packaging.python.org/en/latest/specifications/entry-points/). When `tokenmind gateway` starts, it scans:

1. built-in channels in `tokenmind/channels/`
2. external packages registered under the compatibility entry-point group `tokenmind.channels`

The internal package namespace is still `tokenmind`, so plugin imports and entry-point groups currently keep that name.

## Quick Start

We'll build a minimal webhook channel that receives messages via HTTP POST and sends replies back.

### Project Structure

```text
tokenmind-channel-webhook/
├── tokenmind_channel_webhook/
│   ├── __init__.py
│   └── channel.py
└── pyproject.toml
```

### 1. Create Your Channel

```python
# tokenmind_channel_webhook/__init__.py
from tokenmind_channel_webhook.channel import WebhookChannel

__all__ = ["WebhookChannel"]
```

```python
# tokenmind_channel_webhook/channel.py
import asyncio
from typing import Any

from aiohttp import web
from loguru import logger

from tokenmind.channels.base import BaseChannel
from tokenmind.bus.events import OutboundMessage


class WebhookChannel(BaseChannel):
    name = "webhook"
    display_name = "Webhook"

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return {"enabled": False, "port": 9000, "allowFrom": []}

    async def start(self) -> None:
        self._running = True
        port = self.config.get("port", 9000)

        app = web.Application()
        app.router.add_post("/message", self._on_request)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("Webhook listening on :{}", port)

        while self._running:
            await asyncio.sleep(1)

        await runner.cleanup()

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        logger.info("[webhook] -> {}: {}", msg.chat_id, msg.content[:80])

    async def _on_request(self, request: web.Request) -> web.Response:
        body = await request.json()
        sender = body.get("sender", "unknown")
        chat_id = body.get("chat_id", sender)
        text = body.get("text", "")
        media = body.get("media", [])

        await self._handle_message(
            sender_id=sender,
            chat_id=chat_id,
            content=text,
            media=media,
        )

        return web.json_response({"ok": True})
```

### 2. Register the Entry Point

```toml
[project]
name = "tokenmind-channel-webhook"
version = "0.1.0"
dependencies = ["tokenmind-ai", "aiohttp"]

[project.entry-points."tokenmind.channels"]
webhook = "tokenmind_channel_webhook:WebhookChannel"

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
```

The key (`webhook`) becomes the config section name. The value points to your `BaseChannel` subclass.

### 3. Install and Configure

```bash
pip install -e .
tokenmind plugins list
tokenmind onboard
```

Then edit `~/.tokenmind/config.json`:

```json
{
  "channels": {
    "webhook": {
      "enabled": true,
      "port": 9000,
      "allowFrom": ["*"]
    }
  }
}
```

### 4. Run and Test

```bash
tokenmind gateway
```

In another terminal:

```bash
curl -X POST http://localhost:9000/message ^
  -H "Content-Type: application/json" ^
  -d "{\"sender\":\"user1\",\"chat_id\":\"user1\",\"text\":\"Hello!\"}"
```

## BaseChannel API

### Required

| Method | Description |
|--------|-------------|
| `async start()` | Must keep running until the channel stops. |
| `async stop()` | Cleans up resources and stops the channel. |
| `async send(msg: OutboundMessage)` | Delivers an outbound message to the platform. |

### Provided by BaseChannel

| Method / Property | Description |
|-------------------|-------------|
| `_handle_message(...)` | Validates access and publishes the incoming message to the bus. |
| `is_allowed(sender_id)` | Checks `allowFrom`. |
| `default_config()` | Supplies defaults for `tokenmind onboard`. |
| `transcribe_audio(file_path)` | Transcribes audio if configured. |
| `is_running` | Returns `self._running`. |

## Naming Convention

| What | Format | Example |
|------|--------|---------|
| Distribution name | `tokenmind-channel-{name}` | `tokenmind-channel-webhook` |
| Entry-point group | `tokenmind.channels` | `tokenmind.channels` |
| Entry-point key | `{name}` | `webhook` |
| Config section | `channels.{name}` | `channels.webhook` |
| Python package | `tokenmind_channel_{name}` | `tokenmind_channel_webhook` |

## Local Development

```bash
git clone https://github.com/you/tokenmind-channel-webhook
cd tokenmind-channel-webhook
pip install -e .
tokenmind plugins list
tokenmind gateway
```

## Verify

```bash
$ tokenmind plugins list

  Name       Source    Enabled
  telegram   builtin   yes
  webhook    plugin    yes
  webhook    plugin    yes
```
