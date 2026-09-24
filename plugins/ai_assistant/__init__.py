# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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

作者: hedongwei

修复记录:
- AIWorker.run: 修正 except 块的缩进（P1-5）。
- AIResultDialog._build_ui: 使用 self._enable_insert 而非 enable_insert。
- _run_ai_action: 删除未使用的 replace_mode 参数（P3-4）。
  该参数声明后从未被读取，所有调用方均依赖默认行为
  （AIResultDialog 的 enable_insert=True）。
"""

import os
import sys
import json
from typing import Optional, List, Dict, Any, Tuple

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QDialogButtonBox, QFormLayout,
    QMessageBox, QTextBrowser, QPlainTextEdit, QApplication,
    QProgressBar, QCheckBox, QGroupBox, QMenu
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt5.QtGui import QFont, QColor, QKeySequence


# ============================================================
# 依赖检查
# ============================================================
# 检查 ai_client 是否可用
try:
    from core.ai_client import (
        AIClient, AIClientFactory,
        AIAuthError, AIConfigError, AIClientError,
        PROMPT_EXPLAIN, PROMPT_REFACTOR, PROMPT_FIX,
        PROMPT_COMMENT, PROMPT_TESTS, PROMPT_REVIEW,
        PROMPT_SUMMARY,
        load_ai_client_from_settings,
        save_ai_client_to_settings,
        set_ai_client,
        get_ai_client,
    )
    _AI_CLIENT_OK = True
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
        PluginBase, PluginAPI,
        PERMISSION_NETWORK, PERMISSION_EDITOR_READ,
        PERMISSION_EDITOR_WRITE, PERMISSION_DIALOG,
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


# 检查额外依赖（缺失时提示）
try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False


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
    '.py': 'python', '.pyw': 'python',
    '.js': 'javascript', '.mjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript',
    '.jsx': 'javascript',
    '.c': 'c', '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp',
    '.h': 'cpp', '.hpp': 'cpp',
    '.java': 'java', '.go': 'go', '.rs': 'rust',
    '.rb': 'ruby', '.php': 'php',
    '.html': 'html', '.htm': 'html',
    '.css': 'css', '.scss': 'scss',
    '.json': 'json', '.xml': 'xml',
    '.md': 'markdown', '.sql': 'sql',
    '.sh': 'bash', '.bat': 'batch', '.ps1': 'powershell',
}


# ============================================================
# AI 请求工作线程
# ============================================================
class AIWorker(QThread):
    """
    AI 请求线程（流式）。

    信号:
        chunk_received(str): 收到流式片段
        finished_ok(str): 完成（完整文本）
        finished_err(str): 失败（错误信息）
    """

    chunk_received = pyqtSignal(str)
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def __init__(self, client, prompt: str,
                 system: str = "", parent=None):
        super().__init__(parent)
        self.client = client
        self.prompt = prompt
        self.system = system
        self._cancelled = False

    def cancel(self):
        """取消请求"""
        self._cancelled = True

    def run(self):
        """
        执行请求。

        修复说明（P1-5）:
            - 原实现中 `except` 块的缩进为 16 空格（比对应的
              `try` 多 4 个空格），导致整个文件编译时报
              SyntaxError: invalid syntax，插件无法加载。
            - 此处修正为 8 空格，与 `try` 对齐。
        """
        try:
            if self.client is None:
                self.finished_err.emit("未配置 AI 客户端")
                return

            # 尝试流式调用
            full_text = ""
            if hasattr(self.client, 'chat_stream'):
                try:
                    def _on_chunk(text):
                        self.chunk_received.emit(text)

                    full_text = self.client.chat_stream(
                        prompt=self.prompt,
                        system=self.system,
                        callback=_on_chunk,
                    )
                except Exception as e:
                    # 流式失败，回退到非流式
                    print(f"[AI插件] 流式失败，回退: {e}")
                    full_text = self.client.chat(
                        prompt=self.prompt,
                        system=self.system,
                    )
            else:
                # 无流式接口，直接调用
                full_text = self.client.chat(
                    prompt=self.prompt,
                    system=self.system,
                )

            if self._cancelled:
                self.finished_err.emit("已取消")
                return

            self.finished_ok.emit(full_text or "")

        except Exception as e:
            import traceback
            traceback.print_exc()
            # 翻译常见错误为友好提示
            friendly_msg = self._friendly_error(str(e), self.client)
            self.finished_err.emit(friendly_msg)

    @staticmethod
    def _friendly_error(raw: str, client) -> str:
        """把底层错误翻译为友好的中文提示"""
        provider = getattr(client, 'provider', '') if client else ''
        base_url = getattr(client, 'base_url', '') if client else ''

        # 连接被拒绝
        if 'Connection refused' in raw or 'WinError 10061' in raw \
                or '积极拒绝' in raw:
            if provider == 'ollama':
                return (
                    "无法连接到 Ollama 服务（localhost:11434）。\n\n"
                    "请尝试：\n"
                    "  1. 启动 Ollama：在终端运行 `ollama serve`\n"
                    "  2. 或从 https://ollama.com/download 安装 Ollama\n"
                    "  3. 或切换 AI 提供商：工具 → AI 助手 → 配置 AI\n"
                )
            return (
                f"无法连接到服务器：{base_url or '未知'}\n\n"
                f"请检查网络连接，或切换 AI 提供商。"
            )

        # 超时
        if 'timeout' in raw.lower() or 'timed out' in raw.lower():
            return (
                f"请求超时（服务器响应过慢）。\n\n"
                f"请检查网络，或换一个模型/提供商。"
            )

        # 认证失败
        if '401' in raw or 'Unauthorized' in raw \
                or 'API Key 无效' in raw:
            return (
                "API Key 无效或未配置。\n\n"
                "请打开：工具 → AI 助手 → 配置 AI，重新填写。"
            )

        # 404 / 找不到
        if '404' in raw:
            return (
                f"服务器返回 404（模型或路径不存在）。\n\n"
                f"请检查 Model 名称是否正确。\n"
                f"当前 base_url: {base_url or '未知'}"
            )

        # 限流
        if '429' in raw or 'rate limit' in raw.lower():
            return (
                "请求频率超过限制（429）。\n\n"
                "请稍后再试，或升级 API 套餐。"
            )

        # 默认：原样返回
        return raw


# ============================================================
# AI 结果对话框
# ============================================================
class AIResultDialog(QDialog):
    """
    AI 结果展示对话框。

    显示 AI 返回的文本，支持:
    - 复制
    - 替换选中代码
    - 插入到光标处
    - 取消
    """

    def __init__(self, title: str, main_window,
                 enable_insert: bool = True, parent=None):
        super().__init__(parent or main_window)

        self.setWindowTitle(title)
        self.resize(820, 620)

        self.main_window = main_window
        self._result_text = ""
        self._worker: Optional[AIWorker] = None
        # 关键：保存到实例属性，供 _build_ui 使用
        self._enable_insert = enable_insert

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 状态标签
        self.status_label = QLabel("正在生成...")
        self.status_label.setStyleSheet(
            "color: #f0ad4e; padding: 4px; font-size: 12px;"
        )
        layout.addWidget(self.status_label)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # 无限循环
        self.progress.setMaximumHeight(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        # 结果浏览器
        self.browser = QTextBrowser()
        self.browser.setFont(QFont("Microsoft YaHei", 10))
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser, 1)

        # 按钮
        btn_layout = QHBoxLayout()

        self.copy_btn = QPushButton("📋 复制")
        self.copy_btn.clicked.connect(self._on_copy)
        self.copy_btn.setEnabled(False)
        btn_layout.addWidget(self.copy_btn)

        # 关键修复：使用 self._enable_insert 而不是 enable_insert
        if self._enable_insert:
            self.replace_btn = QPushButton("↩ 替换选中代码")
            self.replace_btn.clicked.connect(self._on_replace)
            self.replace_btn.setEnabled(False)
            btn_layout.addWidget(self.replace_btn)

            self.insert_btn = QPushButton("⬇ 插入到光标处")
            self.insert_btn.clicked.connect(self._on_insert)
            self.insert_btn.setEnabled(False)
            btn_layout.addWidget(self.insert_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)
        btn_layout.addWidget(self.cancel_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel { color: #d4d4d4; }
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                padding: 8px;
                font-family: "Microsoft YaHei", "Consolas", monospace;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 70px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
            QProgressBar {
                background-color: #2d2d2d;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #0e639c;
                border-radius: 2px;
            }
        """)

    # --------------------------------------------------------
    # 流式接收
    # --------------------------------------------------------
    def set_worker(self, worker: AIWorker):
        """绑定 Worker"""
        self._worker = worker
        worker.chunk_received.connect(self._on_chunk)
        worker.finished_ok.connect(self._on_finished)
        worker.finished_err.connect(self._on_error)

        self.cancel_btn.setVisible(True)
        self.cancel_btn.clicked.connect(worker.cancel)

    def _on_chunk(self, text: str):
        """收到流式片段"""
        self._result_text += text
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)

        # 自动滚动到底
        try:
            sb = self.browser.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception:
            pass

    def _on_finished(self, full_text: str):
        """完成"""
        if full_text:
            self._result_text = full_text

        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)

        self.status_label.setText("✓ 完成")
        self.status_label.setStyleSheet(
            "color: #7ec850; padding: 4px; font-size: 12px;"
        )
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

        self.copy_btn.setEnabled(bool(self._result_text))
        # 使用 self._enable_insert
        if self._enable_insert:
            self.replace_btn.setEnabled(bool(self._result_text))
            self.insert_btn.setEnabled(bool(self._result_text))

        self.cancel_btn.setVisible(False)

    def _on_error(self, err: str):
        """失败"""
        self.status_label.setText(f"✗ 失败: {err}")
        self.status_label.setStyleSheet(
            "color: #f14c4c; padding: 4px; font-size: 12px;"
        )
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        self.browser.setPlainText(f"生成失败：\n\n{err}")
        self.cancel_btn.setVisible(False)

    # --------------------------------------------------------
    # 按钮动作
    # --------------------------------------------------------
    def _on_copy(self):
        """复制到剪贴板"""
        try:
            QApplication.clipboard().setText(self._result_text)
            QMessageBox.information(self, "已复制", "已复制到剪贴板")
        except Exception as e:
            QMessageBox.warning(self, "复制失败", str(e))

    def _extract_code(self, text: str) -> str:
        """从 markdown 里提取第一个代码块"""
        import re
        # 匹配 ```lang\n...\n```
        pattern = re.compile(r'```[^\n]*\n(.*?)\n?```', re.DOTALL)
        m = pattern.search(text)
        if m:
            return m.group(1)
        # 无代码块，返回全文（去掉首尾空白）
        return text.strip()

    def _on_replace(self):
        """替换选中代码"""
        if not self.main_window:
            return

        try:
            proxy = self.main_window.tabs.current_proxy()
            if not proxy or not proxy.sc:
                QMessageBox.warning(self, "替换失败", "当前没有编辑器")
                return

            code = self._extract_code(self._result_text)
            if not code:
                QMessageBox.warning(self, "替换失败", "结果为空")
                return

            proxy.sc.replaceSelectedText(code)
            self.status_label.setText("✓ 已替换选中代码")
            self.status_label.setStyleSheet(
                "color: #7ec850; padding: 4px; font-size: 12px;"
            )
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "替换失败", str(e))

    def _on_insert(self):
        """插入到光标处"""
        if not self.main_window:
            return

        try:
            proxy = self.main_window.tabs.current_proxy()
            if not proxy or not proxy.sc:
                QMessageBox.warning(self, "插入失败", "当前没有编辑器")
                return

            code = self._extract_code(self._result_text)
            if not code:
                QMessageBox.warning(self, "插入失败", "结果为空")
                return

            pos = proxy.sc.SendScintilla(proxy.sc.SCI_GETCURRENTPOS)
            proxy.sc.SendScintilla(
                proxy.sc.SCI_INSERTTEXT, pos, code.encode('utf-8')
            )
            self.status_label.setText("✓ 已插入到光标处")
            self.status_label.setStyleSheet(
                "color: #7ec850; padding: 4px; font-size: 12px;"
            )
            self.accept()

        except Exception as e:
            QMessageBox.warning(self, "插入失败", str(e))

    def _on_cancel(self):
        """取消请求"""
        if self._worker:
            self._worker.cancel()

    def closeEvent(self, event):
        """关闭时取消请求"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        super().closeEvent(event)


# ============================================================
# AI 配置对话框
# ============================================================
class AIConfigDialog(QDialog):
    """
    AI 配置对话框。

    配置 Provider / API Key / Model / Base URL。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("AI 助手配置")
        self.resize(520, 420)

        self._build_ui()
        self._apply_style()
        self._load_settings()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 说明
        info = QLabel(
            "配置 AI 服务。支持 OpenAI、DeepSeek、Ollama（本地）、"
            "通义千问、Moonshot、智谱 GLM、Claude 等。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; padding: 8px; font-size: 12px;")
        layout.addWidget(info)

        # 表单
        form = QFormLayout()

        # Provider
        self.provider_combo = QComboBox()
        if AIClientFactory:
            try:
                providers = AIClientFactory.list_providers()
                for key, display in providers:
                    self.provider_combo.addItem(display, key)
            except Exception:
                self._add_fallback_providers()
        else:
            self._add_fallback_providers()

        self.provider_combo.currentIndexChanged.connect(
            self._on_provider_changed
        )
        form.addRow("提供商:", self.provider_combo)

        # API Key
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("sk-...")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        form.addRow("API Key:", self.api_key_edit)

        # Model
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("模型:", self.model_combo)

        # Base URL
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText(
            "留空使用默认地址（如 https://api.openai.com/v1）"
        )
        form.addRow("Base URL:", self.base_url_edit)

        layout.addLayout(form)

        # 提示
        hint = QLabel(
            "💡 提示：\n"
            "  · Ollama 本地模型无需 API Key\n"
            "  · API Key 存储在 QSettings（明文），请勿在共享环境使用"
        )
        hint.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()

        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self._on_test)
        btn_layout.addWidget(self.test_btn)

        btn_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)

        layout.addLayout(btn_layout)

    def _add_fallback_providers(self):
        """添加后备提供商列表"""
        fallback = [
            ("OpenAI", "openai"),
            ("Ollama (本地)", "ollama"),
            ("DeepSeek", "deepseek"),
            ("通义千问", "qwen"),
            ("Moonshot", "moonshot"),
            ("智谱 GLM", "zhipu"),
            ("Anthropic Claude", "claude"),
        ]
        for display, key in fallback:
            self.provider_combo.addItem(display, key)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel { color: #d4d4d4; }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                min-height: 20px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
                font-size: 12px;
                min-width: 70px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
        """)

    def _load_settings(self):
        """加载已有配置"""
        try:
            settings = QSettings("QingCao", "AI")
            provider = settings.value("provider", "openai", type=str)
            api_key = settings.value("api_key", "", type=str)
            model = settings.value("model", "", type=str)
            base_url = settings.value("base_url", "", type=str)

            # 选中 provider
            for i in range(self.provider_combo.count()):
                if self.provider_combo.itemData(i) == provider:
                    self.provider_combo.setCurrentIndex(i)
                    break

            self.api_key_edit.setText(api_key)
            self.model_combo.setCurrentText(model)
            self.base_url_edit.setText(base_url)

            # 更新模型列表
            self._on_provider_changed()

        except Exception as e:
            print(f"[AI插件] 加载配置失败: {e}")

    def _on_provider_changed(self):
        """Provider 变化 → 更新模型列表"""
        provider = self.provider_combo.currentData()

        # 清空
        self.model_combo.clear()

        # 从工厂获取默认模型
        models = []
        if AIClientFactory:
            try:
                models = AIClientFactory.get_default_models(provider)
            except Exception:
                pass

        # 后备默认模型
        if not models:
            defaults = {
                "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
                "ollama": ["llama3.2", "llama3.1", "qwen2.5"],
                "deepseek": ["deepseek-chat", "deepseek-coder"],
                "qwen": ["qwen-plus", "qwen-turbo", "qwen-max"],
                "moonshot": ["moonshot-v1-8k"],
                "zhipu": ["glm-4", "glm-4-plus", "glm-4-flash"],
                "claude": [
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                ],
            }
            models = defaults.get(provider, [])

        for m in models:
            self.model_combo.addItem(m)

        # Ollama 不需要 API Key
        if provider == "ollama":
            self.api_key_edit.setPlaceholderText("（本地模型无需 Key）")
        else:
            self.api_key_edit.setPlaceholderText("sk-...")

    def _on_test(self):
        """测试连接"""
        provider = self.provider_combo.currentData()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()
        base_url = self.base_url_edit.text().strip()

        if provider != "ollama" and not api_key:
            QMessageBox.warning(self, "测试失败", "请先填写 API Key")
            return

        if not _AI_CLIENT_OK:
            QMessageBox.warning(
                self, "测试失败",
                "core.ai_client 模块不可用，无法测试连接"
            )
            return

        if not _REQUESTS_OK:
            QMessageBox.warning(
                self, "测试失败",
                "缺少 requests 库\n请运行: pip install requests"
            )
            return

        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中...")

        try:
            client = AIClientFactory.create(
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )

            result = client.chat(
                prompt="请回复：OK",
                system="你是一个测试助手，只需回复 OK。",
            )

            QMessageBox.information(
                self, "测试成功",
                f"✓ 连接成功！\n\n返回：{str(result)[:200]}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "测试失败",
                f"✗ 连接失败：\n\n{e}"
            )
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("🔌 测试连接")

    def _on_save(self):
        """保存配置"""
        provider = self.provider_combo.currentData()
        api_key = self.api_key_edit.text().strip()
        model = self.model_combo.currentText().strip()
        base_url = self.base_url_edit.text().strip()

        try:
            settings = QSettings("QingCao", "AI")
            settings.setValue("provider", provider)
            settings.setValue("api_key", api_key)
            settings.setValue("model", model)
            settings.setValue("base_url", base_url)
            settings.sync()

            QMessageBox.information(self, "保存成功", "AI 配置已保存")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))


# ============================================================
# 插件主类
# ============================================================
class Plugin(PluginBase):
    """
    AI 助手插件。

    继承 PluginBase，实现 on_activate / on_deactivate。
    """

    NAME = PLUGIN_NAME
    VERSION = PLUGIN_VERSION
    DESCRIPTION = PLUGIN_DESCRIPTION
    AUTHOR = "hedongwei"
    PERMISSIONS = [
        PERMISSION_NETWORK,
        PERMISSION_EDITOR_READ,
        PERMISSION_EDITOR_WRITE,
        PERMISSION_DIALOG,
    ]

    def __init__(self):
        super().__init__()
        self._menus: List[Any] = []
        self._client = None
        self._active_dialogs: List[AIResultDialog] = []

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def on_activate(self):
        """激活时调用"""
        self.api.log(f"AI 助手 v{self.VERSION} 已激活")

        # 检查依赖
        if not _AI_CLIENT_OK:
            self.api.show_status(
                "AI 助手：core.ai_client 不可用", 5000, "error"
            )
            return

        if not _REQUESTS_OK:
            self.api.show_status(
                "AI 助手：缺少 requests 库，请运行 pip install requests",
                5000, "warning"
            )

        # 加载 AI 客户端（如果已配置）
        try:
            self._client = load_ai_client_from_settings()
            if self._client:
                self.api.log("已从配置加载 AI 客户端")
            else:
                self.api.log("AI 客户端未配置，使用前请先设置")
        except Exception as e:
            self.api.log(f"加载 AI 客户端失败: {e}", "error")

        # 注册菜单
        self._register_menus()

        # 注册快捷键
        self._register_shortcuts()

        self.api.log("AI 助手初始化完成")

    def on_deactivate(self):
        """卸载时调用"""
        # 关闭所有活动对话框
        for dlg in list(self._active_dialogs):
            try:
                dlg.close()
            except Exception:
                pass
        self._active_dialogs.clear()

        # 清理菜单
        for action in self._menus:
            try:
                self.api.remove_menu(action)
            except Exception:
                pass
        self._menus.clear()

        self.api.log("AI 助手已卸载")

    # --------------------------------------------------------
    # 菜单注册
    # --------------------------------------------------------
    def _register_menus(self):
        """注册菜单项"""
        menu_items = [
            ("工具/AI 助手/💡 解释代码", self._on_explain, "Ctrl+Shift+E"),
            ("工具/AI 助手/🔧 重构代码", self._on_refactor, "Ctrl+Shift+R"),
            ("工具/AI 助手/🐛 修复 Bug", self._on_fix, None),
            ("工具/AI 助手/💬 添加注释", self._on_comment, None),
            ("工具/AI 助手/📖 生成 Docstring", self._on_docstring, None),
            ("工具/AI 助手/🧪 生成单元测试", self._on_tests, None),
            ("工具/AI 助手/⚡ 性能优化", self._on_optimize, None),
            ("工具/AI 助手/🔍 Code Review", self._on_review, None),
            ("工具/AI 助手/📝 代码摘要", self._on_summary, None),
        ]

        for path, callback, shortcut in menu_items:
            try:
                action = self.api.add_menu(path, callback, shortcut)
                if action:
                    self._menus.append(action)
            except Exception as e:
                self.api.log(f"注册菜单 {path} 失败: {e}", "error")

        # 语言转换子菜单
        convert_langs = [
            ("Python", "python"),
            ("JavaScript", "javascript"),
            ("TypeScript", "typescript"),
            ("Java", "java"),
            ("C++", "cpp"),
            ("Go", "go"),
            ("Rust", "rust"),
        ]

        for display, lang in convert_langs:
            try:
                action = self.api.add_menu(
                    f"工具/AI 助手/🔄 转换为 {display}",
                    lambda checked=False, l=lang: self._on_convert(l),
                    None
                )
                if action:
                    self._menus.append(action)
            except Exception:
                pass

        # 配置菜单
        try:
            config_action = self.api.add_menu(
                "工具/AI 助手/⚙ 配置 AI...",
                self._on_configure,
                None
            )
            if config_action:
                self._menus.append(config_action)
        except Exception:
            pass

    def _register_shortcuts(self):
        """注册快捷键"""
        shortcuts = [
            ("Ctrl+Shift+A", self._show_ai_menu),
            ("Ctrl+Shift+E", self._on_explain),
            ("Ctrl+Shift+R", self._on_refactor),
        ]

        for key, callback in shortcuts:
            try:
                self.api.register_shortcut(key, callback)
            except Exception as e:
                self.api.log(f"注册快捷键 {key} 失败: {e}", "error")

    # --------------------------------------------------------
    # 核心动作
    # --------------------------------------------------------
    def _get_context(self) -> Tuple[str, str, str]:
        """
        获取当前编辑器上下文。

        返回:
            (代码, 语言, 文件路径)
        """
        try:
            editor = self.api.current_editor()
            if editor is None:
                return ("", "", "")

            # 优先使用选中代码
            code = editor.sc.selectedText() if editor.sc else ""
            if not code:
                # 无选中：使用全文
                code = editor.sc.text() if editor.sc else ""

            # 检测语言
            filepath = ""
            if editor.document:
                filepath = editor.document.filepath or ""

            lang = "text"
            if filepath:
                ext = os.path.splitext(filepath)[1].lower()
                lang = LANG_EXT_MAP.get(ext, "text")

            return (code, lang, filepath)

        except Exception as e:
            self.api.log(f"获取上下文失败: {e}", "error")
            return ("", "", "")

    def _ensure_client(self) -> bool:
        """确保 AI 客户端可用"""
        if not _AI_CLIENT_OK:
            self.api.show_message(
                "AI 不可用",
                "core.ai_client 模块不可用。\n"
                "请确认项目结构完整。"
            )
            return False

        if self._client is None:
            self._client = load_ai_client_from_settings()

        if self._client is None:
            reply = self.api.ask_yes_no(
                "未配置 AI",
                "AI 客户端尚未配置。\n\n是否现在配置？"
            )
            if reply:
                self._on_configure()
            return False

        return True

    def _run_ai_action(self, prompt_template: str, title: str,
                        system_prompt: str,
                        **format_kwargs):
        """
        执行 AI 动作的通用方法。

        参数:
            prompt_template: 提示词模板（含 {code}, {lang} 等占位符）
            title: 对话框标题
            system_prompt: 系统提示词
            **format_kwargs: 模板额外参数

        修复说明（P3-4）:
            - 删除了原先未使用的 replace_mode 参数。
              该参数声明后从未被读取，所有调用方均依赖默认行为
              （AIResultDialog 的 enable_insert=True）。
        """
        if not self._ensure_client():
            return

        # 获取上下文
        code, lang, filepath = self._get_context()

        if not code.strip():
            self.api.show_message(
                "无代码",
                "请先打开文件或选中代码。"
            )
            return

        # 格式化提示词
        try:
            prompt = prompt_template.format(
                code=code,
                lang=lang,
                src_lang=lang,
                **format_kwargs
            )
        except KeyError as e:
            self.api.log(f"提示词格式化失败（缺少 {e}）", "error")
            # 使用默认值
            prompt = prompt_template.format(
                code=code, lang=lang, src_lang=lang,
                dst_lang="Python", style="Google",
                framework="pytest"
            )

        # 创建对话框
        main_window = self.api.win
        dlg = AIResultDialog(
            title=title,
            main_window=main_window,
            enable_insert=True,
            parent=main_window,
        )
        self._active_dialogs.append(dlg)

        # 创建 Worker
        worker = AIWorker(self._client, prompt, system_prompt)
        dlg.set_worker(worker)
        worker.start()

        # 显示对话框（exec_ 会阻塞直到关闭）
        dlg.exec_()

        # 清理
        if dlg in self._active_dialogs:
            self._active_dialogs.remove(dlg)

    # --------------------------------------------------------
    # 具体动作
    # --------------------------------------------------------
    def _on_explain(self):
        """解释代码"""
        self._run_ai_action(
            PROMPT_EXPLAIN,
            "💡 解释代码",
            "你是资深开发者，用中文简洁地解释代码逻辑，分点说明。",
        )

    def _on_refactor(self):
        """重构代码"""
        self._run_ai_action(
            PROMPT_REFACTOR,
            "🔧 重构代码",
            "你是重构专家，保持功能不变，提升可读性和可维护性。",
        )

    def _on_fix(self):
        """修复 Bug"""
        self._run_ai_action(
            PROMPT_FIX,
            "🐛 修复 Bug",
            "你是调试专家，找出代码中的 bug 并修复。",
        )

    def _on_comment(self):
        """添加注释"""
        self._run_ai_action(
            PROMPT_COMMENT,
            "💬 添加注释",
            "你是文档专家，为代码添加清晰的中文注释。",
        )

    def _on_docstring(self):
        """生成 Docstring"""
        self._run_ai_action(
            PROMPT_DOCSTRING,
            "📖 生成 Docstring",
            "你是 Python 文档专家，使用 Google 风格 docstring。",
            style="Google",
        )

    def _on_tests(self):
        """生成单元测试"""
        self._run_ai_action(
            PROMPT_TESTS,
            "🧪 生成单元测试",
            "你是测试工程师，生成完整的单元测试。",
            framework="pytest",
        )

    def _on_optimize(self):
        """性能优化"""
        self._run_ai_action(
            PROMPT_OPTIMIZE,
            "⚡ 性能优化",
            "你是性能优化专家，优化代码性能但保持功能不变。",
        )

    def _on_review(self):
        """Code Review"""
        self._run_ai_action(
            PROMPT_REVIEW,
            "🔍 Code Review",
            "你是资深开发者，用中文分点指出代码中的问题。",
        )

    def _on_summary(self):
        """代码摘要"""
        self._run_ai_action(
            PROMPT_SUMMARY,
            "📝 代码摘要",
            "用中文简洁总结代码的核心功能。",
        )

    def _on_convert(self, dst_lang: str):
        """转换语言"""
        self._run_ai_action(
            PROMPT_CONVERT,
            f"🔄 转换为 {dst_lang}",
            "你是多语言专家，保持代码功能等价地转换语言。",
            dst_lang=dst_lang,
        )

    # --------------------------------------------------------
    # AI 菜单（快捷键 Ctrl+Shift+A）
    # --------------------------------------------------------
    def _show_ai_menu(self):
        """显示 AI 快速菜单"""
        try:
            main_window = self.api.win
            if main_window is None:
                return

            # 获取全局鼠标位置
            from PyQt5.QtGui import QCursor
            pos = QCursor.pos()

            menu = QMenu(main_window)

            menu.addAction("💡 解释代码", self._on_explain)
            menu.addAction("🔧 重构代码", self._on_refactor)
            menu.addAction("🐛 修复 Bug", self._on_fix)
            menu.addSeparator()
            menu.addAction("💬 添加注释", self._on_comment)
            menu.addAction("📖 生成 Docstring", self._on_docstring)
            menu.addAction("🧪 生成单元测试", self._on_tests)
            menu.addSeparator()
            menu.addAction("⚡ 性能优化", self._on_optimize)
            menu.addAction("🔍 Code Review", self._on_review)
            menu.addAction("📝 代码摘要", self._on_summary)
            menu.addSeparator()
            menu.addAction("⚙ 配置 AI...", self._on_configure)

            menu.exec_(pos)

        except Exception as e:
            self.api.log(f"显示 AI 菜单失败: {e}", "error")
            import traceback
            traceback.print_exc()

    # --------------------------------------------------------
    # 配置
    # --------------------------------------------------------
    def _on_configure(self):
        """打开 AI 配置"""
        try:
            main_window = self.api.win
            dlg = AIConfigDialog(parent=main_window)

            if dlg.exec_() == QDialog.Accepted:
                # 重新加载客户端
                try:
                    self._client = load_ai_client_from_settings()
                    if self._client:
                        self.api.show_status(
                            "AI 配置已更新", 2000, "success"
                        )
                    else:
                        self.api.show_status(
                            "AI 配置保存失败，请检查", 3000, "warning"
                        )
                except Exception as e:
                    self.api.log(f"重新加载客户端失败: {e}", "error")
        except Exception as e:
            self.api.log(f"打开配置对话框失败: {e}", "error")
            import traceback
            traceback.print_exc()


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    win = QMainWindow()
    win.setWindowTitle("AI 助手插件测试")
    win.resize(900, 600)

    # 模拟 tabs
    class FakeTabs:
        def current_proxy(self):
            return None
        def count(self):
            return 0

    win.tabs = FakeTabs()

    # 创建 PluginAPI
    api = None
    if _PLUGIN_BASE_OK:
        try:
            api = PluginAPI(
                win,
                permissions=[
                    PERMISSION_NETWORK,
                    PERMISSION_EDITOR_READ,
                    PERMISSION_EDITOR_WRITE,
                    PERMISSION_DIALOG,
                ],
                plugin_name=PLUGIN_NAME,
            )
        except Exception as e:
            print(f"创建 PluginAPI 失败: {e}")

    # 创建插件
    plugin = Plugin()
    print(f"插件: {plugin.NAME} v{plugin.VERSION}")
    print(f"描述: {plugin.DESCRIPTION}")
    print(f"权限: {plugin.PERMISSIONS}")
    print()

    # 激活
    if api is not None:
        try:
            plugin.activate(api)
            print("插件激活成功")
        except Exception as e:
            print(f"插件激活失败: {e}")
            import traceback
            traceback.print_exc()

    # 打开配置对话框（可选）
    if api is not None and "--config" in sys.argv:
        plugin._on_configure()

    QTimer.singleShot(2000, app.quit)
    sys.exit(app.exec_())