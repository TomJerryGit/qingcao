# -*- coding: utf-8 -*-
"""性能剖析器"""
import cProfile
import io
import os
import pstats
from typing import Any, Dict, List, Optional


class Profiler:
    """性能剖析器"""

    def __init__(self):
        self.profiler = None
        self.active = False
        self._result: Optional[str] = None

    def start(self):
        """开始剖析"""
        if self.active:
            return False
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        self.active = True
        return True

    def stop(self, sort_by="cumulative", top_n=30) -> Optional[str]:
        """停止剖析并返回报告"""
        if not self.active:
            return None

        self.profiler.disable()
        self.active = False

        # 生成报告
        buf = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=buf)
        stats.sort_stats(sort_by)
        stats.print_stats(top_n)

        self._result = buf.getvalue()
        return self._result

    def get_result(self) -> Optional[str]:
        return self._result

    def save_report(self, filepath):
        """保存报告"""
        if not self._result:
            return False
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self._result)
            return True
        except Exception:
            return False


# 全局单例
_profiler = None


def get_profiler():
    global _profiler
    if _profiler is None:
        _profiler = Profiler()
    return _profiler