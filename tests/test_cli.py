from __future__ import annotations

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


def test_missing_token_error_guides_user() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["user", "me"])

    assert result.exit_code != 0
    combined_output = result.output + getattr(result, "stderr", "")
    assert "NOCFO_API_TOKEN" in combined_output
    assert "nocfo auth configure" in combined_output
