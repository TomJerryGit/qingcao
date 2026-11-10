# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

插件名称: ai_assistant (AI 助手)
==================================
在编辑器内使用 AI 进行代码解释、重构、生成测试等。

权限:
    - network       访问 AI 服务
    - editor_read   读取编辑器内容
    - editor_write  修改编辑器内容
    - dialog        显示对话框

功能:
    - 解释代码（选中代码 → 中文解释）
    - 重构代码（提升可读性/性能）
    - 修复 Bug
    - 添加注释
    - 生成 Docstring
    - 生成单元测试
    - 性能优化
    - Code Review
    - 代码摘要
    - 语言转换（Python ↔ JavaScript ↔ ...）
    - AI 配置（Provider/API Key/Model/Base URL）

快捷键:
    - Ctrl+Shift+A        打开 AI 菜单
    - Ctrl+Shift+E        解释选中代码
    - Ctrl+Shift+R        重构选中代码

作者: TomJerry

修复记录:
- AIWorker.run: 修正 except 块的缩进（P1-5）。
- AIResultDialog._build_ui: 使用 self._enable_insert 而非 enable_insert。
- _run_ai_action: 删除未使用的 replace_mode 参数（P3-4）。
  该参数声明后从未被读取，所有调用方均依赖默认行为
  （AIResultDialog 的 enable_insert=True）。
"""

import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


try:
    from core.ollama_client import OllamaClient
except ImportError:  # 独立运行插件时的兜底
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core.ollama_client import OllamaClient


# ============================================================
# 依赖检查
# ============================================================
# 检查 ai_client 是否可用
try:
    from core.ai_client import (
        PROMPT_COMMENT,
        PROMPT_EXPLAIN,
        PROMPT_FIX,
        PROMPT_REFACTOR,
        PROMPT_REVIEW,
        PROMPT_SUMMARY,
        PROMPT_TESTS,
        AIAuthError,
        AIClient,
        AIClientError,
        AIClientFactory,
        AIConfigError,
        get_ai_client,
        load_ai_client_from_settings,
        save_ai_client_to_settings,
        set_ai_client,
        tokens_for,
    )

    _AI_CLIENT_OK = True

    # 结果缓存（首轮命中可省一次 HTTP 请求）
    from core.ai_cache import AIResultCache, get_result_cache  # noqa: E402

    _AI_CACHE_OK = True
except ImportError as e:
    print(f"[AI插件] 无法导入 core.ai_client: {e}")
    _AI_CLIENT_OK = False

    # 定义占位符，避免 import 阶段崩溃
    AIClient = None
    AIClientFactory = None
    AIAuthError = Exception
    AIConfigError = Exception
    AIClientError = Exception
    PROMPT_EXPLAIN = ""
    PROMPT_REFACTOR = ""
    PROMPT_FIX = ""
    PROMPT_COMMENT = ""
    PROMPT_TESTS = ""
    PROMPT_REVIEW = ""
    PROMPT_SUMMARY = ""

    # 缓存不可用时的占位（get_result_cache() 返回 None，
    # 调用方需判空；见 _run_ai_action 里的用法）
    _AI_CACHE_OK = False

    def get_result_cache():
        return None

    AIResultCache = None

    def load_ai_client_from_settings():
        return None

    def save_ai_client_to_settings(client):
        pass

    def set_ai_client(client):
        pass

    def get_ai_client():
        return None


# 检查 PluginBase 是否可用
try:
    from app.plugins import (
        PERMISSION_DIALOG,
        PERMISSION_EDITOR_READ,
        PERMISSION_EDITOR_WRITE,
        PERMISSION_NETWORK,
        PluginAPI,
        PluginBase,
    )

    _PLUGIN_BASE_OK = True
except ImportError as e:
    print(f"[AI插件] 无法导入 app.plugins: {e}")
    _PLUGIN_BASE_OK = False

    # 定义占位基类
    class PluginBase:
        NAME = "unknown"
        VERSION = "0.0.0"
        DESCRIPTION = ""
        AUTHOR = ""
        PERMISSIONS = []

        def __init__(self):
            self.api = None

        def activate(self, api):
            self.api = api
            if api is None:
                return
            try:
                self.on_activate()
            except Exception as e:
                import traceback

                traceback.print_exc()
                raise

        def on_activate(self):
            pass

        def deactivate(self):
            try:
                self.on_deactivate()
            except Exception:
                pass

        def on_deactivate(self):
            pass

    PluginAPI = None
    PERMISSION_NETWORK = "network"
    PERMISSION_EDITOR_READ = "editor_read"
    PERMISSION_EDITOR_WRITE = "editor_write"
    PERMISSION_DIALOG = "dialog"


# 检查额外依赖（缺失时提示）；惰性检测，避免启动时导入 requests（~0.9s）
_REQUESTS_OK = None


def _requests_ok():
    global _REQUESTS_OK
    if _REQUESTS_OK is None:
        try:
            import requests  # noqa: F401

            _REQUESTS_OK = True
        except ImportError:
            _REQUESTS_OK = False
    return _REQUESTS_OK


# ============================================================
# 常量
# ============================================================
PLUGIN_NAME = "ai_assistant"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "AI 助手 - 代码解释、重构、测试生成"

# 提示词模板补全（core.ai_client 未提供的）
PROMPT_DOCSTRING = """请为以下代码生成 {style} 风格的 docstring。
只输出添加 docstring 后的完整代码，不要额外解释。

代码：
```{lang}
{code}
```"""

PROMPT_OPTIMIZE = """请对以下代码进行性能优化，保持功能完全不变。
只输出优化后的完整代码，不要解释。

代码：
```{lang}
{code}
```"""

PROMPT_CONVERT = """请将以下 {src_lang} 代码转换为 {dst_lang}，保持功能等价。
只输出转换后的代码，不要解释。

代码：
```{src_lang}
{code}
```"""


# 语言后缀 → 语言名
LANG_EXT_MAP = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".xml": "xml",
    ".md": "markdown",
    ".sql": "sql",
    ".sh": "bash",
    ".bat": "batch",
    ".ps1": "powershell",
}


# ============================================================
# AI 请求工作线程
# ============================================================


__all__ = [n for n in dir() if not n.startswith("__")]
