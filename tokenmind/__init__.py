"""
TokenMind - A lightweight AI agent framework
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("tokenmind-ai")
except PackageNotFoundError:  # editable install before metadata is generated
    __version__ = "0.0.0+dev"

__logo__ = "☀️"
