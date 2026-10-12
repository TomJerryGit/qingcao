#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目对象"""
import json
import os


class Project:
    """青草项目"""

    def __init__(self, name="", root_path="", files=None, active_file=None):
        self.name = name
        self.root_path = root_path
        self.files = files or []
        self.active_file = active_file

    def to_dict(self):
        """序列化"""
        return {
            'name': self.name,
            'root_path': self.root_path,
            'files': self.files,
            'active_file': self.active_file,
        }

    @classmethod
    def from_dict(cls, d):
        """反序列化"""
        return cls(
            d.get('name', ''),
            d.get('root_path', ''),
            d.get('files', []),
            d.get('active_file'),
        )

    def save(self, filepath):
        """保存到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or '.',
                        exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Project] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath):
        """从文件加载"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"[Project] 加载失败: {e}")
            return None