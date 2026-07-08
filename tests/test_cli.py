"""Tests for the CLI entry point."""

from __future__ import annotations

import pytest

from doc_analyzer.cli import main


class TestCli:
    def test_no_args_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "doc_analyzer" in captured.out

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["--version"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "doc_analyzer" in captured.out

    def test_short_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["-v"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "doc_analyzer" in captured.out
