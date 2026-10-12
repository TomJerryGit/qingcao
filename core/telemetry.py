# -*- coding: utf-8 -*-
"""匿名遥测（尊重隐私）"""
import hashlib
import json
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QSettings, pyqtSignal


TELEMETRY_DIR = "data/telemetry"
TELEMETRY_FILE = os.path.join(TELEMETRY_DIR, "stats.json")


class Telemetry(QObject):
    """遥测管理器"""

    enabled_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        os.makedirs(TELEMETRY_DIR, exist_ok=True)

        self.settings = QSettings("QingCao", "Editor")
        self._enabled = self.settings.value(
            "telemetry", False, type=bool
        )

        self._machine_id = self._get_machine_id()
        self._stats = self._load_stats()

    @property
    def enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        """启用/禁用遥测"""
        if self._enabled != enabled:
            self._enabled = enabled
            self.settings.setValue("telemetry", enabled)
            self.enabled_changed.emit(enabled)

    def _get_machine_id(self):
        """获取匿名机器 ID"""
        try:
            import uuid as _uuid
            node = _uuid.getnode()
            # 哈希隐藏真实 MAC
            return hashlib.sha256(
                str(node).encode('utf-8')
            ).hexdigest()[:16]
        except Exception:
            return "unknown"

    def _load_stats(self):
        """加载统计数据"""
        if os.path.exists(TELEMETRY_FILE):
            try:
                with open(TELEMETRY_FILE, encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            'first_run': time.time(),
            'last_run': 0,
            'run_count': 0,
            'total_edit_time': 0,
            'files_opened': 0,
            'files_saved': 0,
            'searches_run': 0,
            'plugins_loaded': 0,
            'features_used': [],
        }

    def _save_stats(self):
        """保存统计"""
        try:
            with open(TELEMETRY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._stats, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def record_app_start(self):
        """记录应用启动"""
        if not self._enabled:
            return

        self._stats['last_run'] = time.time()
        self._stats['run_count'] = self._stats.get('run_count', 0) + 1
        self._save_stats()

    def record_event(self, event_name, **kwargs):
        """记录事件"""
        if not self._enabled:
            return

        features = self._stats.setdefault('features_used', [])
        if event_name not in features:
            features.append(event_name)
            if len(features) > 100:
                features = features[-100:]
                self._stats['features_used'] = features

        # 常见事件的计数
        counter_keys = {
            'file_opened': 'files_opened',
            'file_saved': 'files_saved',
            'search': 'searches_run',
            'plugin_loaded': 'plugins_loaded',
        }
        if event_name in counter_keys:
            key = counter_keys[event_name]
            self._stats[key] = self._stats.get(key, 0) + 1

        # 定期保存
        if self._stats['run_count'] % 5 == 0:
            self._save_stats()

    def get_stats(self):
        """获取统计"""
        return dict(self._stats)

    def export_anonymous_report(self):
        """导出匿名报告"""
        try:
            from version import __version__ as _app_version
        except ImportError:  # pragma: no cover
            _app_version = '0.0.0'
        return {
            'machine_id': self._machine_id,
            'app_version': _app_version,
            'platform': __import__('sys').platform,
            'stats': {
                k: v for k, v in self._stats.items()
                if k != 'features_used'
            },
            'feature_count': len(self._stats.get('features_used', [])),
        }

    def clear(self):
        """清空所有数据"""
        self._stats = {
            'first_run': time.time(),
            'last_run': 0,
            'run_count': 0,
            'total_edit_time': 0,
            'files_opened': 0,
            'files_saved': 0,
            'searches_run': 0,
            'plugins_loaded': 0,
            'features_used': [],
        }
        self._save_stats()


# 全局单例
_instance = None


def get_telemetry():
    global _instance
    if _instance is None:
        _instance = Telemetry()
    return _instance