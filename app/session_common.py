#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为会话管理模块，包含：
- SessionManager：会话保存与恢复
- 打开文件列表、光标位置、滚动位置记忆
- 标签顺序、活动标签记忆
- 书签持久化
- 折叠状态持久化
- 窗口几何与布局记忆
- 面板可见性与位置记忆
- 分屏状态记忆
- 自动保存与崩溃恢复
- 会话版本兼容与迁移
- 会话文件原子写入
- 会话文件损坏自修复

新增（v2.1）：
- save_autosave：自动备份未保存文件
- clear_autosave：正常退出时清理自动备份
- check_and_recover_crash：启动时检测并恢复崩溃备份

统一使用 PyQt5（pyqtSignal 而非 Signal）
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QDockWidget, QMainWindow, QSplitter


# ============================================================
# 常量定义
# ============================================================
SESSION_FILE = "session.json"
SESSION_VERSION = 2
MAX_SESSION_BACKUPS = 5
AUTOSAVE_INTERVAL_MS = 120000  # 2 分钟
MAX_RECENT_SESSIONS = 10

# 应用根目录（绝对路径）
#
# 为什么必须绝对化（真实缺陷，与"插件全部不加载"同源）：
#   相对路径的含义取决于**当前工作目录**。从资源管理器双击 exe 时
#   cwd 恰好是程序目录，一切正常；但通过快捷方式/任务栏/其他目录启动时，
#   `session.json` 会写到别处 —— 表现为"打开的文件列表、光标位置、
#   面板布局每次启动都丢"。同理 `data/backups` 也会漂移。
try:
    from infrastructure.plugin_loader import app_root_dir as _app_root

    _APP_ROOT = _app_root()
except Exception:  # pragma: no cover
    _APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def instance_session_file(root: str, new_window: bool, pid: int) -> str:
    """多实例：新窗口实例使用独立会话文件，避免互相覆盖"""
    name = ("session_w%d.json" % pid) if new_window else "session.json"
    return os.path.join(root, name)


SESSION_FILE = os.environ.get("QINGCAO_SESSION_FILE") or instance_session_file(
    _APP_ROOT, os.environ.get("QINGCAO_NEW_WINDOW") == "1", os.getpid()
)
SESSION_BACKUP_DIR = os.environ.get("QINGCAO_SESSION_BACKUP_DIR") or os.path.join(
    _APP_ROOT, "data", "backups"
)

# 自动备份目录
AUTOSAVE_DIR = os.path.join(_APP_ROOT, "backup", "autosave")
AUTOSAVE_META = "meta.json"


# ============================================================
# 会话管理器
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
