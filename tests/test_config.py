from __future__ import annotations

from pathlib import Path

import pytest

from nocfo_toolkit.config import ConfigStore, OutputFormat, TokenSource, load_config


def test_load_config_prefers_explicit_values(tmp_path: Path) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    store.write(
        {
            "api_token": "stored-token",
            "base_url": "https://stored.example",
            "output_format": "json",
        }
    )

    config = load_config(
        api_token="explicit-token",
        base_url="https://explicit.example/",
        output_format="table",
        store=store,
    )

    assert config.api_token == "explicit-token"
    assert config.token_source == TokenSource.CLI
    assert config.base_url == "https://explicit.example"
    assert config.output_format == OutputFormat.TABLE


def test_load_config_uses_store_fallback(tmp_path: Path) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    store.write(
        {
            "api_token": "stored-token",
            "base_url": "https://stored.example/",
            "output_format": "json",
        }
    )

    config = load_config(store=store)

    assert config.api_token == "stored-token"
    assert config.token_source == TokenSource.STORE
    assert config.base_url == "https://stored.example"
    assert config.output_format == OutputFormat.JSON


def test_load_config_prefers_env_over_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    store.write({"api_token": "stored-token"})
    monkeypatch.setenv("NOCFO_API_TOKEN", "env-token")

    config = load_config(store=store)

    assert config.api_token == "env-token"
    assert config.token_source == TokenSource.ENV


def test_load_config_rejects_invalid_token(tmp_path: Path) -> None:
    store = ConfigStore(path=tmp_path / "config.json")

    with pytest.raises(ValueError, match="whitespace"):
        load_config(api_token="bad token", store=store)


def test_load_config_reads_parallel_jwt_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    store.write({"api_token": "stored-pat"})
    monkeypatch.setenv("NOCFO_JWT_TOKEN", "jwt-token-value")

    config = load_config(store=store)

    assert config.api_token == "stored-pat"
    assert config.jwt_token == "jwt-token-value"
    assert config.token_source == TokenSource.STORE


def test_load_config_rejects_invalid_jwt_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    monkeypatch.setenv("NOCFO_JWT_TOKEN", "bad jwt token")

    with pytest.raises(ValueError, match="JWT token cannot contain whitespace"):
        load_config(store=store)


def test_load_config_reads_nocfo_client_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    monkeypatch.setenv("NOCFO_CLIENT", "my-mcp-agent/1.0")

    config = load_config(store=store)

    assert config.nocfo_client == "my-mcp-agent/1.0"


def test_load_config_passes_through_nocfo_client_env_without_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ConfigStore(path=tmp_path / "config.json")
    monkeypatch.setenv("NOCFO_CLIENT", "custom mcp")

    config = load_config(store=store)

    assert config.nocfo_client == "custom mcp"
