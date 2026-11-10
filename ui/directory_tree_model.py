# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""目录树模型（v2.24 拆出）。"""

from ui.directory_tree_common import *


class DirectoryTreeModel:
    """
    目录树数据模型。

    管理目录树的数据结构，负责:
    - 目录扫描与缓存
    - 路径信息查询
    - 文件过滤
    """

    def __init__(self):
        self.root_path: str = ""
        self.exclude_dirs: Set[str] = set(DEFAULT_EXCLUDE_DIRS)
        self.exclude_patterns: List[str] = []
        self.show_hidden: bool = False
        self.follow_symlinks: bool = False
        self._dir_cache: Dict[str, List[str]] = {}

    # --------------------------------------------------------
    # 根目录
    # --------------------------------------------------------
    def set_root(self, path: str):
        """设置根目录"""
        self.root_path = os.path.abspath(path) if path else ""
        self._dir_cache.clear()

    def get_root(self) -> str:
        """获取根目录"""
        return self.root_path

    # --------------------------------------------------------
    # 目录扫描
    # --------------------------------------------------------
    def list_directory(self, path: str, use_cache: bool = False) -> List[Tuple[str, bool]]:
        """
        列出目录内容。

        参数:
            path: 目录路径
            use_cache: 是否使用缓存

        返回:
            [(名称, 是否目录), ...] 已排序
        """
        if use_cache and path in self._dir_cache:
            return self._dir_cache[path]

        result = []

        try:
            entries = os.listdir(path)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            return result

        dirs = []
        files = []

        for name in entries:
            # 隐藏文件过滤
            if not self.show_hidden and name.startswith("."):
                continue

            # 排除目录
            if name in self.exclude_dirs:
                continue

            # 排除模式
            if self._matches_exclude(name):
                continue

            full_path = os.path.join(path, name)

            try:
                is_dir = os.path.isdir(full_path)

                # 符号链接处理
                if os.path.islink(full_path):
                    if not self.follow_symlinks:
                        # 符号链接显示为文件
                        is_dir = False

                if is_dir:
                    dirs.append(name)
                else:
                    files.append(name)

            except OSError:
                continue

        # 排序：目录优先，然后按名称
        dirs.sort(key=str.lower)
        files.sort(key=str.lower)

        for d in dirs:
            result.append((d, True))
        for f in files:
            result.append((f, False))

        if use_cache:
            self._dir_cache[path] = result

        return result

    def _matches_exclude(self, name: str) -> bool:
        """检查是否匹配排除模式"""
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    # --------------------------------------------------------
    # 文件信息
    # --------------------------------------------------------
    def get_file_info(self, path: str) -> Dict[str, Any]:
        """获取文件信息"""
        try:
            stat = os.stat(path)
            return {
                "path": path,
                "name": os.path.basename(path),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "ctime": stat.st_ctime,
                "is_dir": os.path.isdir(path),
                "is_file": os.path.isfile(path),
                "is_link": os.path.islink(path),
                "readable": os.access(path, os.R_OK),
                "writable": os.access(path, os.W_OK),
                "executable": os.access(path, os.X_OK),
            }
        except OSError:
            return {}

    def get_relative_path(self, full_path: str) -> str:
        """获取相对于根目录的路径"""
        if not self.root_path:
            return full_path
        try:
            return os.path.relpath(full_path, self.root_path)
        except ValueError:
            return full_path

    def get_depth(self, path: str) -> int:
        """获取路径深度"""
        if not self.root_path:
            return 0
        rel = self.get_relative_path(path)
        if rel == ".":
            return 0
        return rel.count(os.sep) + 1

    # --------------------------------------------------------
    # 清理
    # --------------------------------------------------------
    def clear_cache(self):
        """清空缓存"""
        self._dir_cache.clear()

    def clear_cache_for(self, path: str):
        """清空指定路径的缓存"""
        self._dir_cache.pop(path, None)


# ============================================================
# 目录树面板
# ============================================================
