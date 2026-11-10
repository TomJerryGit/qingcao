# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件 API 模块，包含：
- PluginAPI：暴露给插件的安全接口
- PluginBase：插件基类（推荐继承）
- 权限校验机制
- 菜单注册
- 面板注册
- 事件订阅
- 编辑器访问
- 文件系统操作
- 网络请求
- 快捷键注册
- 语法高亮注册
- LSP 注册
- 状态栏消息
- 对话框辅助
- 配置读写
- 命令注册

修复记录:
- PluginBase.activate: 当 api 为 None 时安全处理，避免二次崩溃
- PluginAPI: 构造时增加 main_window 与 plugin_name 的健壮性校验
- 所有 *_safe 方法在 api 为 None 时返回安全默认值
"""

import functools
import inspect
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import (
    BaseEvent,
    CursorEvent,
    EditorChangedEvent,
    FileClosedEvent,
    FileModifiedEvent,
    FileOpenedEvent,
    FileSavedEvent,
    MacroStartedEvent,
    MacroStoppedEvent,
    NotificationEvent,
    ProjectClosedEvent,
    ProjectOpenedEvent,
    SelectionEvent,
    StatusMessageEvent,
    TabAddedEvent,
    TabChangedEvent,
    TabRemovedEvent,
    ThemeEvent,
    bus,
)


# ============================================================
# 常量
# ============================================================
# 插件权限常量
PERMISSION_FILESYSTEM = "filesystem"
PERMISSION_NETWORK = "network"
PERMISSION_PROCESS = "process"
PERMISSION_CLIPBOARD = "clipboard"
PERMISSION_DIALOG = "dialog"
PERMISSION_EDITOR_WRITE = "editor_write"
PERMISSION_EDITOR_READ = "editor_read"
PERMISSION_TERMINAL = "terminal"
# P1-2 修复：README 文档中列出了 lsp / debugger，但代码里
# 没有这两个常量，parse_permissions 会把它们静默过滤掉，
# 导致插件声明的权限与运行时权限不一致。
PERMISSION_LSP = "lsp"
PERMISSION_DEBUGGER = "debugger"

ALL_PERMISSIONS = [
    PERMISSION_FILESYSTEM,
    PERMISSION_NETWORK,
    PERMISSION_PROCESS,
    PERMISSION_CLIPBOARD,
    PERMISSION_DIALOG,
    PERMISSION_EDITOR_WRITE,
    PERMISSION_EDITOR_READ,
    PERMISSION_TERMINAL,
    PERMISSION_LSP,
    PERMISSION_DEBUGGER,
]

# 权限名称（中文，供 UI 展示；与 app/plugin_manager.PERMISSION_NAMES 对齐）
PERMISSION_LABELS = {
    PERMISSION_FILESYSTEM: "读写本地文件",
    PERMISSION_NETWORK: "访问网络",
    PERMISSION_PROCESS: "执行系统命令",
    PERMISSION_CLIPBOARD: "读写剪贴板",
    PERMISSION_DIALOG: "显示对话框 / 访问主窗口",
    PERMISSION_EDITOR_WRITE: "修改编辑器内容",
    PERMISSION_EDITOR_READ: "读取编辑器内容",
    PERMISSION_TERMINAL: "使用集成终端",
    PERMISSION_LSP: "注册 LSP 服务",
    PERMISSION_DEBUGGER: "调试功能",
}

# API 版本
API_VERSION = "2.0.0"


# ============================================================
# 权限错误
# ============================================================
class PermissionError(Exception):
    """插件权限不足时抛出"""

    pass


# ============================================================
# 插件 API
# ============================================================
class _BackgroundBridge(QObject):
    """后台任务结果桥（v2.3 `run_background` 用）

    每个后台任务配一个独立桥：`run_background` 可能在同一个 API
    实例上并发多个任务，共享信号无法区分结果归属。
    桥对象在**主线程**创建；工作线程只 emit，Qt 按队列把回调
    投递回主线程执行 —— 这就是"后台执行、主线程回调"的实现方式。

    `cancelled` 由插件卸载路径置位，回调据此跳过，避免在窗口
    销毁后操作 Qt 对象。
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = False


# 供 mixin/主类复用的公开符号
__all__ = [n for n in dir() if not n.startswith("_")] + ["PermissionError"]


# v2.24：导出包含单下划线符号（供 Mixin 星号导入）
__all__ = [n for n in dir() if not n.startswith('__')]
