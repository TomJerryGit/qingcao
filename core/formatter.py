# -*- coding: utf-8 -*-
"""代码格式化器"""
import os
import shutil
import subprocess
from typing import Optional, Tuple, List


class Formatter:
    """代码格式化器基类"""

    name = "base"
    languages = []

    def is_available(self) -> bool:
        return False

    def format_code(self, code: str, filepath: str = "") -> Tuple[bool, str]:
        return False, "未实现"


class BlackFormatter(Formatter):
    """Black 格式化器（Python）"""

    name = "black"
    languages = ["python"]

    def is_available(self) -> bool:
        return shutil.which("black") is not None

    def format_code(self, code, filepath=""):
        try:
            result = subprocess.run(
                ["black", "-", "--quiet"],
                input=code, capture_output=True,
                text=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stderr
        except FileNotFoundError:
            return False, "black 未安装: pip install black"
        except Exception as e:
            return False, str(e)


class Autopep8Formatter(Formatter):
    """autopep8 格式化器（Python）"""

    name = "autopep8"
    languages = ["python"]

    def is_available(self) -> bool:
        return shutil.which("autopep8") is not None

    def format_code(self, code, filepath=""):
        try:
            result = subprocess.run(
                ["autopep8", "-", "--aggressive", "--aggressive"],
                input=code, capture_output=True,
                text=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stderr
        except FileNotFoundError:
            return False, "autopep8 未安装: pip install autopep8"
        except Exception as e:
            return False, str(e)


class ClangFormatFormatter(Formatter):
    """clang-format（C/C++）"""

    name = "clang-format"
    languages = ["c", "cpp"]

    def is_available(self) -> bool:
        return shutil.which("clang-format") is not None

    def format_code(self, code, filepath=""):
        try:
            result = subprocess.run(
                ["clang-format", "-assume-filename=" + (filepath or "temp.cpp")],
                input=code, capture_output=True,
                text=True, timeout=10,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stderr
        except FileNotFoundError:
            return False, "clang-format 未安装"
        except Exception as e:
            return False, str(e)


class FormatterRegistry:
    """格式化器注册表"""

    def __init__(self):
        self._formatters = [
            BlackFormatter(),
            Autopep8Formatter(),
            ClangFormatFormatter(),
        ]

    def list_available(self) -> List[Formatter]:
        return [f for f in self._formatters if f.is_available()]

    def get_for_language(self, language: str) -> List[Formatter]:
        lang = language.lower()
        return [f for f in self._formatters
                if f.is_available() and lang in f.languages]

    def format(self, code, language="python",
               filepath="", formatter_name="") -> Tuple[bool, str]:
        """格式化代码"""
        candidates = self.get_for_language(language)

        if not candidates:
            # 尝试所有可用的
            candidates = self.list_available()

        if not candidates:
            return False, "没有可用的格式化器"

        # 优先使用指定名
        if formatter_name:
            for f in candidates:
                if f.name == formatter_name:
                    return f.format_code(code, filepath)

        # 否则用第一个
        return candidates[0].format_code(code, filepath)


# 全局单例
_registry = None


def get_formatter_registry():
    global _registry
    if _registry is None:
        _registry = FormatterRegistry()
    return _registry