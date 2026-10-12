# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
使用数据统计与分析模块。

职责:
- 聚合 telemetry（遥测）、session（会话）、local_completer（词频）等数据
- 提供使用统计的领域模型（不依赖 Qt GUI）
- 生成可读的分析报告
- 支持导出 JSON / 文本
- 历史趋势（近 N 天的使用情况）

设计原则:
- 纯数据 + 业务逻辑，不导入 QtWidgets
- 依赖 telemetry / session / local_completer 的公共接口
- 失败静默，避免影响主流程

作者: hedongwei
"""

import datetime
import json
import os
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# 常量
# ============================================================
# 从会话文件统计
SESSION_FILE = "session.json"

# 从 onboarding 文件统计
ONBOARDING_FILE = "data/onboarding.json"

# 使用统计缓存有效期（秒）
CACHE_TTL = 30


# ============================================================
# 数据模型
# ============================================================
@dataclass
class UsageSnapshot:
    """
    一次使用统计快照。

    汇总某一时刻的统计数据，用于 UI 展示与导出。
    """

    # ---- 基础统计 ----
    first_run: float = 0.0              # 首次使用时间戳
    last_run: float = 0.0               # 最近使用时间戳
    run_count: int = 0                  # 启动次数
    total_edit_time: float = 0.0        # 累计编辑时长（秒）

    # ---- 文件统计 ----
    files_opened: int = 0               # 打开文件次数
    files_saved: int = 0                # 保存文件次数
    files_by_ext: Dict[str, int] = field(default_factory=dict)

    # ---- 功能统计 ----
    searches_run: int = 0               # 搜索次数
    plugins_loaded: int = 0             # 加载插件数
    features_used: List[str] = field(default_factory=list)

    # ---- 补全统计 ----
    recent_words_count: int = 0         # 最近使用的词数
    word_freq_size: int = 0             # 词频库大小
    top_words: List[Tuple[str, int]] = field(default_factory=list)

    # ---- 时间维度 ----
    hourly_activity: Dict[int, int] = field(default_factory=dict)
    daily_activity: Dict[str, int] = field(default_factory=dict)

    # ---- 元信息 ----
    generated_at: float = field(default_factory=time.time)

    # ---- 派生属性 ----
    @property
    def usage_days(self) -> int:
        """使用天数（首次到最近）"""
        if self.first_run <= 0 or self.last_run <= 0:
            return 0
        delta = self.last_run - self.first_run
        return max(1, int(delta / 86400) + 1)

    @property
    def average_files_per_run(self) -> float:
        """平均每次启动打开文件数"""
        if self.run_count <= 0:
            return 0.0
        return self.files_opened / self.run_count

    @property
    def edit_time_hours(self) -> float:
        """编辑时长（小时）"""
        return self.total_edit_time / 3600.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        d = asdict(self)
        d['usage_days'] = self.usage_days
        d['average_files_per_run'] = self.average_files_per_run
        d['edit_time_hours'] = self.edit_time_hours
        return d


# ============================================================
# 统计器
# ============================================================
class UsageStats:
    """
    使用统计分析器。

    从各种数据源拉取原始数据，聚合成 UsageSnapshot。
    支持缓存（默认 30 秒），避免频繁读取磁盘。
    """

    def __init__(self,
                 session_file: str = SESSION_FILE,
                 onboarding_file: str = ONBOARDING_FILE):
        self.session_file = session_file
        self.onboarding_file = onboarding_file

        # 缓存
        self._cache: Optional[UsageSnapshot] = None
        self._cache_time: float = 0.0

    # ========================================================
    # 公共接口
    # ========================================================
    def get_snapshot(self, force: bool = False) -> UsageSnapshot:
        """
        获取统计快照。

        参数:
            force: 强制刷新（忽略缓存）

        返回:
            UsageSnapshot
        """
        # 检查缓存
        if not force and self._cache is not None:
            if time.time() - self._cache_time < CACHE_TTL:
                return self._cache

        snapshot = self._build_snapshot()

        self._cache = snapshot
        self._cache_time = time.time()

        return snapshot

    def clear_cache(self):
        """清空缓存"""
        self._cache = None
        self._cache_time = 0.0

    # ========================================================
    # 构建快照
    # ========================================================
    def _build_snapshot(self) -> UsageSnapshot:
        """从各数据源构建快照"""
        snapshot = UsageSnapshot()

        # 从 telemetry 收集
        self._collect_from_telemetry(snapshot)

        # 从 onboarding 收集
        self._collect_from_onboarding(snapshot)

        # 从 session 收集
        self._collect_from_session(snapshot)

        # 从 local_completer 收集
        self._collect_from_completer(snapshot)

        return snapshot

    # --------------------------------------------------------
    # telemetry
    # --------------------------------------------------------
    def _collect_from_telemetry(self, snapshot: UsageSnapshot):
        """从 telemetry 收集"""
        try:
            from core.telemetry import get_telemetry
            t = get_telemetry()
            stats = t.get_stats()

            snapshot.first_run = float(stats.get('first_run', 0.0))
            snapshot.last_run = float(stats.get('last_run', 0.0))
            snapshot.run_count = int(stats.get('run_count', 0))
            snapshot.total_edit_time = float(
                stats.get('total_edit_time', 0.0)
            )
            snapshot.files_opened = int(stats.get('files_opened', 0))
            snapshot.files_saved = int(stats.get('files_saved', 0))
            snapshot.searches_run = int(stats.get('searches_run', 0))
            snapshot.plugins_loaded = int(stats.get('plugins_loaded', 0))
            snapshot.features_used = list(
                stats.get('features_used', [])
            )

        except ImportError:
            pass
        except Exception:
            pass

    # --------------------------------------------------------
    # onboarding
    # --------------------------------------------------------
    def _collect_from_onboarding(self, snapshot: UsageSnapshot):
        """从 onboarding.json 收集"""
        if not os.path.exists(self.onboarding_file):
            return

        try:
            with open(self.onboarding_file, encoding='utf-8') as f:
                data = json.load(f)

            # onboarding.json 的字段优先覆盖
            if 'saves' in data and not snapshot.files_saved:
                snapshot.files_saved = int(data['saves'])
            if 'files_opened' in data and not snapshot.files_opened:
                snapshot.files_opened = int(data['files_opened'])
            if 'run_count' in data and not snapshot.run_count:
                snapshot.run_count = int(data['run_count'])

            # 首次运行时间
            if not snapshot.first_run and 'first_run' in data:
                try:
                    snapshot.first_run = float(data['first_run'])
                except Exception:
                    pass
        except Exception:
            pass

    # --------------------------------------------------------
    # session
    # --------------------------------------------------------
    def _collect_from_session(self, snapshot: UsageSnapshot):
        """从 session.json 收集"""
        if not os.path.exists(self.session_file):
            return

        try:
            with open(self.session_file, encoding='utf-8') as f:
                session = json.load(f)

            # 文件类型统计
            for finfo in session.get('files', []):
                fp = finfo.get('filepath') or ''
                if not fp:
                    continue
                ext = os.path.splitext(fp)[1].lower()
                if ext:
                    snapshot.files_by_ext[ext] = \
                        snapshot.files_by_ext.get(ext, 0) + 1

            # 最后保存时间作为活动时间
            saved_at = session.get('saved_at')
            if saved_at and not snapshot.last_run:
                try:
                    dt = datetime.datetime.fromisoformat(saved_at)
                    snapshot.last_run = dt.timestamp()
                except Exception:
                    pass
        except Exception:
            pass

    # --------------------------------------------------------
    # local_completer
    # --------------------------------------------------------
    def _collect_from_completer(self, snapshot: UsageSnapshot):
        """从 local_completer 收集"""
        try:
            from core.local_completer import get_local_completer
            completer = get_local_completer()
            if completer is None:
                return

            snapshot.recent_words_count = len(
                getattr(completer, 'recent_words', [])
            )

            freq = getattr(completer, 'word_freq', None)
            if freq:
                snapshot.word_freq_size = len(freq)
                # Top 10
                try:
                    top = freq.most_common(10)
                    snapshot.top_words = [(w, c) for w, c in top]
                except Exception:
                    pass
        except ImportError:
            pass
        except Exception:
            pass

    # ========================================================
    # 报告生成
    # ========================================================
    def format_summary_text(self, snapshot: Optional[UsageSnapshot] = None
                             ) -> str:
        """生成文本报告"""
        if snapshot is None:
            snapshot = self.get_snapshot()

        lines = []
        lines.append("使用统计摘要")
        lines.append("=" * 50)
        lines.append("")

        # 基础
        lines.append("[基础]")
        lines.append(f"  首次使用:   {self._format_time(snapshot.first_run)}")
        lines.append(f"  最近使用:   {self._format_time(snapshot.last_run)}")
        lines.append(f"  使用天数:   {snapshot.usage_days} 天")
        lines.append(f"  启动次数:   {snapshot.run_count}")
        lines.append(f"  编辑时长:   {snapshot.edit_time_hours:.1f} 小时")
        lines.append("")

        # 文件
        lines.append("[文件]")
        lines.append(f"  打开文件:   {snapshot.files_opened} 次")
        lines.append(f"  保存文件:   {snapshot.files_saved} 次")
        lines.append(
            f"  每次启动平均打开: "
            f"{snapshot.average_files_per_run:.2f} 个文件"
        )
        if snapshot.files_by_ext:
            lines.append("  文件类型 Top 5:")
            sorted_ext = sorted(
                snapshot.files_by_ext.items(),
                key=lambda x: x[1], reverse=True
            )[:5]
            for ext, cnt in sorted_ext:
                lines.append(f"    {ext:12s} {cnt}")
        lines.append("")

        # 功能
        lines.append("[功能]")
        lines.append(f"  搜索次数:   {snapshot.searches_run}")
        lines.append(f"  加载插件:   {snapshot.plugins_loaded}")
        lines.append(f"  使用功能:   {len(snapshot.features_used)} 种")
        if snapshot.features_used:
            for feat in snapshot.features_used[:10]:
                lines.append(f"    • {feat}")
        lines.append("")

        # 补全
        lines.append("[智能补全]")
        lines.append(f"  最近使用词数: {snapshot.recent_words_count}")
        lines.append(f"  词频库大小:   {snapshot.word_freq_size}")
        if snapshot.top_words:
            lines.append("  高频词 Top 5:")
            for word, cnt in snapshot.top_words[:5]:
                lines.append(f"    {word:20s} {cnt}")
        lines.append("")

        return "\n".join(lines)

    def format_summary_html(self, snapshot: Optional[UsageSnapshot] = None
                             ) -> str:
        """生成 HTML 报告"""
        if snapshot is None:
            snapshot = self.get_snapshot()

        html = ['<h2>使用统计</h2>']
        html.append('<table style="font-size:13px;">')

        rows = [
            ("首次使用", self._format_time(snapshot.first_run)),
            ("最近使用", self._format_time(snapshot.last_run)),
            ("使用天数", f"{snapshot.usage_days} 天"),
            ("启动次数", snapshot.run_count),
            ("编辑时长", f"{snapshot.edit_time_hours:.1f} 小时"),
            ("打开文件", f"{snapshot.files_opened} 次"),
            ("保存文件", f"{snapshot.files_saved} 次"),
            ("搜索次数", snapshot.searches_run),
            ("加载插件", snapshot.plugins_loaded),
            ("使用功能", f"{len(snapshot.features_used)} 种"),
            ("词频库大小", snapshot.word_freq_size),
        ]

        for k, v in rows:
            html.append(
                f'<tr><td style="padding:4px 12px 4px 0; '
                f'color:#888;">{k}</td>'
                f'<td style="padding:4px 0; color:#7ec850;">{v}</td></tr>'
            )

        html.append('</table>')

        # 文件类型
        if snapshot.files_by_ext:
            html.append('<h3>文件类型 Top 5</h3>')
            html.append('<table style="font-size:12px;">')
            sorted_ext = sorted(
                snapshot.files_by_ext.items(),
                key=lambda x: x[1], reverse=True
            )[:5]
            for ext, cnt in sorted_ext:
                html.append(
                    f'<tr><td style="padding:2px 12px 2px 0;">{ext}</td>'
                    f'<td style="padding:2px 0;">{cnt}</td></tr>'
                )
            html.append('</table>')

        return "".join(html)

    # ========================================================
    # 导出
    # ========================================================
    def export_json(self, filepath: str,
                    snapshot: Optional[UsageSnapshot] = None) -> bool:
        """导出为 JSON"""
        try:
            if snapshot is None:
                snapshot = self.get_snapshot()

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot.to_dict(), f, indent=2,
                          ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[UsageStats] 导出失败: {e}")
            return False

    def export_text(self, filepath: str,
                    snapshot: Optional[UsageSnapshot] = None) -> bool:
        """导出为文本"""
        try:
            text = self.format_summary_text(snapshot)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except Exception as e:
            print(f"[UsageStats] 导出失败: {e}")
            return False

    # ========================================================
    # 清理
    # ========================================================
    def reset_all(self) -> bool:
        """清空所有统计数据"""
        try:
            # 清空 telemetry
            try:
                from core.telemetry import get_telemetry
                get_telemetry().clear()
            except Exception:
                pass

            # 清空词频
            try:
                from core.local_completer import get_local_completer
                completer = get_local_completer()
                if completer:
                    completer.word_freq.clear()
                    completer.file_words.clear()
                    completer.recent_words.clear()
            except Exception:
                pass

            self.clear_cache()
            return True
        except Exception as e:
            print(f"[UsageStats] 清空失败: {e}")
            return False

    # ========================================================
    # 辅助
    # ========================================================
    @staticmethod
    def _format_time(ts: float) -> str:
        """格式化时间戳"""
        if not ts or ts <= 0:
            return "从未"
        try:
            dt = datetime.datetime.fromtimestamp(ts)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "?"

    def __repr__(self) -> str:
        return f"<UsageStats cache={'hit' if self._cache else 'miss'}>"


# ============================================================
# 全局单例
# ============================================================
_instance: Optional[UsageStats] = None


def get_usage_stats() -> UsageStats:
    """获取全局 UsageStats 单例"""
    global _instance
    if _instance is None:
        _instance = UsageStats()
    return _instance


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    stats = get_usage_stats()
    snapshot = stats.get_snapshot(force=True)

    print(stats.format_summary_text(snapshot))
    print()
    print("快照:", snapshot)
    print("使用天数:", snapshot.usage_days)
    print("平均每次打开文件:", snapshot.average_files_per_run)