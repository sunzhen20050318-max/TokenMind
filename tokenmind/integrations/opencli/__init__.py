"""OpenCLI integration: install detection + subprocess service."""

from tokenmind.integrations.opencli.detector import (
    DEFAULT_DAEMON_PORT,
    PINNED_OPENCLI_VERSION,
    detect_installation,
    install_opencli,
    installation_to_dict,
)
from tokenmind.integrations.opencli.service import FEATURED_SITES, OpenCLIService
from tokenmind.integrations.opencli.site_registry import (
    SiteEntry,
    SiteRegistry,
    hostname_from_url,
)
from tokenmind.integrations.opencli.types import (
    InstallStep,
    OpencliInstallation,
    ProfileInfo,
    RiskLevel,
    RunResult,
    SiteCommand,
    SiteInfo,
)

__all__ = [
    "DEFAULT_DAEMON_PORT",
    "FEATURED_SITES",
    "PINNED_OPENCLI_VERSION",
    "InstallStep",
    "OpenCLIService",
    "OpencliInstallation",
    "ProfileInfo",
    "RiskLevel",
    "RunResult",
    "SiteCommand",
    "SiteEntry",
    "SiteInfo",
    "SiteRegistry",
    "detect_installation",
    "hostname_from_url",
    "install_opencli",
    "installation_to_dict",
]
