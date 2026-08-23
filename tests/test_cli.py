"""
Unit tests for Typer CLI commands and terminal table renderers.
"""

import os
import tempfile
import pytest
from typer.testing import CliRunner
from fincontroller.cli.main import app

runner = CliRunner()


def test_cli_benchmark_command():
    result = runner.invoke(app, ["benchmark", "--seed", "42"])
    assert result.exit_code == 0
    assert "Benchmark Evaluation Metrics" in result.output
    assert "Match Rate:" in result.output
    assert "Unresolved Exceptions" in result.output


def test_cli_reconcile_command():
    result = runner.invoke(
        app,
        ["reconcile", "data/sample_razorpay_settlements.csv", "data/sample_bank_statement.csv"],
    )
    assert result.exit_code == 0
    assert "Reconciliation Summary" in result.output
    assert "Match Rate" in result.output
    assert "Unresolved Exceptions" in result.output


def test_cli_verify_audit_command():
    result = runner.invoke(app, ["verify-audit"])
    assert result.exit_code == 0
    assert "PASSED" in result.output
    assert "Tamper-Evident Audit Verification" in result.output


def test_cli_ask_command():
    result = runner.invoke(app, ["ask", "Why did pay_AMBIG_DUP_00_A need human review?"])
    assert result.exit_code == 0
    assert "AI Finance Controller Copilot" in result.output
