# -*- coding: utf-8 -*-
"""多根工作区"""
import os
import json
from typing import List, Dict, Optional, Any


WORKSPACE_FILE = "workspace.json"
WORKSPACE_EXT = ".qingcao-workspace"


class WorkspaceFolder:
    """工作区文件夹"""

    def __init__(self, path, name=""):
        self.path = os.path.abspath(path)
        self.name = name or os.path.basename(self.path)
        self.expanded = True


class Workspace:
    """工作区"""

    def __init__(self):
        self.folders: List[WorkspaceFolder] = []
        self.name = "未命名工作区"
        self.filepath = ""

    def add_folder(self, path, name="") -> bool:
        """添加文件夹"""
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return False

        for f in self.folders:
            if f.path == path:
                return False

        self.folders.append(WorkspaceFolder(path, name))
        return True

    def remove_folder(self, path) -> bool:
        """移除文件夹"""
        path = os.path.abspath(path)
        for i, f in enumerate(self.folders):
            if f.path == path:
                del self.folders[i]
                return True
        return False

    def has_folder(self, path) -> bool:
        """是否有某文件夹"""
        path = os.path.abspath(path)
        return any(f.path == path for f in self.folders)

    def clear(self):
        """清空"""
        self.folders.clear()

    def get_folder_for_file(self, filepath) -> Optional[WorkspaceFolder]:
        """找到文件所属的文件夹"""
        filepath = os.path.abspath(filepath)
        best = None
        best_len = 0
        for f in self.folders:
            if filepath.startswith(f.path):
                if len(f.path) > best_len:
                    best = f
                    best_len = len(f.path)
        return best

    def to_dict(self):
        return {
            'name': self.name,
            'folders': [
                {'path': f.path, 'name': f.name}
                for f in self.folders
            ],
        }

    @classmethod
    def from_dict(cls, d):
        ws = cls()
        ws.name = d.get('name', '未命名工作区')
        for fd in d.get('folders', []):
            ws.add_folder(fd.get('path', ''), fd.get('name', ''))
        return ws

    def save(self, filepath):
        """保存"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f,
                          indent=2, ensure_ascii=False)
            self.filepath = filepath
            return True
        except Exception:
            return False

    @classmethod
    def load(cls, filepath):
        """加载"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                d = json.load(f)
            ws = cls.from_dict(d)
            ws.filepath = filepath
            return ws
        except Exception:
            return None

    def is_empty(self):
        return len(self.folders) == 0

    def __repr__(self):
        return "<Workspace folders=%d>" % len(self.folders)