#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件访问封装（预留扩展）"""


class FileAccess:
    """文件访问接口（当前为占位，未来支持异步 IO、远程文件等）"""

    @staticmethod
    def read_text(filepath, encoding='utf-8'):
        """读取文本"""
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except Exception:
            return ""

    @staticmethod
    def write_text(filepath, content, encoding='utf-8'):
        """写入文本"""
        try:
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(content)
            return True
        except Exception:
            return False

    @staticmethod
    def read_bytes(filepath):
        """读取字节"""
        try:
            with open(filepath, 'rb') as f:
                return f.read()
        except Exception:
            return b''

    @staticmethod
    def exists(filepath):
        """检查文件是否存在"""
        import os
        return os.path.exists(filepath)