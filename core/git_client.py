# -*- coding: utf-8 -*-
"""Git 客户端封装"""
import os
import subprocess
from typing import List, Dict, Optional, Tuple


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

    def is_repo(self) -> bool:
        """是否为 Git 仓库"""
        code, out, _ = self._run(['rev-parse', '--git-dir'])
        return code == 0

    def find_root(self, filepath) -> Optional[str]:
        """从文件路径找到 Git 根目录"""
        dirpath = filepath if os.path.isdir(filepath) else os.path.dirname(filepath)
        while dirpath != os.path.dirname(dirpath):
            if os.path.isdir(os.path.join(dirpath, '.git')):
                return dirpath
            dirpath = os.path.dirname(dirpath)
        return None

    def status(self) -> Dict[str, str]:
        """获取所有文件的 Git 状态"""
        code, out, _ = self._run(['status', '--porcelain'])
        if code != 0:
            return {}

        result = {}
        for line in out.splitlines():
            if len(line) < 4:
                continue
            status = line[:2]
            filepath = line[3:].strip()
            result[filepath] = status
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