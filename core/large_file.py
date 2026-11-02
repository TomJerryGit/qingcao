# -*- coding: utf-8 -*-
"""大文件支持（v2.17）：大文件模式 + 实时诊断阈值配置"""
import os


LARGE_FILE_THRESHOLD_BYTES = 10 * 1024 * 1024      # 10MB：启用大文件模式
HUGE_FILE_THRESHOLD_BYTES = 40 * 1024 * 1024       # 40MB：更激进的精简
DEFAULT_LIVE_DIAGNOSTICS_MB = 5


def file_size(path):
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def is_large_file(path, threshold=LARGE_FILE_THRESHOLD_BYTES) -> bool:
    return file_size(path) >= threshold


def is_huge_file(path) -> bool:
    return file_size(path) >= HUGE_FILE_THRESHOLD_BYTES


def live_diagnostics_limit_bytes() -> int:
    """实时沙箱诊断大文件阈值（MB -> 字节）：
    环境变量 QINGCAO_LIVE_DIAGNOSTICS_MAX_MB >
    QSettings("QingCao","Editor").live_diagnostics_max_mb > 默认 5MB
    """
    mb = None
    try:
        raw = os.environ.get("QINGCAO_LIVE_DIAGNOSTICS_MAX_MB")
        if raw:
            mb = float(raw)
    except Exception:
        mb = None
    if mb is None:
        try:
            from PyQt5.QtCore import QSettings
            mb = float(QSettings("QingCao", "Editor").value(
                "live_diagnostics_max_mb", DEFAULT_LIVE_DIAGNOSTICS_MB,
                type=int))
        except Exception:
            mb = DEFAULT_LIVE_DIAGNOSTICS_MB
    try:
        mb = max(1.0, min(512.0, float(mb)))
    except Exception:
        mb = DEFAULT_LIVE_DIAGNOSTICS_MB
    return int(mb * 1024 * 1024)


def apply_large_file_mode(editor, huge: bool = False) -> bool:
    """对大文件编辑器关闭高开销特性（折叠/彩虹缩进/缩进参考线）"""
    if editor is None:
        return False
    try:
        from PyQt5.Qsci import QsciScintilla
        editor.setFolding(QsciScintilla.NoFoldStyle)
    except Exception:
        pass
    try:
        if hasattr(editor, "set_rainbow_enabled"):
            editor.set_rainbow_enabled(False)
    except Exception:
        pass
    try:
        editor.setIndentationGuides(False)
    except Exception:
        pass
    try:
        editor.setMarginWidth(2, 0)
    except Exception:
        pass
    try:
        editor._qc_large_file = True
        editor._qc_huge_file = bool(huge)
    except Exception:
        pass
    return True
