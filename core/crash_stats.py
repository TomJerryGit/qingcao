# -*- coding: utf-8 -*-
"""
崩溃统计（纯数据层，无 Qt UI 依赖）
====================================
扫描 data/crashes/*.json，提供：
- 总数 / 近期数 / 首次/最近时间
- 按异常类型聚合（Top N）
- 清理策略

设计：
- 不依赖 Qt（可被 CLI 或 CI 调用）
- 失败静默（崩溃数据目录损坏不影响主流程）
"""

import datetime
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


CRASH_DIR = os.path.join("data", "crashes")
DEFAULT_RECENT_DAYS = 7
DEFAULT_TRIGGER_COUNT = 3


@dataclass
class CrashRecord:
    """单条崩溃记录"""
    filepath: str = ""
    timestamp: float = 0.0
    exception_type: str = ""
    exception_message: str = ""
    app_version: str = ""
    platform: str = ""

    @property
    def datetime_str(self) -> str:
        if self.timestamp <= 0:
            return "?"
        try:
            return datetime.datetime.fromtimestamp(
                self.timestamp
            ).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "?"

    def to_dict(self) -> Dict[str, Any]:
        return {
            'filepath': self.filepath,
            'timestamp': self.timestamp,
            'exception_type': self.exception_type,
            'exception_message': self.exception_message,
            'app_version': self.app_version,
            'platform': self.platform,
        }


class CrashStats:
    """
    崩溃统计器。

    用法::

        stats = CrashStats()          # 默认读 data/crashes/
        if stats.should_notify():     # 近期崩溃 >= 3 次
            show_dialog(stats)
    """

    def __init__(self, crash_dir: str = CRASH_DIR,
                 recent_days: int = DEFAULT_RECENT_DAYS,
                 trigger_count: int = DEFAULT_TRIGGER_COUNT):
        self.crash_dir = crash_dir
        self.recent_days = recent_days
        self.trigger_count = trigger_count

    # --------------------------------------------------------
    # 扫描
    # --------------------------------------------------------
    def scan(self) -> List[CrashRecord]:
        """扫描崩溃目录，返回按时间倒序的记录列表"""
        records: List[CrashRecord] = []

        if not os.path.isdir(self.crash_dir):
            return records

        try:
            for name in os.listdir(self.crash_dir):
                if not name.endswith('.json'):
                    continue
                path = os.path.join(self.crash_dir, name)
                if not os.path.isfile(path):
                    continue

                rec = self._parse_one(path)
                if rec:
                    records.append(rec)
        except Exception:
            return records

        # 按时间倒序
        records.sort(key=lambda r: r.timestamp, reverse=True)
        return records

    def _parse_one(self, path: str) -> Optional[CrashRecord]:
        """解析单个 crash_*.json"""
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            # 文件损坏：用 mtime 兜底
            try:
                return CrashRecord(
                    filepath=path,
                    timestamp=os.path.getmtime(path),
                    exception_type="(无法解析)",
                )
            except Exception:
                return None

        try:
            ts_str = data.get('timestamp', '')
            ts = 0.0
            if ts_str:
                try:
                    ts = datetime.datetime.fromisoformat(
                        ts_str
                    ).timestamp()
                except Exception:
                    ts = 0.0
            if ts <= 0:
                try:
                    ts = os.path.getmtime(path)
                except Exception:
                    ts = 0.0

            return CrashRecord(
                filepath=path,
                timestamp=ts,
                exception_type=data.get('exception_type', ''),
                exception_message=data.get('exception_message', ''),
                app_version=data.get('app_version', ''),
                platform=data.get('platform', ''),
            )
        except Exception:
            return None

    # --------------------------------------------------------
    # 统计
    # --------------------------------------------------------
    def get_total_count(self) -> int:
        return len(self.scan())

    def get_recent_records(self, days: Optional[int] = None
                            ) -> List[CrashRecord]:
        """最近 N 天的记录"""
        days = days or self.recent_days
        cutoff = time.time() - days * 86400
        return [r for r in self.scan() if r.timestamp >= cutoff]

    def get_recent_count(self, days: Optional[int] = None) -> int:
        return len(self.get_recent_records(days))

    def group_by_exception(self) -> Dict[str, int]:
        """按异常类型聚合（用于展示"最常见崩溃"）"""
        result: Dict[str, int] = {}
        for r in self.scan():
            key = r.exception_type or "(未知)"
            result[key] = result.get(key, 0) + 1
        return result

    def get_top_exceptions(self, n: int = 5
                            ) -> List[tuple]:
        """Top N 异常类型"""
        grouped = self.group_by_exception()
        return sorted(grouped.items(), key=lambda x: x[1], reverse=True)[:n]

    # --------------------------------------------------------
    # 触发判定
    # --------------------------------------------------------
    def should_notify(self) -> bool:
        """是否应弹提醒（最近 N 天 >= M 次）"""
        return self.get_recent_count() >= self.trigger_count

    # --------------------------------------------------------
    # 清理
    # --------------------------------------------------------
    def clear(self) -> int:
        """删除所有崩溃记录，返回删除数量"""
        count = 0
        if not os.path.isdir(self.crash_dir):
            return 0
        try:
            for name in os.listdir(self.crash_dir):
                if not name.endswith('.json'):
                    continue
                path = os.path.join(self.crash_dir, name)
                try:
                    os.remove(path)
                    count += 1
                except Exception:
                    pass
        except Exception:
            pass
        return count

    def cleanup_old(self, keep_days: int = 30) -> int:
        """删除超过 N 天的记录，返回删除数量"""
        cutoff = time.time() - keep_days * 86400
        count = 0
        for r in self.scan():
            if r.timestamp < cutoff:
                try:
                    os.remove(r.filepath)
                    count += 1
                except Exception:
                    pass
        return count

    # --------------------------------------------------------
    # 摘要
    # --------------------------------------------------------
    def get_summary(self) -> Dict[str, Any]:
        return {
            'total': self.get_total_count(),
            'recent': self.get_recent_count(),
            'recent_days': self.recent_days,
            'trigger_count': self.trigger_count,
            'top_exceptions': self.get_top_exceptions(5),
        }

    def __repr__(self) -> str:
        s = self.get_summary()
        return (f"<CrashStats total={s['total']} "
                f"recent={s['recent']}/{s['recent_days']}d>")