# -*- coding: utf-8 -*-
"""Git 客户端封装"""
import os
import subprocess
from typing import Dict, List, Optional, Tuple


class GitClient:
    """Git 命令封装"""

    def __init__(self, root_path=""):
        self.root_path = root_path

    def _run(self, args, cwd=None):
        """执行 git 命令"""
        cwd = cwd or self.root_path
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='replace'
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)

    def _run_raw(self, args, cwd=None):
        """执行 git 命令并返回**原始字节**（用于 -z 输出）

        `_run` 用 `text=True` 解码后再按行切分，遇到 NUL 分隔输出（-z）
        时信息会丢失，因此单独提供字节版。
        """
        cwd = cwd or self.root_path
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=cwd,
                capture_output=True,
                timeout=10,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, b"", str(e).encode("utf-8", "replace")

    def is_repo(self) -> bool:
        """是否为 Git 仓库"""
        code, out, _ = self._run(['rev-parse', '--git-dir'])
        return code == 0

    def find_root(self, filepath) -> Optional[str]:
        """从文件路径找到 Git 根目录

        修复（worktree 场景）：
            原先只判断 `os.path.isdir(<d>/.git)`。在 **git worktree /
            submodule** 中 `.git` 是一个**文件**（内容形如
            `gitdir: /path/.git/worktrees/xxx`），`isdir` 为假 →
            找不到仓库根 → 该路径上的 Git 功能全部失效。

            现优先用 `git rev-parse --show-toplevel`（git 自己的权威判定，
            正确处理 worktree / submodule / 符号链接），失败再退化为
            向上查找 `.git`（用 `exists` 而非 `isdir`）。
        """
        if not filepath:
            return None
        start = (filepath if os.path.isdir(filepath)
                 else os.path.dirname(filepath))
        if not start:
            return None

        try:
            code, out, _ = self._run(
                ['rev-parse', '--show-toplevel'], cwd=start
            )
            if code == 0:
                root = (out or "").strip()
                if root and os.path.isdir(root):
                    return os.path.normpath(root)
        except Exception:
            pass

        dirpath = os.path.abspath(start)
        while True:
            if os.path.exists(os.path.join(dirpath, '.git')):
                return dirpath
            parent = os.path.dirname(dirpath)
            if parent == dirpath:
                return None
            dirpath = parent

    def status(self) -> Dict[str, str]:
        """获取所有文件的 Git 状态

        修复（F3，含空格 / 中文路径解析失败）：
            原先解析 `git status --porcelain` 的**文本**输出，直接
            `line[3:].strip()` 当路径。git 对这类路径会**加引号并做八进制
            转义**：

                "with space.txt"          （含空格：加引号）
                "\\344\\270\\255..."       （非 ASCII：core.quotePath）

            于是字典的键变成带引号/转义的字符串，与真实路径对不上 ——
            调用方按真实路径查状态永远查不到。

            现改用 `-z`（NUL 分隔）：该模式下 git **不做任何转义或引用**，
            路径是原始字节，从根上消除歧义；并正确跳过重命名条目的
            源路径字段（-z 下 rename 会多带一条记录）。
        """
        code, raw, _ = self._run_raw(['status', '--porcelain', '-z'])
        if code != 0 or not raw:
            return self._status_text_fallback()

        result: Dict[str, str] = {}
        fields = raw.split(b'\x00')
        idx = 0
        while idx < len(fields):
            entry = fields[idx]
            idx += 1
            if len(entry) < 4:
                continue
            st = entry[:2].decode('utf-8', 'replace')
            path_bytes = entry[3:]
            if not path_bytes:
                continue
            path = path_bytes.decode('utf-8', 'surrogateescape')
            result[path] = st
            # R/C：紧随其后的是源路径，跳过
            if st[:1] in ('R', 'C') and idx < len(fields):
                idx += 1
        return result

    def _status_text_fallback(self) -> Dict[str, str]:
        """文本解析回退：至少正确去掉引号与八进制转义"""
        code, out, _ = self._run(['status', '--porcelain'])
        if code != 0:
            return {}
        result: Dict[str, str] = {}
        for line in out.splitlines():
            if len(line) < 4:
                continue
            st = line[:2]
            path = line[3:].strip()
            if ' -> ' in path:
                path = path.split(' -> ', 1)[1].strip()
            if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
                body = path[1:-1]
                try:
                    body = body.encode('utf-8').decode('unicode_escape')
                except Exception:
                    try:
                        body = body.encode('latin-1', 'backslashreplace').decode(
                            'unicode_escape')
                    except Exception:
                        pass
                path = body
            result[path] = st
        return result

    def current_branch(self) -> str:
        """当前分支"""
        code, out, _ = self._run(['rev-parse', '--abbrev-ref', 'HEAD'])
        if code == 0:
            return out.strip()
        return ""

    def diff(self, filepath) -> str:
        """获取文件差异"""
        code, out, _ = self._run(['diff', filepath])
        return out if code == 0 else ""

    def diff_staged(self, filepath) -> str:
        """暂存区差异"""
        code, out, _ = self._run(['diff', '--cached', filepath])
        return out if code == 0 else ""

    def add(self, filepath) -> bool:
        """暂存文件"""
        code, _, _ = self._run(['add', filepath])
        return code == 0

    def reset(self, filepath) -> bool:
        """取消暂存"""
        code, _, _ = self._run(['reset', 'HEAD', filepath])
        return code == 0

    def commit(self, message) -> Tuple[bool, str]:
        """提交"""
        code, out, err = self._run(['commit', '-m', message])
        return code == 0, err or out

    def push(self, remote='origin', branch='') -> Tuple[bool, str]:
        """推送"""
        args = ['push']
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)
        code, out, err = self._run(args)
        return code == 0, err or out

    def pull(self, remote='origin') -> Tuple[bool, str]:
        """拉取"""
        code, out, err = self._run(['pull', remote])
        return code == 0, err or out

    def log(self, limit=20) -> List[Dict[str, str]]:
        """最近提交"""
        code, out, _ = self._run([
            'log', '--oneline', '-n', str(limit),
            '--format=%h|%s|%an|%ar'
        ])
        if code != 0:
            return []
        result = []
        for line in out.splitlines():
            parts = line.split('|', 3)
            if len(parts) == 4:
                result.append({
                    'hash': parts[0],
                    'message': parts[1],
                    'author': parts[2],
                    'when': parts[3],
                })
        return result