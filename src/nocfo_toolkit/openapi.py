"""OpenAPI fetch and cache helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

CACHE_PATH = Path.home() / ".cache" / "nocfo-cli" / "openapi.json"


def load_openapi_spec(
    *,
    base_url: str,
    openapi_path: str = "/openapi/",
    cache_path: Path | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Load OpenAPI spec from API with local cache fallback."""

    cache = cache_path or CACHE_PATH
    url = f"{base_url.rstrip('/')}/{openapi_path.strip('/')}/"

    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
        spec = response.json()
        _write_cache(cache, spec)
        return spec
    except (httpx.HTTPError, ValueError):
        cached = _read_cache(cache)
        if cached is not None:
            return cached
        raise RuntimeError(
            "Failed to load OpenAPI spec from network and no local cache exists."
        )


def filter_mcp_spec(spec: dict[str, Any], mcp_tag: str = "MCP") -> dict[str, Any]:
    """Return spec containing only operations tagged as MCP."""

    filtered_paths: dict[str, Any] = {}
    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        kept_methods: dict[str, Any] = {}
        for method, meta in methods.items():
            if not isinstance(meta, dict):
                continue
            tags = meta.get("tags", [])
            if mcp_tag in tags:
                kept_methods[method] = meta
        if kept_methods:
            filtered_paths[path] = kept_methods

    filtered = dict(spec)
    filtered["paths"] = filtered_paths
    return filtered


def _write_cache(path: Path, spec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec), encoding="utf-8")


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
