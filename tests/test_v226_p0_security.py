# -*- coding: utf-8 -*-
"""v2.26 P0：git 白名单 + AI 隐私/取消"""

import subprocess
import types

import pytest


def test_git_subcommand_whitelist(monkeypatch):
    from core.git_client import ALLOWED_SUBCOMMANDS, GitClient

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    code, out, err = GitClient(".")._run(["arbitrary", "--help"])
    assert code == -1 and "not allowed" in err and not calls

    code, out, err = GitClient(".")._run(["status", "--porcelain"])
    assert code == 0 and out == "ok"
    assert calls and calls[0][1].get("shell") is False
    assert calls[0][1].get("timeout") == 15
    assert "status" in ALLOWED_SUBCOMMANDS


def test_git_output_truncated(monkeypatch):
    from core import git_client

    big = "x" * (git_client.MAX_OUTPUT_CHARS + 10)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(returncode=0, stdout=big, stderr=""),
    )
    code, out, err = git_client.GitClient(".")._run(["status"])
    assert len(out) == git_client.MAX_OUTPUT_CHARS


def test_ai_privacy_mode_blocks_network():
    from core.ai_client import AIClient, AIConfigError

    client = AIClient(api_key="x", privacy_mode=True)
    with pytest.raises(AIConfigError):
        client._make_request("https://api.example.com", {}, {})


def test_ai_cancel_blocks_request():
    from core.ai_client import AICancelledError, AIClient

    client = AIClient(api_key="x")
    client.cancel()
    with pytest.raises(AICancelledError):
        client._make_request("https://api.example.com", {}, {})


def test_ai_config_dialog_has_privacy_toggle():
    src = open("plugins/ai_assistant/ai_config_dialog.py", encoding="utf-8").read()
    assert "privacy_check" in src and "privacy_mode" in src
