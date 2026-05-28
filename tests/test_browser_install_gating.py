"""OpenCLI one-click install + browser-tool availability gating."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tokenmind.agent.tools.browser import BrowserTool
from tokenmind.audit import AuditLogger
from tokenmind.integrations.opencli import (
    PINNED_OPENCLI_VERSION,
    OpenCLIService,
    install_opencli,
)


def _tool(tmp_path: Path) -> BrowserTool:
    return BrowserTool(service=OpenCLIService(audit=AuditLogger(tmp_path)))


class TestAvailabilityGating:
    def test_hidden_when_opencli_missing(self, tmp_path: Path) -> None:
        tool = _tool(tmp_path)
        with patch("tokenmind.agent.tools.browser.shutil.which", return_value=None):
            assert tool.is_available() is False

    def test_visible_when_opencli_present(self, tmp_path: Path) -> None:
        tool = _tool(tmp_path)
        with patch(
            "tokenmind.agent.tools.browser.shutil.which",
            return_value="/usr/local/bin/opencli",
        ):
            assert tool.is_available() is True

    def test_availability_cached_within_ttl(self, tmp_path: Path) -> None:
        tool = _tool(tmp_path)
        with patch(
            "tokenmind.agent.tools.browser.shutil.which",
            return_value="/usr/local/bin/opencli",
        ) as which:
            assert tool.is_available() is True
            assert tool.is_available() is True  # cached, no second scan
            assert which.call_count == 1

    def test_registry_filters_unavailable_browser_tool(self, tmp_path: Path) -> None:
        from tokenmind.agent.tools.registry import ToolRegistry

        reg = ToolRegistry()
        tool = _tool(tmp_path)
        reg.register(tool)
        with patch("tokenmind.agent.tools.browser.shutil.which", return_value=None):
            names = [d["function"]["name"] for d in reg.get_definitions()]
            assert "browser" not in names
        # New tool instance to bypass the TTL cache of the first one.
        reg2 = ToolRegistry()
        reg2.register(_tool(tmp_path))
        with patch(
            "tokenmind.agent.tools.browser.shutil.which",
            return_value="/usr/local/bin/opencli",
        ):
            names = [d["function"]["name"] for d in reg2.get_definitions()]
            assert "browser" in names


class TestInstallOpencli:
    @pytest.mark.asyncio
    async def test_fails_without_npm(self) -> None:
        with patch("tokenmind.integrations.opencli.detector.shutil.which", return_value=None):
            ok, msg = await install_opencli()
        assert ok is False
        assert "npm" in msg.lower()

    @pytest.mark.asyncio
    async def test_installs_pinned_version(self) -> None:
        captured = {}

        async def fake_run(cmd, timeout=240.0):
            captured["cmd"] = cmd
            return 0, "added 1 package", ""

        with (
            patch(
                "tokenmind.integrations.opencli.detector.shutil.which",
                return_value="/usr/bin/npm",
            ),
            patch("tokenmind.integrations.opencli.detector._run", side_effect=fake_run),
        ):
            ok, msg = await install_opencli()

        assert ok is True
        assert captured["cmd"] == [
            "npm",
            "install",
            "-g",
            f"@jackwener/opencli@{PINNED_OPENCLI_VERSION}",
        ]

    @pytest.mark.asyncio
    async def test_reports_npm_failure(self) -> None:
        async def fake_run(cmd, timeout=240.0):
            return 1, "", "EACCES: permission denied"

        with (
            patch(
                "tokenmind.integrations.opencli.detector.shutil.which",
                return_value="/usr/bin/npm",
            ),
            patch("tokenmind.integrations.opencli.detector._run", side_effect=fake_run),
        ):
            ok, msg = await install_opencli()

        assert ok is False
        assert "EACCES" in msg


class TestInstallRoute:
    @pytest.mark.asyncio
    async def test_install_endpoint_returns_status(self, tmp_path: Path) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from tokenmind.server.dependencies import set_opencli_service
        from tokenmind.server.routes.browser import router

        service = OpenCLIService(audit=AuditLogger(tmp_path))
        service.detect = AsyncMock(  # type: ignore[method-assign]
            return_value=__import__(
                "tokenmind.integrations.opencli.types", fromlist=["OpencliInstallation"]
            ).OpencliInstallation(
                opencli_installed=True,
                opencli_version="1.8.0",
                opencli_path="/usr/local/bin/opencli",
                node_installed=True,
                node_version="22.0.0",
                node_ok=True,
                daemon_port=19825,
                daemon_running=False,
                profiles=[],
                missing_steps=[],
                ready=False,
                last_error=None,
            )
        )
        set_opencli_service(service)

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        with patch(
            "tokenmind.server.routes.browser.install_opencli",
            new=AsyncMock(return_value=(True, "added 1 package")),
        ):
            r = client.post("/api/browser/install")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["version"] == PINNED_OPENCLI_VERSION
        assert body["status"]["opencli"]["installed"] is True
