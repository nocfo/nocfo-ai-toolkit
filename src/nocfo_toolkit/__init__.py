"""NoCFO AI Toolkit package."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("nocfo-cli")
except PackageNotFoundError:  # pragma: no cover - local editable fallback
    __version__ = "0.0.0"
