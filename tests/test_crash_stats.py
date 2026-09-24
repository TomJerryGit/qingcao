# -*- coding: utf-8 -*-
"""崩溃统计测试（A3）"""
import os
import json
import time
import datetime
import pytest


def _write_crash(path, ts_offset_seconds=0, exc_type="ValueError"):
    ts = time.time() + ts_offset_seconds
    data = {
        'timestamp': datetime.datetime.fromtimestamp(ts).isoformat(),
        'exception_type': exc_type,
        'exception_message': 'test message',
        'app_version': '2.0.1',
        'platform': 'test',
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


class TestCrashStats:
    def _stats(self, tmp_path, **kwargs):
        from core.crash_stats import CrashStats
        return CrashStats(str(tmp_path), **kwargs)

    def test_empty_dir(self, tmp_path):
        stats = self._stats(tmp_path)
        assert stats.get_total_count() == 0
        assert stats.should_notify() is False

    def test_scan_recent(self, tmp_path):
        # 3 天内：应该计入 recent
        _write_crash(str(tmp_path / "crash_1.json"), -3600)
        # 10 天前：不应计入 recent
        _write_crash(str(tmp_path / "crash_2.json"), -10 * 86400)

        stats = self._stats(tmp_path, recent_days=7)
        assert stats.get_total_count() == 2
        assert stats.get_recent_count() == 1

    def test_should_notify(self, tmp_path):
        for i in range(3):
            _write_crash(
                str(tmp_path / f"crash_{i}.json"),
                -3600 - i * 60,
            )
        stats = self._stats(tmp_path, recent_days=7, trigger_count=3)
        assert stats.should_notify() is True

    def test_should_not_notify_below_threshold(self, tmp_path):
        for i in range(2):
            _write_crash(
                str(tmp_path / f"crash_{i}.json"), -3600,
            )
        stats = self._stats(tmp_path, trigger_count=3)
        assert stats.should_notify() is False

    def test_group_by_exception(self, tmp_path):
        _write_crash(str(tmp_path / "a.json"), -100, "ValueError")
        _write_crash(str(tmp_path / "b.json"), -200, "ValueError")
        _write_crash(str(tmp_path / "c.json"), -300, "TypeError")
        stats = self._stats(tmp_path)
        grouped = stats.group_by_exception()
        assert grouped["ValueError"] == 2
        assert grouped["TypeError"] == 1

    def test_clear(self, tmp_path):
        _write_crash(str(tmp_path / "a.json"), -100)
        _write_crash(str(tmp_path / "b.json"), -200)
        stats = self._stats(tmp_path)
        assert stats.get_total_count() == 2
        removed = stats.clear()
        assert removed == 2
        assert stats.get_total_count() == 0

    def test_corrupt_file_tolerated(self, tmp_path):
        """损坏的 JSON 不崩，用 mtime 兜底"""
        bad = tmp_path / "crash_bad.json"
        bad.write_text("{ not valid json", encoding='utf-8')
        stats = self._stats(tmp_path)
        records = stats.scan()
        # 应该能扫到（类型为"无法解析"）
        assert len(records) == 1