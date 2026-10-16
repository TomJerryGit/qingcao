# -*- coding: utf-8 -*-
"""协议正确性审计测试：git_client / file_merge / sync / plugin_store

本文件的用例记录曾经的协议层缺陷（详见 `docs/audit_protocols.md`）。
这些缺陷**已全部修复**，用例已正式纳入常规测试套件
（不再标记 `audit_expected_fail`，也不再被 `addopts` 排除）。

运行::

    python -m pytest tests/test_audit_protocols.py -v
"""
import os
import subprocess
import sys
import zipfile

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.file_merge import ThreeWayMerger  # noqa: E402
from core.git_client import GitClient  # noqa: E402


# =========================================================
# file_merge —— 当前仓库里没有任何 file_merge 测试
# =========================================================

class TestThreeWayMerge:
    """F1/F2：合并必须不丢内容，且保持末尾换行"""

    def test_append_on_both_sides_is_preserved(self):
        """F1：双方都在末尾追加时，两侧内容都应出现（或记为冲突）

        实测当前实现返回 'a\\nb'，两侧追加全部丢失且 conflicts 为空。
        """
        r = ThreeWayMerger.merge(
            "a\nb\n",
            "a\nb\nLOCAL_NEW\n",
            "a\nb\nREMOTE_NEW\n",
        )
        merged = r['merged']
        assert ('LOCAL_NEW' in merged and 'REMOTE_NEW' in merged) or r['conflicts'], (
            "末尾追加被静默丢弃且未记为冲突: merged=%r conflicts=%r"
            % (merged, r['conflicts'])
        )

    def test_append_one_side_with_other_edit_is_preserved(self):
        """F1：本地末尾追加 + 远程改首行 → 两者都要保留"""
        r = ThreeWayMerger.merge(
            "a\nb\n",
            "a\nb\nLOCAL_TAIL\n",
            "REMOTE_A\nb\n",
        )
        assert 'LOCAL_TAIL' in r['merged'] and 'REMOTE_A' in r['merged'], (
            "本地的末尾追加丢失: merged=%r" % r['merged']
        )

    def test_trailing_newline_preserved(self):
        """F2：合并结果应保持末尾换行

        实测当前实现把 'line1\\n...\\nline4\\n' 合并成 '...\\nREMOTE'（丢了末尾换行）。
        """
        r = ThreeWayMerger.merge(
            "line1\nline2\nline3\nline4\n",
            "LOCAL\nline2\nline3\nline4\n",
            "line1\nline2\nline3\nREMOTE\n",
        )
        assert r['merged'].endswith("\n"), (
            "合并后末尾换行丢失: %r" % r['merged']
        )

    def test_single_side_change_takes_that_side(self):
        """对照组：只有一方改动时应直接采用该方（当前实现正确）"""
        r = ThreeWayMerger.merge("a\nb\n", "a\nLOCAL\n", "a\nb\n")
        assert r['merged'] == "a\nLOCAL\n"
        assert r['strategy'] == 'keep_local'


# =========================================================
# git_client —— 真实仓库上的路径解析
# =========================================================

def _init_repo(path):
    def g(*a):
        return subprocess.run(['git'] + list(a), cwd=path, capture_output=True,
                              text=True, encoding='utf-8', errors='replace')
    g('init', '-q')
    g('config', 'user.email', 't@t.t')
    g('config', 'user.name', 't')
    return g


class TestGitClientPaths:
    """F3：porcelain 输出对含空格/非 ASCII 的路径会加引号或转义"""

    def test_status_parses_path_with_space(self, tmp_path):
        """F3：含空格的路径应能被解析成真实存在的路径"""
        _init_repo(str(tmp_path))
        name = "with space.txt"
        (tmp_path / name).write_text("x\n", encoding="utf-8")

        st = GitClient(str(tmp_path)).status()
        assert name in st, (
            "含空格路径解析失败: 解析键=%r（含字面引号）"
            % [k for k in st]
        )
        assert os.path.exists(os.path.join(str(tmp_path), name))

    def test_status_parses_non_ascii_path(self, tmp_path):
        """F3：非 ASCII 路径（git 默认 core.quotePath=true 会转义）"""
        g = _init_repo(str(tmp_path))
        name = "中文名字.txt"
        (tmp_path / name).write_text("x\n", encoding="utf-8")
        g('config', 'core.quotePath', 'true')     # git 默认值

        st = GitClient(str(tmp_path)).status()
        assert name in st, (
            "非 ASCII 路径解析失败: 解析键=%r" % [k for k in st]
        )

    def test_find_root_in_worktree(self, tmp_path):
        """F4：git worktree 的 .git 是文件，find_root 应仍能识别"""
        repo = tmp_path / "repo"
        repo.mkdir()
        g = _init_repo(str(repo))
        (repo / "a.txt").write_text("x\n", encoding="utf-8")
        g('add', '-A')
        g('commit', '-q', '-m', 'init')

        wt = tmp_path / "wt"
        r = subprocess.run(['git', 'worktree', 'add', str(wt), '-b', 'wtb'],
                           cwd=str(repo), capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        if r.returncode != 0:
            pytest.skip("worktree 创建失败: %s" % r.stderr[:120])

        assert os.path.isfile(str(wt / ".git")), "前提：worktree 的 .git 应为文件"
        found = GitClient(str(wt)).find_root(str(wt / "x.txt"))
        assert found is not None, (
            "find_root 未识别 worktree（返回 None），期望 %s" % wt
        )
