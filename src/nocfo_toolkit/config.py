"""Configuration management for NoCFO toolkit."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments

    def load_dotenv(*args, **kwargs):  # type: ignore[no-redef]
        return False


DEFAULT_BASE_URL = "https://api-prd.nocfo.io"
AUTH_HEADER_SCHEME = "Token"
MIN_PAT_LENGTH = 8


class OutputFormat(str, Enum):
    """Supported output formats for CLI commands."""

    TABLE = "table"
    JSON = "json"


class TokenSource(str, Enum):
    """Where the API token was resolved from."""

    CLI = "cli"
    ENV = "env"
    STORE = "store"
    MISSING = "missing"


@dataclass(frozen=True)
class ToolkitConfig:
    """Resolved toolkit configuration."""

    api_token: str | None = None
    token_source: TokenSource = TokenSource.MISSING
    base_url: str = DEFAULT_BASE_URL
    output_format: OutputFormat = OutputFormat.TABLE
    jwt_token: str | None = None
    nocfo_client: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.api_token or self.jwt_token)


class ConfigStore:
    """Persist and read local CLI configuration."""

    def __init__(self, path: Path | None = None) -> None:
        default_path = Path.home() / ".config" / "nocfo-cli" / "config.json"
        self.path = path or default_path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Keep local token storage user-private.
        self.path.chmod(0o600)

    def set_token(self, token: str) -> None:
        config = self.read()
        config["api_token"] = token.strip()
        self.write(config)

    def set_base_url(self, base_url: str) -> None:
        config = self.read()
        config["base_url"] = base_url.rstrip("/")
        self.write(config)

    def clear_token(self) -> None:
        config = self.read()
        config.pop("api_token", None)
        self.write(config)


def _to_output_format(value: str | None) -> OutputFormat:
    if not value:
        return OutputFormat.TABLE
    normalized = value.strip().lower()
    if normalized == OutputFormat.JSON.value:
        return OutputFormat.JSON
    return OutputFormat.TABLE


def sanitize_api_token(value: str | None) -> str | None:
    """Normalize and lightly validate PAT token shape."""

    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    if any(ch.isspace() for ch in token):
        raise ValueError("API token cannot contain whitespace characters.")
    if len(token) < MIN_PAT_LENGTH:
        raise ValueError(
            f"API token looks too short (minimum {MIN_PAT_LENGTH} characters expected)."
        )
    return token


def sanitize_jwt_token(value: str | None) -> str | None:
    """Normalize JWT token from environment."""

    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    if any(ch.isspace() for ch in token):
        raise ValueError("JWT token cannot contain whitespace characters.")
    return token


def sanitize_nocfo_client(value: str | None) -> str | None:
    """Pass through optional x-nocfo-client value as-is."""
    return value


def _resolve_token(
    *,
    cli_token: str | None,
    env_token: str | None,
    stored_token: str | None,
) -> tuple[str | None, TokenSource]:
    if cli_token:
        return cli_token, TokenSource.CLI
    if env_token:
        return env_token, TokenSource.ENV
    if stored_token:
        return stored_token, TokenSource.STORE
    return None, TokenSource.MISSING


def load_config(
    *,
    api_token: str | None = None,
    base_url: str | None = None,
    output_format: str | None = None,
    env_file: str | None = None,
    store: ConfigStore | None = None,
) -> ToolkitConfig:
    """Resolve config precedence: CLI > env > stored config > defaults."""

    load_dotenv(dotenv_path=env_file, override=False)
    store = store or ConfigStore()
    stored = store.read()

    raw_token, token_source = _resolve_token(
        cli_token=api_token,
        env_token=os.getenv("NOCFO_API_TOKEN"),
        stored_token=stored.get("api_token"),
    )
    resolved_token = sanitize_api_token(raw_token)
    resolved_jwt_token = sanitize_jwt_token(os.getenv("NOCFO_JWT_TOKEN"))
    resolved_nocfo_client = sanitize_nocfo_client(os.getenv("NOCFO_CLIENT"))
    resolved_base_url = (
        base_url
        or os.getenv("NOCFO_BASE_URL")
        or stored.get("base_url")
        or DEFAULT_BASE_URL
    ).rstrip("/")
    resolved_output = _to_output_format(
        output_format or os.getenv("NOCFO_OUTPUT_FORMAT") or stored.get("output_format")
    )

    return ToolkitConfig(
        api_token=resolved_token,
        token_source=token_source if resolved_token else TokenSource.MISSING,
        base_url=resolved_base_url,
        output_format=resolved_output,
        jwt_token=resolved_jwt_token,
        nocfo_client=resolved_nocfo_client,
    )
