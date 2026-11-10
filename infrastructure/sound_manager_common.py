#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为音效管理器模块，包含：
- SoundManager：音效管理器（单例）
- SoundEffect：音效对象（播放、循环、音量）
- SoundEvent：音效事件枚举
- SoundCategory：音效分类
- SoundLibrary：音效库（内置音效）
- SoundCache：音效缓存
- SoundPlayer：多通道播放器
- 音量控制（主音量/分类音量）
- 静音控制
- 音效淡入淡出
- 音效优先级
- 节流控制（防止频繁触发）
- 音效配置持久化
- 系统提示音回退
- 程序化生成音效
- 音效资源扫描

修复记录:
- 将 QtMultimedia 的导入包裹在 try/except 中（P2-6）。
  某些 PyQt5 安装不包含 QtMultimedia（如 Linux 精简安装、
  使用 pip install PyQt5 而非完整 Qt 包），会导致整个模块
  导入失败。现在缺失时会优雅降级：
    * SoundEffect 内部将 self._effect 置为 None
    * SoundManager 播放时回退到 QApplication.beep()
    * 不再因 import 失败而中断启动
"""

import io
import math
import os
import struct
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QSettings,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtWidgets import QApplication


# ============================================================
# QtMultimedia 安全导入（P2-6 修复）
# ============================================================
# 某些 PyQt5 安装（尤其 Linux 精简包）不包含 QtMultimedia 模块。
# 直接 import 会导致整个 sound_manager.py 加载失败，
# 进而影响 SoundManager 的调用方（主窗口、插件等）。
#
# 这里采用 try/except 包裹导入，缺失时将 QSoundEffect 等置为 None，
# 并在 SoundEffect / SoundManager 内部通过 _MULTIMEDIA_OK 判断降级。
try:
    from PyQt5.QtMultimedia import QAudioDeviceInfo, QAudioOutput, QMediaPlayer, QSoundEffect

    _MULTIMEDIA_OK = True
except ImportError as _mm_err:
    QSoundEffect = None
    QAudioOutput = None
    QMediaPlayer = None
    QAudioDeviceInfo = None
    _MULTIMEDIA_OK = False
    print(f"[SoundManager] QtMultimedia 不可用，音效将回退到系统提示音: {_mm_err}")


# ============================================================
# 常量
# ============================================================
# 默认音效目录
def _default_sound_dir() -> str:
    """资源目录用绝对路径（相对路径随工作目录变化）"""
    try:
        from infrastructure.plugin_loader import app_root_dir

        return os.path.join(app_root_dir(), "resources", "sounds")
    except Exception:  # pragma: no cover
        return os.path.join("resources", "sounds")


DEFAULT_SOUND_DIR = _default_sound_dir()

# 默认主音量（0.0 - 1.0）
DEFAULT_MASTER_VOLUME = 0.7

# 节流时间（毫秒）：同一音效在此时段内不重复播放
DEFAULT_THROTTLE_MS = 50

# 最大同时播放的通道数
MAX_CHANNELS = 16

# 缓存大小
MAX_CACHE_SIZE = 100

# 声音采样率
SAMPLE_RATE = 44100

# 淡出/淡入持续时间（毫秒）
FADE_DURATION_MS = 200


# ============================================================
# 音效分类枚举
# ============================================================
class SoundCategory(Enum):
    """音效分类"""

    UI = "ui"  # 界面交互
    EDITOR = "editor"  # 编辑操作
    NOTIFICATION = "notification"  # 通知
    ERROR = "error"  # 错误
    SUCCESS = "success"  # 成功
    SYSTEM = "system"  # 系统


# ============================================================
# 音效事件枚举
# ============================================================
class SoundEvent(Enum):
    """音效事件"""

    # 文件操作
    FILE_NEW = "file_new"
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    FILE_CLOSE = "file_close"
    FILE_DELETE = "file_delete"

    # 编辑
    EDIT_TYPE = "edit_type"
    EDIT_DELETE = "edit_delete"
    EDIT_PASTE = "edit_paste"
    EDIT_UNDO = "edit_undo"
    EDIT_REDO = "edit_redo"
    EDIT_FIND = "edit_find"
    EDIT_REPLACE = "edit_replace"

    # 界面
    UI_CLICK = "ui_click"
    UI_TOGGLE = "ui_toggle"
    UI_HOVER = "ui_hover"
    UI_SCROLL = "ui_scroll"
    UI_TAB_SWITCH = "ui_tab_switch"
    UI_MENU_OPEN = "ui_menu_open"

    # 通知
    NOTIFY_INFO = "notify_info"
    NOTIFY_WARNING = "notify_warning"
    NOTIFY_ERROR = "notify_error"
    NOTIFY_SUCCESS = "notify_success"

    # 其他
    MACRO_START = "macro_start"
    MACRO_STOP = "macro_stop"
    SEARCH_FOUND = "search_found"
    SEARCH_NOT_FOUND = "search_not_found"
    TYPING = "typing"


# ============================================================
# 音效事件到分类的映射
# ============================================================
EVENT_CATEGORY_MAP: Dict[SoundEvent, SoundCategory] = {
    SoundEvent.FILE_NEW: SoundCategory.UI,
    SoundEvent.FILE_OPEN: SoundCategory.UI,
    SoundEvent.FILE_SAVE: SoundCategory.SUCCESS,
    SoundEvent.FILE_CLOSE: SoundCategory.UI,
    SoundEvent.FILE_DELETE: SoundCategory.UI,
    SoundEvent.EDIT_TYPE: SoundCategory.EDITOR,
    SoundEvent.EDIT_DELETE: SoundCategory.EDITOR,
    SoundEvent.EDIT_PASTE: SoundCategory.EDITOR,
    SoundEvent.EDIT_UNDO: SoundCategory.EDITOR,
    SoundEvent.EDIT_REDO: SoundCategory.EDITOR,
    SoundEvent.EDIT_FIND: SoundCategory.EDITOR,
    SoundEvent.EDIT_REPLACE: SoundCategory.EDITOR,
    SoundEvent.UI_CLICK: SoundCategory.UI,
    SoundEvent.UI_TOGGLE: SoundCategory.UI,
    SoundEvent.UI_HOVER: SoundCategory.UI,
    SoundEvent.UI_SCROLL: SoundCategory.UI,
    SoundEvent.UI_TAB_SWITCH: SoundCategory.UI,
    SoundEvent.UI_MENU_OPEN: SoundCategory.UI,
    SoundEvent.NOTIFY_INFO: SoundCategory.NOTIFICATION,
    SoundEvent.NOTIFY_WARNING: SoundCategory.NOTIFICATION,
    SoundEvent.NOTIFY_ERROR: SoundCategory.ERROR,
    SoundEvent.NOTIFY_SUCCESS: SoundCategory.SUCCESS,
    SoundEvent.MACRO_START: SoundCategory.NOTIFICATION,
    SoundEvent.MACRO_STOP: SoundCategory.NOTIFICATION,
    SoundEvent.SEARCH_FOUND: SoundCategory.NOTIFICATION,
    SoundEvent.SEARCH_NOT_FOUND: SoundCategory.NOTIFICATION,
    SoundEvent.TYPING: SoundCategory.EDITOR,
}


# ============================================================
# 音效事件到文件的映射（默认）
# ============================================================
EVENT_FILE_MAP: Dict[SoundEvent, str] = {
    SoundEvent.FILE_NEW: "file_new.wav",
    SoundEvent.FILE_OPEN: "file_open.wav",
    SoundEvent.FILE_SAVE: "file_save.wav",
    SoundEvent.FILE_CLOSE: "file_close.wav",
    SoundEvent.FILE_DELETE: "file_delete.wav",
    SoundEvent.EDIT_TYPE: "type.wav",
    SoundEvent.EDIT_DELETE: "delete.wav",
    SoundEvent.EDIT_PASTE: "paste.wav",
    SoundEvent.EDIT_UNDO: "undo.wav",
    SoundEvent.EDIT_REDO: "redo.wav",
    SoundEvent.EDIT_FIND: "find.wav",
    SoundEvent.EDIT_REPLACE: "replace.wav",
    SoundEvent.UI_CLICK: "click.wav",
    SoundEvent.UI_TOGGLE: "toggle.wav",
    SoundEvent.UI_HOVER: "hover.wav",
    SoundEvent.UI_SCROLL: "scroll.wav",
    SoundEvent.UI_TAB_SWITCH: "tab_switch.wav",
    SoundEvent.UI_MENU_OPEN: "menu_open.wav",
    SoundEvent.NOTIFY_INFO: "info.wav",
    SoundEvent.NOTIFY_WARNING: "warning.wav",
    SoundEvent.NOTIFY_ERROR: "error.wav",
    SoundEvent.NOTIFY_SUCCESS: "success.wav",
    SoundEvent.MACRO_START: "macro_start.wav",
    SoundEvent.MACRO_STOP: "macro_stop.wav",
    SoundEvent.SEARCH_FOUND: "found.wav",
    SoundEvent.SEARCH_NOT_FOUND: "not_found.wav",
    SoundEvent.TYPING: "type.wav",
}


# ============================================================
# 音效对象
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
