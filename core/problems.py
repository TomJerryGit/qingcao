# -*- coding: utf-8 -*-
"""问题收集与管理"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


class Severity(Enum):
    """问题严重程度"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


@dataclass
class Problem:
    """单个问题"""
    filepath: str = ""
    line: int = 0
    col: int = 0
    severity: str = "info"
    message: str = ""
    source: str = ""       # 来源（LSP/TODO/...）
    code: str = ""         # 错误码
    end_line: int = 0
    end_col: int = 0

    def __hash__(self):
        return hash((self.filepath, self.line, self.col, self.message))


class ProblemManager(QObject):
    """问题管理器"""

    problems_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.problems: Dict[str, List[Problem]] = {}  # filepath -> [Problem]

    def set_file_problems(self, filepath, problems):
        """设置某文件的全部问题"""
        if problems:
            self.problems[filepath] = list(problems)
        else:
            self.problems.pop(filepath, None)
        self.problems_changed.emit()

    def add_problem(self, problem):
        """添加单个问题"""
        self.problems.setdefault(problem.filepath, []).append(problem)
        self.problems_changed.emit()

    def remove_file(self, filepath):
        """删除某文件的所有问题"""
        if filepath in self.problems:
            del self.problems[filepath]
            self.problems_changed.emit()

    def clear(self):
        """清空所有问题"""
        self.problems.clear()
        self.problems_changed.emit()

    def all_problems(self) -> List[Problem]:
        """获取所有问题"""
        result = []
        for plist in self.problems.values():
            result.extend(plist)
        return result

    def count_by_severity(self):
        """按严重程度统计"""
        counts = {"error": 0, "warning": 0, "info": 0, "hint": 0}
        for p in self.all_problems():
            if p.severity in counts:
                counts[p.severity] += 1
        return counts

    def get_for_file(self, filepath) -> List[Problem]:
        """获取指定文件的问题"""
        return self.problems.get(filepath, [])


# 全局单例
_manager = None


def get_problem_manager():
    global _manager
    if _manager is None:
        _manager = ProblemManager()
    return _manager