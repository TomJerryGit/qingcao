#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为标签管理器模块，包含：
- TabManager：多标签管理
- 标签新增、关闭、切换、排序
- 标签脏状态标记（*）
- 只读文件锁图标（🔒）
- Git 状态颜色标记
- 标签右键菜单（关闭其他、关闭右侧、复制路径等）
- 中键关闭标签
- 恢复最近关闭的标签
- 后台标签资源自动释放
- 标签拖拽分离为独立窗口
- 文件外部修改检测
- 事件总线联动

统一使用 PyQt5。

修复记录:
- 统一通过辅助方法 _get_proxy_filepath / _get_proxy_encoding /
  _get_proxy_provider 访问文件信息，避免 proxy.prov / proxy.document.enc
  等旧 API 崩溃
- 兼容新旧两种 EditorProxy 结构（document + prov）
- 所有直接访问 proxy.document / proxy.prov 的地方增加 hasattr 保护
- close_tab: 关闭时收集书签和折叠状态，供恢复使用（P1-4）
- restore_closed_tab: 恢复书签和折叠状态
"""

import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QFileSystemWatcher, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabBar,
    QTabWidget,
    QWidget,
)

from app.event_bus import (
    FileClosedEvent,
    FileModifiedEvent,
    FileOpenedEvent,
    FileSavedEvent,
    TabAddedEvent,
    TabChangedEvent,
    TabRemovedEvent,
    bus,
)
from core.content_provider import (
    LocalFileProvider,
    MemoryProvider,
    is_binary_sample,
)


logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================
MAX_CLOSED_TABS = 20             # 最多记录最近关闭的标签数量
IDLE_RELEASE_MINUTES = 30        # 后台标签闲置多久后释放内容
IDLE_CHECK_INTERVAL_MS = 60000   # 空闲检查间隔

# Git 状态颜色
GIT_MODIFIED_COLOR = QColor("#E5A72D")   # 橙色：已修改
GIT_ADDED_COLOR = QColor("#6A9955")      # 绿色：新增
GIT_DELETED_COLOR = QColor("#F14C4C")    # 红色：已删除
GIT_UNTRACKED_COLOR = QColor("#808080")  # 灰色：未跟踪

# 文件类型标签颜色（用于快速识别）
FILE_TYPE_COLORS = {
    '.py':   QColor("#3572A5"),
    '.pyw':  QColor("#3572A5"),
    '.cpp':  QColor("#f34b7d"),
    '.cc':   QColor("#f34b7d"),
    '.cxx':  QColor("#f34b7d"),
    '.h':    QColor("#f34b7d"),
    '.hpp':  QColor("#f34b7d"),
    '.c':    QColor("#555555"),
    '.js':   QColor("#f1e05a"),
    '.ts':   QColor("#2b7489"),
    '.jsx':  QColor("#61dafb"),
    '.tsx':  QColor("#61dafb"),
    '.java': QColor("#b07219"),
    '.rs':   QColor("#dea584"),
    '.go':   QColor("#00ADD8"),
    '.rb':   QColor("#701516"),
    '.php':  QColor("#4F5D95"),
    '.html': QColor("#e34c26"),
    '.htm':  QColor("#e34c26"),
    '.css':  QColor("#563d7c"),
    '.scss': QColor("#c6538c"),
    '.json': QColor("#f1e05a"),
    '.xml':  QColor("#0060ac"),
    '.md':   QColor("#083fa1"),
    '.txt':  QColor("#999999"),
    '.log':  QColor("#c0c0c0"),
    '.csv':  QColor("#1e8e3e"),
    '.ini':  QColor("#999999"),
    '.cfg':  QColor("#999999"),
    '.yml':  QColor("#cb171e"),
    '.yaml': QColor("#cb171e"),
    '.toml': QColor("#9c4221"),
    '.sh':   QColor("#89e051"),
    '.bat':  QColor("#C1F12E"),
    '.ps1':  QColor("#012456"),
    '.sql':  QColor("#e38c00"),
}

# 节点类型
NODE_TYPE_DIR = 0
NODE_TYPE_FILE = 1
NODE_TYPE_ROOT = 2


# ============================================================
# 标签管理器
# ============================================================

__all__ = [n for n in dir() if not n.startswith('__')]
