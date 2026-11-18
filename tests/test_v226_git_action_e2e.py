# -*- coding: utf-8 -*-
"""v2.26 P1：git_deep 动作 e2e（临时 Git 仓库夹具）"""

import os
import subprocess


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _git(repo, *args):
    return subprocess.run(
        ["git"] + list(args), cwd=repo, capture_output=True, text=True, timeout=30
    )


def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(str(repo), "init").returncode == 0
    _git(str(repo), "config", "user.email", "test@example.com")
    _git(str(repo), "config", "user.name", "Test")
    f = repo / "a.txt"
    f.write_text("one\n", encoding="utf-8")
    assert _git(str(repo), "add", ".").returncode == 0
    assert _git(str(repo), "commit", "-m", "init").returncode == 0
    f.write_text("one\ntwo\n", encoding="utf-8")
    return repo, f


class _API:
    def __init__(self, repo):
        self.repo = repo
        self.path = str(repo / "a.txt")

    def git_branch(self, path):
        return _git(self.repo, "branch", "--show-current").stdout.strip()

    def git_status(self, path):
        return {"raw": _git(self.repo, "status", "--porcelain").stdout}

    def git_diff(self, path, staged=False):
        args = ["diff"] + (["--cached"] if staged else [])
        return _git(self.repo, *args).stdout

    def git_log(self, path, limit=30):
        return _git(self.repo, "log", "--oneline", "-%d" % limit).stdout


def test_git_deep_actions_on_real_repo(tmp_path):
    from plugins.git_deep import _HostGit

    repo, f = _make_repo(tmp_path)
    host = _HostGit(_API(repo), str(f))
    assert host.current_branch() in ("master", "main")
    assert "a.txt" in str(host.status())
    diff = host.diff()
    assert "+two" in diff
    assert "init" in host.log()
