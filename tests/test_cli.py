from __future__ import annotations

import os

import nocfo_toolkit.cli.app as cli_app_module
from nocfo_toolkit.cli.app import app
from typer.testing import CliRunner


def test_cli_registers_expected_top_level_groups() -> None:
    commands = app.registered_commands
    groups = {group.name for group in app.registered_groups}

    assert any(command.name == "mcp" for command in commands)
    assert "auth" in groups
    assert "businesses" in groups
    assert "accounts" in groups
    assert "documents" in groups
    assert "contacts" in groups
    assert "invoices" in groups
    assert "purchase-invoices" in groups
    assert "products" in groups
    assert "files" in groups
    assert "tags" in groups
    assert "user" in groups


def test_auth_status_never_prints_token() -> None:
    runner = CliRunner()
    token = "pat_super_secret_value"
    result = runner.invoke(
        app, ["--api-token", token, "--output", "json", "auth", "status"]
    )

    assert result.exit_code == 0
    assert token not in result.output


def test_missing_token_error_guides_user(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("NOCFO_API_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", os.path.join(str(tmp_path), ".config"))

    runner = CliRunner()
    result = runner.invoke(app, ["user", "me"])

    assert result.exit_code != 0
    combined_output = result.output + getattr(result, "stderr", "")
    assert "NOCFO_API_TOKEN" in combined_output
    assert "nocfo auth configure" in combined_output


def test_mcp_watch_requires_local_base_url() -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--base-url",
            "https://api-prd.nocfo.io",
            "mcp",
            "--transport",
            "http",
            "--watch",
        ],
    )

    assert result.exit_code != 0
    assert "local backend base URL" in result.output


def test_mcp_watch_delegates_to_watch_runner(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_watch_runner(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(cli_app_module, "_run_mcp_with_watch", _fake_watch_runner)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "--base-url",
            "http://localhost:8000",
            "mcp",
            "--transport",
            "http",
            "--watch",
            "--watch-path",
            "src",
        ],
    )

    assert result.exit_code == 0
    assert captured["transport"] == "http"
    assert captured["watch_paths"] == ["src"]
