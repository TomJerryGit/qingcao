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

import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QSettings, Qt, QThread, QTimer, pyqtSignal
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
except ImportError:                       # 独立运行插件时的兜底
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
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
                 system: str = "", parent=None,
                 use_history: bool = False, max_tokens=None):
        super().__init__(parent)
        self.client = client
        self.prompt = prompt
        self.system = system
        self._cancelled = False
        # 多轮上下文：True 时该请求会带上之前轮次并记录本轮
        self.use_history = bool(use_history)
        # 按任务分档的 token 上限（None = 用客户端默认）
        self.max_tokens = max_tokens

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
            stream_kw = {"use_history": self.use_history}
            if self.max_tokens:
                stream_kw["max_tokens"] = self.max_tokens
            if hasattr(self.client, 'chat_stream'):
                try:
                    def _on_chunk(text):
                        self.chunk_received.emit(text)

                    full_text = self.client.chat_stream(
                        prompt=self.prompt,
                        system=self.system,
                        callback=_on_chunk,
                        **stream_kw,
                    )
                except Exception as e:
                    # 流式失败，回退到非流式
                    print(f"[AI插件] 流式失败，回退: {e}")
                    full_text = self.client.chat(
                        prompt=self.prompt,
                        system=self.system,
                        use_history=self.use_history,
                    )
            else:
                # 无流式接口，直接调用
                full_text = self.client.chat(
                    prompt=self.prompt,
                    system=self.system,
                    use_history=self.use_history,
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
                "请求超时（服务器响应过慢）。\n\n"
                "请检查网络，或换一个模型/提供商。"
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
        # 追问/新会话所需的状态。这里必须**显式初始化**：
        # 原先这些属性只在 _run_ai_action 里动态赋值，导致
        # start_new_session() 里的 getattr(self,'_client',None) 拿到 None，
        # 清空上下文的动作被宽 except 静默吞掉（表现为"新会话无效"）。
        self._client = None
        self._system_prompt = ""
        self._code_context = ""
        self._max_tokens = None
        self._action_title = ""
        self._chunk_start = None
        self._chunk_buf = ""
        self._wait_timer = None
        self._wait_start = None
        self._wait_phase = ""
        self._first_chunk_at = None
        self._stream_chars = 0

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

        # 追问输入（多轮对话）
        #
        # 设计说明：只传历史而不给追问入口，多轮就没有意义。
        # 这里放在浏览器与按钮之间，回车即发送。
        follow_row = QHBoxLayout()
        self.follow_edit = QLineEdit()
        self.follow_edit.setPlaceholderText(
            "继续追问（回车发送）—— 例如「把上面的代码改成用 for 循环」")
        self.follow_edit.returnPressed.connect(self._on_follow_up)
        self.follow_edit.setEnabled(False)
        follow_row.addWidget(self.follow_edit, 1)

        self.follow_btn = QPushButton("➤ 追问")
        self.follow_btn.clicked.connect(self._on_follow_up)
        self.follow_btn.setEnabled(False)
        follow_row.addWidget(self.follow_btn)

        self.multi_turn_check = QCheckBox("记住上下文")
        self.multi_turn_check.setChecked(True)
        self.multi_turn_check.setToolTip(
            "勾选后，本次对话的往来会一并发送给模型，\n"
            "可以连续追问（如「再简化一点」「换成列表推导式」）。\n"
            "取消勾选则每次都是独立提问。")
        follow_row.addWidget(self.multi_turn_check)

        self.new_session_btn = QPushButton("＋ 新会话")
        self.new_session_btn.setToolTip(
            "清空对话上下文并开始新话题。\n"
            "上一个话题的记录会留在窗口里，但不再发送给模型。")
        self.new_session_btn.clicked.connect(self.start_new_session)
        follow_row.addWidget(self.new_session_btn)
        layout.addLayout(follow_row)

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

    # --------------------------------------------------------
    # 等待/推理状态反馈
    # --------------------------------------------------------
    def _start_waiting(self, phase: str = "生成中"):
        """开始显示带计时的等待状态

        为什么要计时：大模型（尤其本地 Ollama 在 CPU 上）首个 token
        可能要等十几秒。此前状态栏只有静态"正在生成..."，用户无法判断
        是真的在跑还是已经卡死。加上累计耗时后，"没反应"变成"可见进度"。
        """
        self._wait_phase = phase
        self._wait_start = time.time()
        self._first_chunk_at = None
        self._stream_chars = 0
        self.status_label.setStyleSheet(
            "color: #f0ad4e; padding: 4px; font-size: 12px;")
        if getattr(self, "_wait_timer", None) is None:
            self._wait_timer = QTimer(self)
            self._wait_timer.setInterval(200)
            self._wait_timer.timeout.connect(self._tick_waiting)
        self._wait_timer.start()
        self._tick_waiting()

    def _tick_waiting(self):
        """定时刷新等待文案（每 200ms）"""
        if getattr(self, "_wait_start", None) is None:
            return
        elapsed = time.time() - self._wait_start
        phase = getattr(self, "_wait_phase", "生成中")
        if self._first_chunk_at is None:
            # 还没收到任何片段：连上了但模型在思考
            self.status_label.setText(
                "%s… 已等待 %.1f 秒（模型思考中，首字输出较慢属正常）"
                % (phase, elapsed))
        else:
            speed = ""
            if elapsed > 0:
                speed = " · %.0f 字/秒" % (self._stream_chars / elapsed)
            self.status_label.setText(
                "接收中… %.1f 秒 · 已收到 %d 字%s"
                % (elapsed, self._stream_chars, speed))

    def _stop_waiting(self):
        """停止等待计时"""
        try:
            if getattr(self, "_wait_timer", None) is not None:
                self._wait_timer.stop()
        except Exception:
            pass
        self._wait_start = None

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
    def start_new_session(self):
        """开始新会话：清空上下文，但保留窗口内已有记录

        为什么保留记录：用户可能想对照上一个话题的结论。
        但上下文（会发给模型的部分）必须清空，否则新话题会带上
        无关的旧对话，既费 token 也干扰回答。
        """
        cleared = False
        try:
            client = getattr(self, '_client', None)
            if client is not None and hasattr(client, 'reset_history'):
                client.reset_history()
                cleared = True
        except Exception:
            cleared = False
        # 清掉追加缓冲，避免后续片段拼到旧文本上
        self._chunk_start = None
        self._chunk_buf = ''
        self._result_text += "\n\n---\n\n**（新会话开始，上下文已清空）**\n\n"
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)
        if cleared:
            self.status_label.setText("已开始新会话 · 上下文已清空")
        else:
            # 不要静默：没有客户端时上下文其实没被清，必须让用户知道
            self.status_label.setText(
                "已开始新会话（注意：未绑定 AI 客户端，上下文未清空）")
        self.status_label.setStyleSheet(
            "color: #4ec9b0; padding: 4px; font-size: 12px;")
        self.follow_edit.setFocus()

    # --------------------------------------------------------
    # 缓存命中
    # --------------------------------------------------------
    def show_cached(self, text: str):
        """直接显示缓存结果（不发请求）

        命中缓存时仍要：
          * 让按钮可用（复制/替换/插入）；
          * 允许继续追问 —— 此时把缓存内容当作首轮的 assistant 回复
            写回客户端历史，保证追问的上下文与"重新生成"一致。
        """
        self._result_text = text or ""
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)

        self.status_label.setText(
            "✓ 来自缓存（未发起新请求）· 输入追问可继续对话")
        self.status_label.setStyleSheet(
            "color: #4ec9b0; padding: 4px; font-size: 12px;")
        self.progress.setRange(0, 1)
        self.progress.setValue(1)

        self.copy_btn.setEnabled(bool(self._result_text))
        if self._enable_insert:
            self.replace_btn.setEnabled(bool(self._result_text))
            self.insert_btn.setEnabled(bool(self._result_text))

        self.cancel_btn.setVisible(False)
        self.follow_edit.setEnabled(True)
        self.follow_btn.setEnabled(True)

        # 把缓存内容补进历史，使追问的上下文与首次生成一致
        try:
            client = getattr(self, '_client', None)
            if client is not None and hasattr(client, '_history'):
                sys_p = getattr(self, '_system_prompt', '') or ''
                code = getattr(self, '_code_context', '') or ''
                if code.strip():
                    client._history.extend([
                        {"role": "user",
                         "content": "（缓存命中，原始代码略）"},
                        {"role": "assistant", "content": self._result_text},
                    ])
                    client._trim_history()
        except Exception:
            pass

    def set_worker(self, worker: AIWorker):
        """绑定 Worker（首轮）"""
        self._worker = worker
        self._system_prompt = getattr(worker, 'system', '') or ''
        worker.chunk_received.connect(self._on_chunk)
        worker.finished_ok.connect(self._on_finished)
        worker.finished_err.connect(self._on_error)

        self.cancel_btn.setVisible(True)
        self.cancel_btn.clicked.connect(worker.cancel)
        # 开始显示带计时的等待状态
        self._start_waiting("生成中")

    # --------------------------------------------------------
    # 多轮追问
    # --------------------------------------------------------
    def _build_follow_prompt(self, question: str) -> str:
        """把追问与原代码上下文组合。

        首轮已经通过历史记录了原代码，但历史会被裁剪（默认 10 轮），
        所以追问时**重新附上代码**更稳妥，也便于模型定位。
        """
        code = getattr(self, '_code_context', '') or ''
        if not code.strip():
            return question
        return ("最初分析的代码：\n```\n%s\n```\n\n%s" % (code, question))

    def _on_follow_up(self):
        """发送追问（在同一对话框内继续对话）"""
        if self._worker is not None and self._worker.isRunning():
            return                      # 上一轮还没结束
        question = self.follow_edit.text().strip()
        if not question:
            return
        if self._client is None or not self._system_prompt:
            return

        # 把本轮问答追加到显示区，保持对话可读
        try:
            self._result_text += "\n\n---\n\n**你：** %s\n\n" % question
            self.browser.setMarkdown(self._result_text)
        except Exception:
            pass

        self.follow_edit.clear()
        self.follow_edit.setEnabled(False)
        self.follow_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.cancel_btn.setVisible(True)
        self._start_waiting("追问中")

        use_history = self.multi_turn_check.isChecked()
        worker = AIWorker(
            self._client,
            self._build_follow_prompt(question),
            self._system_prompt,
            parent=self,
            use_history=use_history,
            max_tokens=getattr(self, '_max_tokens', None),
        )
        # 追问只累积新片段：清空当前累积，避免与上一轮拼接错乱
        self._result_text = self._result_text        # 保留历史显示
        self._chunk_start = len(self._result_text)
        worker.chunk_received.connect(self._on_chunk)
        worker.finished_ok.connect(self._on_follow_finished)
        worker.finished_err.connect(self._on_error)
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(worker.cancel)
        self._worker = worker
        worker.start()

    def _on_follow_finished(self, full_text: str):
        """追问完成"""
        tail = full_text or ''
        # 片段已逐个追加过；这里只做收尾状态
        if not tail and len(self._result_text) <= getattr(self, '_chunk_start', 0):
            self._result_text += "（无输出）"
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)

        elapsed = 0.0
        if getattr(self, '_wait_start', None):
            elapsed = time.time() - self._wait_start
        self._stop_waiting()
        self.status_label.setText(
            "✓ 完成 · 总耗时 %.1f 秒" % elapsed if elapsed else "✓ 完成")
        self.status_label.setStyleSheet(
            "color: #7ec850; padding: 4px; font-size: 12px;")
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.copy_btn.setEnabled(bool(self._result_text))
        self.cancel_btn.setVisible(False)
        # 允许继续追问
        self.follow_edit.setEnabled(True)
        self.follow_btn.setEnabled(True)
        self.follow_edit.setFocus()

    def _on_chunk(self, text: str):
        """收到流式片段

        追问场景下 `_chunk_start` 记录了本轮开始的位置，
        新片段追加在其后（而不是覆盖整段显示）。
        """
        # 首个片段到达 → 记录时刻，状态从"思考中"切到"接收中"
        if getattr(self, "_first_chunk_at", None) is None:
            self._first_chunk_at = time.time()
            # 立即刷新一次文案：否则要等 200ms 定时器才从
            # "模型思考中" 变成 "接收中"，首字反馈会有可感的延迟
            self._tick_waiting()
        self._stream_chars = getattr(self, "_stream_chars", 0) + len(text)

        start = getattr(self, '_chunk_start', None)
        if start is None:
            self._result_text += text
        else:
            self._result_text = self._result_text[:start] + \
                (getattr(self, '_chunk_buf', '') + text)
            self._chunk_buf = getattr(self, '_chunk_buf', '') + text
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
        """首轮完成"""
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
        # 停下来计时，并显示总耗时
        elapsed = 0.0
        if getattr(self, '_wait_start', None):
            elapsed = time.time() - self._wait_start
        self._stop_waiting()
        if elapsed:
            self.status_label.setText("✓ 完成 · 总耗时 %.1f 秒" % elapsed)
        # 首轮完成 → 允许追问
        self.follow_edit.setEnabled(True)
        self.follow_btn.setEnabled(True)

    def _on_error(self, err: str):
        """失败"""
        self._stop_waiting()
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

        # Ollama 探测结果提示（仅在 provider=ollama 时显示）
        self.ollama_hint = QLabel("")
        self.ollama_hint.setWordWrap(True)
        self.ollama_hint.setStyleSheet(
            "color: #4ec9b0; font-size: 11px; padding: 4px 0;")
        self.ollama_hint.setVisible(False)
        layout.addWidget(self.ollama_hint)

        # 结果缓存开关
        self.cache_check = QCheckBox("复用结果缓存（相同代码 + 相同动作不重复请求）")
        self.cache_check.setToolTip(
            "开启后，若 provider / 模型 / 温度 / token 上限 / 提示词完全相同，\n"
            "直接显示上次结果，省一次请求。\n"
            "多轮追问不使用缓存。缓存仅存内存，退出即清空。\n"
            "如需强制重新生成，取消勾选此项。")
        try:
            self.cache_check.setChecked(
                QSettings("QingCao", "AI").value(
                    "result_cache", True, type=bool))
        except Exception:
            self.cache_check.setChecked(True)
        layout.addWidget(self.cache_check)

        # 会话窗口开关
        self.session_check = QCheckBox("复用同一个 AI 对话窗口（非模态，保留上下文）")
        self.session_check.setToolTip(
            "开启（默认）：所有 AI 动作共用一个非模态窗口，\n"
            "切换标签、继续操作都不会丢上下文，可直接追问。\n"
            "关闭：每次动作弹一个独立模态对话框（旧行为）。")
        try:
            self.session_check.setChecked(
                QSettings("QingCao", "AI").value(
                    "session_window", True, type=bool))
        except Exception:
            self.session_check.setChecked(True)
        layout.addWidget(self.session_check)

        # 提示
        hint = QLabel(
            "💡 提示：\n"
            "  · Ollama 本地模型无需 API Key；模型列表会自动从本机 Ollama 读取\n"
            "  · 更完整的模型管理（拉取/删除/已加载）见：工具 → AI 助手 → 🦙 Ollama 管理面板\n"
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

        # Ollama：优先用本地服务真实安装的模型（覆盖硬编码列表）
        # 硬编码列表只是"连不上时"的兜底提示，避免下拉框为空。
        ollama_note = ""
        if provider == "ollama":
            models, ollama_note = self._fetch_ollama_models(models)

        for m in models:
            self.model_combo.addItem(m)

        # Ollama 不需要 API Key
        if provider == "ollama":
            self.api_key_edit.setPlaceholderText("（本地模型无需 Key）")
        else:
            self.api_key_edit.setPlaceholderText("sk-...")

        # 把 Ollama 的探测结果提示给用户
        if ollama_note:
            try:
                self.ollama_hint.setText(ollama_note)
                self.ollama_hint.setVisible(True)
            except Exception:
                pass
        else:
            try:
                self.ollama_hint.setVisible(False)
            except Exception:
                pass

    def _fetch_ollama_models(self, fallback: List[str]):
        """向本机 Ollama 查询已安装模型。

        返回 (模型名列表, 提示文本)。查询失败时回退到 fallback，
        并把失败原因作为提示返回 —— 不阻塞、不抛异常。
        """
        try:
            host = (self.base_url_edit.text().strip()
                    or OllamaClient.DEFAULT_HOST)
            # base_url 可能是 OpenAI 兼容端点（带 /v1），去掉后用于原生 API
            host = host.rstrip('/')
            if host.endswith('/v1'):
                host = host[:-3]
            cli = OllamaClient(host)
            ok, models = cli.list_models()
            if not ok:
                return fallback, ("⚠️ 未能连接 Ollama（%s）。下拉框显示的是"
                                  "常见模型名，请确认服务已启动：ollama serve"
                                  % host)
            if not models:
                return fallback, ("⚠️ Ollama 已连接，但尚未安装任何模型。"
                                  "先运行：ollama pull qwen2.5:7b   "
                                  "（或使用 工具 → AI 助手 → 🦙 Ollama 管理面板）")
            names = [m["name"] for m in models]
            return names, ("✅ 已从本机 Ollama 读取 %d 个模型：%s"
                           % (len(names), "、".join(names[:5])
                              + ("…" if len(names) > 5 else "")))
        except Exception as e:
            return fallback, "⚠️ 查询 Ollama 失败：%s" % e

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
            # 结果缓存开关
            try:
                settings.setValue("result_cache",
                                  self.cache_check.isChecked())
                settings.setValue("session_window",
                                  self.session_check.isChecked())
            except Exception:
                pass
            settings.sync()

            QMessageBox.information(self, "保存成功", "AI 配置已保存")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))


# ============================================================
# Ollama 管理面板
# ============================================================
class OllamaPanel(QWidget):
    """Ollama 本地模型管理面板（停靠窗口）

    功能：
      * 服务状态（运行中 / 未启动）+ 版本号
      * 已安装模型列表（名称、大小、参数量、量化、修改时间）
      * 内存中已加载模型（/api/ps）
      * 拉取新模型（/api/pull，带实时进度）
      * 删除模型（/api/delete）
      * 连通性测试
      * 一键把 Base URL / 模型填入 AI 配置

    说明：
      * 所有网络调用都在**后台 `threading.Thread`** 中执行，不阻塞 UI；
      * 跨线程结果通过 `QObject` 的 `pyqtSignal` 桥回主线程 —— 这是本项目
        已验证的正确样板（参见 `core/search.py::FileSearcher`）。
        刻意**不用 `QThread`**：`QThread` 若在运行中被析构，Qt 会打印
        "QThread: Destroyed while thread is still running" 并可能
        `qFatal()`；`threading.Thread`（daemon）没有这个析构约束，
        窗口关闭时不会崩。
      * 面板可独立于 AI 配置对话框使用。
    """

    # 由主插件转发给 PluginAPI
    log = pyqtSignal(str)
    # 后台线程 → 主线程的信号桥
    _refresh_done = pyqtSignal(bool, str, list, list)
    _pull_progress = pyqtSignal(int, str)
    _pull_done = pyqtSignal(bool, str)

    def __init__(self, plugin=None, parent=None, auto_refresh=True):
        super().__init__(parent)
        self._plugin = plugin
        self._client = OllamaClient()
        self._models: List[Dict[str, Any]] = []
        self._pull_thread = None
        self._busy = False
        self._build_ui()
        # 后台线程 → 主线程的连接
        self._refresh_done.connect(self._on_refresh_done)
        self._pull_progress.connect(self._on_pull_progress)
        self._pull_done.connect(self._on_pull_done)
        # 首次自动刷新（测试可传 auto_refresh=False 跳过）
        if auto_refresh:
            QTimer.singleShot(200, self.refresh)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- 状态行 ---
        top = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #888; font-size: 15px;")
        self.status_label = QLabel("正在检测 Ollama 服务…")
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        self.test_btn = QPushButton("🔌 测试连接")
        self.test_btn.clicked.connect(self.test_connection)
        top.addWidget(self.status_dot)
        top.addWidget(self.status_label, 1)
        top.addWidget(self.test_btn)
        top.addWidget(self.refresh_btn)
        layout.addLayout(top)

        # --- 模型列表 ---
        layout.addWidget(QLabel("已安装模型："))
        self.model_list = QListWidget()
        self.model_list.setAlternatingRowColors(True)
        self.model_list.currentRowChanged.connect(self._on_selection_changed)
        self.model_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.model_list, 1)

        # --- 操作按钮 ---
        btns = QHBoxLayout()
        self.pull_btn = QPushButton("⬇ 拉取模型…")
        self.pull_btn.clicked.connect(self._on_pull)
        self.delete_btn = QPushButton("🗑 删除选中")
        self.delete_btn.clicked.connect(self._on_delete)
        self.delete_btn.setEnabled(False)
        self.use_btn = QPushButton("✓ 用于 AI 配置")
        self.use_btn.clicked.connect(self._on_use_for_ai)
        self.use_btn.setEnabled(False)
        btns.addWidget(self.pull_btn)
        btns.addWidget(self.delete_btn)
        btns.addWidget(self.use_btn)
        btns.addStretch(1)
        layout.addLayout(btns)

        # --- 进度 ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%  %v")
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.detail_label)

        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #0e639c; color: #ffffff;
                border: none; padding: 5px 12px; border-radius: 3px;
                min-width: 70px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #3c3c3c; color: #666666;
            }
            QListWidget {
                border: 1px solid #3c3c3c; border-radius: 3px;
            }
        """)

    # --------------------------------------------------------
    # 状态刷新
    # --------------------------------------------------------
    def _set_status(self, running: bool, text: str):
        self.status_dot.setStyleSheet(
            "color: %s; font-size: 15px;" % ("#4ec9b0" if running else "#f44747")
        )
        self.status_label.setText(text)

    def refresh(self):
        """刷新服务状态 + 模型列表（后台线程）"""
        if self._busy:
            return
        self._busy = True
        self.refresh_btn.setEnabled(False)
        self._set_status(False, "正在检测…")

        panel = self

        def _worker():
            # 任何异常都必须转成 ok=False：否则回调永不触发，
            # 面板会永久停在"正在检测…"且 _busy 卡死（无法再刷新）。
            try:
                ok, status = panel._client.status_text()
                models = panel._client.list_models()[1] if ok else []
                running = panel._client.list_running()[1] if ok else []
            except Exception as e:
                ok, status, models, running = (
                    False, "探测异常: %s" % e, [], [])
            panel._refresh_done.emit(ok, status, models, running)

        th = threading.Thread(target=_worker, daemon=True,
                              name="ollama-refresh")
        th.start()
        self._refresh_thread = th

    def _on_refresh_done(self, ok, status, models, running):
        """刷新线程完成后的 UI 更新（在主线程执行）"""
        self._busy = False
        self.refresh_btn.setEnabled(True)
        self._set_status(ok, status)
        self._populate(models, running)

    def _populate(self, models: List[Dict[str, Any]],
                  running: List[Dict[str, Any]]):
        running_names = {r["name"] for r in running}
        self.model_list.clear()
        self._models = models
        for m in models:
            loaded = "  ● 已加载" if m["name"] in running_names else ""
            extra = "/".join(x for x in (m["parameter_size"],
                                         m["quantization"]) if x)
            item = QListWidgetItem("%s   [%s]%s\n     %s%s" % (
                m["name"], m["size_text"], loaded,
                (extra + "   ") if extra else "", m["modified_at"]))
            item.setData(Qt.UserRole, m["name"])
            item.setToolTip("名称: %s\n大小: %s\n参数: %s\n量化: %s\n家族: %s\n修改: %s" % (
                m["name"], m["size_text"], m["parameter_size"] or "-",
                m["quantization"] or "-", m["family"] or "-",
                m["modified_at"]))
            self.model_list.addItem(item)

        n = len(models)
        nr = len(running)
        self.detail_label.setText(
            "共 %d 个模型%s。双击可复制名称。" % (
                n, ("，内存中已加载 %d 个" % nr) if nr else ""))
        self._on_selection_changed(self.model_list.currentRow())

    def _on_selection_changed(self, row: int):
        has = row >= 0 and row < len(self._models)
        self.delete_btn.setEnabled(has and not self._busy)
        self.use_btn.setEnabled(has)

    # --------------------------------------------------------
    # 操作
    # --------------------------------------------------------
    def test_connection(self):
        ok, status = self._client.status_text()
        self._set_status(ok, status)
        if ok:
            QMessageBox.information(
                self, "Ollama", "连接成功。\n\n服务状态：%s\nOpenAI 兼容端点：%s"
                % (status, self._client.openai_base_url()))
        else:
            QMessageBox.warning(
                self, "Ollama 未连接",
                "无法连接 Ollama 服务。\n\n%s\n\n"
                "请确认：\n"
                "  1. 已安装 Ollama（https://ollama.com/download）\n"
                "  2. 服务已启动：在终端运行 `ollama serve`\n"
                "  3. 地址正确：%s" % (status, self._client.host))

    def _selected_name(self) -> str:
        row = self.model_list.currentRow()
        if 0 <= row < len(self._models):
            return self._models[row]["name"]
        return ""

    def _on_item_double_clicked(self, item):
        """双击复制模型名（方便粘贴到终端 ollama run）"""
        name = item.data(Qt.UserRole) or ""
        if not name:
            return
        try:
            QApplication.clipboard().setText(name)
            self.detail_label.setText("已复制到剪贴板：%s" % name)
        except Exception:
            pass

    def _on_pull(self):
        if self._busy:
            return
        name, ok = QInputDialog.getText(
            self, "拉取 Ollama 模型",
            "模型名称（例如 qwen2.5:7b、deepseek-r1:8b、llama3.2）：")
        if not ok or not name.strip():
            return
        name = name.strip()
        self._busy = True
        self.pull_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.progress.setFormat("%p%  %v")
        self.detail_label.setText("正在拉取 %s …" % name)

        self._pull_name = name
        panel = self

        def _worker():
            def on_event(ev):
                # NDJSON 事件样例：
                # {"status":"pulling manifest"}
                # {"status":"downloading","total":N,"completed":M}
                total = ev.get("total") or 0
                done_n = ev.get("completed") or 0
                pct = int(done_n * 100 / total) if total else 0
                panel._pull_progress.emit(pct, str(ev.get("status") or ""))
                return not getattr(panel, '_pull_cancelled', False)

            ok2, msg = panel._client.pull_model(name, progress=on_event)
            panel._pull_done.emit(ok2, msg)

        th = threading.Thread(target=_worker, daemon=True, name="ollama-pull")
        th.start()
        self._pull_thread = th

    def _on_pull_progress(self, pct, status):
        """拉取进度（主线程）"""
        if pct:
            self.progress.setValue(pct)
        self.detail_label.setText("%s  %s" % (status, getattr(self, '_pull_name', '')))

    def _on_pull_done(self, ok2, msg):
        """拉取结束（主线程）"""
        name = getattr(self, '_pull_name', '')
        self._busy = False
        self.pull_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.detail_label.setText("%s：%s" % (name, msg))
        self.refresh()
        if ok2:
            QMessageBox.information(self, "Ollama",
                                    "模型 %s 拉取完成。" % name)
        else:
            QMessageBox.warning(self, "拉取失败", "%s\n%s" % (name, msg))

    def _on_delete(self):
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(
                self, "删除模型",
                "确定删除本地模型 %s 吗？\n\n此操作会释放其占用的磁盘空间，"
                "且不可撤销（需要时可用「拉取模型」重新下载）。" % name,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        ok, msg = self._client.delete_model(name)
        if ok:
            self.log.emit("[Ollama] 已删除模型 %s" % name)
            self.refresh()
        else:
            QMessageBox.warning(self, "删除失败", msg)

    def _on_use_for_ai(self):
        """把选中的模型写入 AI 配置（provider=ollama）"""
        name = self._selected_name()
        if not name:
            return
        try:
            s = QSettings("QingCao", "AI")
            s.setValue("provider", "ollama")
            s.setValue("model", name)
            s.setValue("base_url", self._client.openai_base_url())
            s.setValue("api_key", "")
            s.sync()
        except Exception as e:
            QMessageBox.warning(self, "写入配置失败", str(e))
            return
        self.log.emit("[Ollama] AI 配置已切换为 %s" % name)
        QMessageBox.information(
            self, "已应用",
            "AI 配置已更新：\n\n  提供商：Ollama (本地)\n  模型：%s\n"
            "  端点：%s\n\n下次使用 AI 功能即生效。"
            % (name, self._client.openai_base_url()))

    # --------------------------------------------------------
    # 供主插件调用
    # --------------------------------------------------------
    def status_summary(self) -> str:
        """给状态栏用的一行摘要（不阻塞：只做短超时探测）"""
        ok, text = self._client.status_text()
        if not ok:
            return "Ollama: 未启动"
        n = len(self._client.list_models()[1])
        return "Ollama: %s · %d 个模型" % (text, n)

    # --------------------------------------------------------
    # 线程收尾（避免 QThread 运行中被销毁 —— Qt 会 abort）
    # --------------------------------------------------------
    def _stop_threads(self, timeout_ms: int = 1500):
        """等待后台线程结束（尽力而为）。

        面板用的是 daemon `threading.Thread`，因此**不会**出现
        `QThread` 那种"运行中被析构 → qFatal"的问题；这里只是尽量
        让进行中的请求收尾，避免退出时打出无意义的 traceback。
        """
        for attr in ('_refresh_thread', '_pull_thread'):
            th = getattr(self, attr, None)
            if th is None:
                continue
            try:
                if th.is_alive():
                    th.join(timeout_ms / 1000.0)
            except Exception:
                pass

    def closeEvent(self, event):
        """面板关闭时等待线程结束"""
        self._stop_threads()
        super().closeEvent(event)


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

        # 注册命令面板命令
        self._register_commands()

        # 内联补全（默认关闭；此前该模块是死代码，从未接线）
        self._setup_inline_completer()

        # 注册 Ollama 管理面板（默认隐藏，从菜单打开）
        self._setup_ollama_panel()

        self.api.log("AI 助手初始化完成")

    # --------------------------------------------------------
    # Ollama 管理面板
    # --------------------------------------------------------
    def _setup_ollama_panel(self):
        """创建 Ollama 管理面板 + 状态栏指示 + 菜单入口。

        面板能力（全部基于 Ollama 原生 REST API）：
          * 服务状态与版本
          * 已安装模型列表（大小/参数量/量化/修改时间）
          * 内存中已加载模型
          * 拉取模型（带进度）、删除模型
          * 测试连接、一键写入 AI 配置
        """
        try:
            self.ollama_panel = OllamaPanel(plugin=self)
        except Exception as e:
            self.api.log("创建 Ollama 面板失败: %s" % e, "error")
            return

        # 面板内的日志转给插件日志
        try:
            self.ollama_panel.log.connect(lambda m: self.api.log(m))
        except Exception:
            pass

        # 注册为停靠面板（默认隐藏）
        try:
            self._ollama_dock = self.api.add_panel(
                "Ollama 管理", self.ollama_panel,
                area="right", visible=False,
            )
        except Exception as e:
            self._ollama_dock = None
            self.api.log("注册 Ollama 面板失败: %s" % e, "error")

        # 菜单项：打开面板 / 快速测试
        try:
            if self._ollama_dock is not None:
                a1 = self.api.add_menu(
                    "工具/AI 助手/🦙 Ollama 管理面板",
                    lambda: self._toggle_ollama_panel(),
                    None,
                )
                if a1:
                    self._menus.append(a1)
            a2 = self.api.add_menu(
                "工具/AI 助手/🦙 Ollama 状态检查",
                lambda: self._check_ollama_status(),
                None,
            )
            if a2:
                self._menus.append(a2)
        except Exception as e:
            self.api.log("注册 Ollama 菜单失败: %s" % e, "error")

        # 状态栏常驻指示（60 秒刷新一次，避免频繁探测）
        #
        # 注意：`PluginBase` 继承自 `object`，**不是 QObject**，
        # 因此 `QTimer(self)` 会抛
        # "TypeError: argument 1 has unexpected type 'Plugin'"。
        # 定时器必须挂在面板（QWidget / QObject）上。
        try:
            self._ollama_timer = QTimer(self.ollama_panel)
            self._ollama_timer.setInterval(60_000)
            self._ollama_timer.timeout.connect(self._refresh_ollama_status)
            self._ollama_timer.start()
        except Exception as e:
            self._ollama_timer = None
            self.api.log("创建 Ollama 状态定时器失败: %s" % e, "error")

        # 启动后延迟做一次状态提示（不阻塞启动）
        try:
            QTimer.singleShot(3000, self._refresh_ollama_status)
        except Exception:
            pass

    def _toggle_ollama_panel(self):
        """显示/隐藏 Ollama 面板"""
        dock = getattr(self, '_ollama_dock', None)
        if dock is None:
            self.api.show_status(
                "Ollama 面板未注册（可能缺少 dialog 权限）", 4000, "warning")
            return
        try:
            if dock.isVisible():
                dock.hide()
            else:
                dock.show()
                dock.raise_()
                panel = getattr(self, 'ollama_panel', None)
                if panel is not None:
                    panel.refresh()
        except Exception as e:
            self.api.log("切换 Ollama 面板失败: %s" % e, "error")

    def _check_ollama_status(self):
        """菜单触发的状态检查（在后台线程做，避免阻塞 UI）"""
        panel = getattr(self, 'ollama_panel', None)
        if panel is None:
            return
        panel.test_connection()
        self._refresh_ollama_status()

    def _refresh_ollama_status(self):
        """刷新状态栏摘要（用短超时，失败静默）"""
        panel = getattr(self, 'ollama_panel', None)
        if panel is None:
            return
        try:
            summary = panel.status_summary()
            self.api.show_status("🦙 %s" % summary, 3000, "info")
        except Exception:
            pass

    def on_deactivate(self):
        """卸载时调用"""
        # 停止内联补全（清建议 + 作废在途请求）
        try:
            comp = getattr(self, 'inline_completer', None)
            if comp is not None:
                comp.cancel()
                comp.set_enabled(False)
        except Exception:
            pass
        self.inline_completer = None

        # 停止 Ollama 状态定时器 + 等待后台线程结束
        try:
            if getattr(self, '_ollama_timer', None) is not None:
                self._ollama_timer.stop()
                self._ollama_timer = None
        except Exception:
            pass
        try:
            panel = getattr(self, 'ollama_panel', None)
            if panel is not None:
                panel._stop_threads()
        except Exception:
            pass
        self.ollama_panel = None
        self._ollama_dock = None

        # 关闭会话窗口
        try:
            sess = getattr(self, '_session_window', None)
            if sess is not None:
                sess.close()
        except Exception:
            pass
        self._session_window = None

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
        # C1: 避开主窗口的 Ctrl+Shift+E / Ctrl+Shift+R
        menu_items = [
            ("工具/AI 助手/💬 打开 AI 对话窗口",
             self._on_open_session_window, None),
            ("工具/AI 助手/💡 解释代码", self._on_explain, "Ctrl+Alt+E"),
            ("工具/AI 助手/🔧 重构代码", self._on_refactor,
             "Ctrl+Alt+Shift+R"),
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
        """注册快捷键

        注意（避免重复绑定）：
            同一快捷键若既通过 `add_menu(..., shortcut)` 注册、又通过
            `api.register_shortcut(...)` 注册，会生成**两个**带同名
            QAction 的动作。Qt 对这种情况会打印
            "Ambiguous shortcut overload" 并**只触发其中一个**。

            因此约定：**菜单项的快捷键由 add_menu 负责**（菜单里能直接
            看到按键提示，可发现性更好），不再用 register_shortcut 重复
            注册；只有"没有对应菜单项"的快捷键才用 register_shortcut。

        当前状态：
            Ctrl+Shift+A     → 无菜单项，用 register_shortcut
            Ctrl+Alt+E       → 有菜单项（💡 解释代码），由菜单负责
            Ctrl+Alt+Shift+R → 有菜单项（🔧 重构代码），由菜单负责
            Ctrl+Alt+Space / Ctrl+Alt+Return
                             → 有菜单项，由菜单负责
        """
        shortcuts = [
            ("Ctrl+Shift+A", self._show_ai_menu),
        ]

        for key, callback in shortcuts:
            try:
                self.api.register_shortcut(key, callback)
            except Exception as e:
                self.api.log(f"注册快捷键 {key} 失败: {e}", "error")

    # --------------------------------------------------------
    # AI 行内补全（此前 ui/ai_inline_completer.py 是死代码）
    # --------------------------------------------------------
    def _setup_inline_completer(self):
        """创建内联补全器并注册菜单。

        设计取舍：
          * **默认关闭**。每次补全都是一次真实的 AI 请求，有延迟也有
            费用；自动启用会打扰输入并可能产生大量请求。
          * **显式触发**：用户按 Ctrl+Alt+Space 才请求，Ctrl+Alt+Return
            接受建议。不做"输入即请求"。
        """
        try:
            from ui.ai_inline_completer import AIInlineCompleter
        except Exception as e:
            self.api.log("内联补全不可用: %s" % e, "warning")
            self.inline_completer = None
            return

        # 注意：`PluginBase` 继承自 `object`，**不是 QObject**，
        # 因此不能把 `self` 当 parent 传给接受 QObject 的构造器
        # （会抛 "argument 1 has unexpected type 'Plugin'"，
        #  且会让整个插件激活失败 → 所有菜单消失）。
        # 这里用无 parent + 插件实例持强引用的方式保证生命周期。
        try:
            self.inline_completer = AIInlineCompleter(None, None, parent=None)
        except Exception as e:
            self.api.log("创建内联补全器失败: %s" % e, "error")
            self.inline_completer = None
            return
        # 默认关闭，并写入首选项以便持久化
        enabled = False
        try:
            settings = QSettings("QingCao", "AI")
            enabled = settings.value("inline_completion", False, type=bool)
        except Exception:
            pass
        self.inline_completer.set_enabled(enabled)

        # 菜单：开关 + 触发 + 接受
        items = [
            ("工具/AI 助手/⌨ 切换行内补全 (Ghost Text)",
             self._toggle_inline_completer, None),
            ("工具/AI 助手/⌨ 请求行内补全",
             self._on_inline_request, "Ctrl+Alt+Space"),
            ("工具/AI 助手/⌨ 接受行内补全",
             self._on_inline_accept, "Ctrl+Alt+Return"),
        ]
        for path, cb, sc in items:
            try:
                action = self.api.add_menu(path, cb, sc)
                if action:
                    self._menus.append(action)
            except Exception as e:
                self.api.log("注册内联补全菜单失败: %s" % e, "error")

    def _sync_inline_editor(self):
        """让补全器绑定到当前编辑器（切换标签/首次使用时调用）"""
        comp = getattr(self, 'inline_completer', None)
        if comp is None:
            return None
        try:
            editor = self.api.current_editor()
            if editor is None:
                return None
            comp.set_client(self._client)
            # 编辑器变了才重新绑定
            if comp.editor is not getattr(editor, 'sc', None):
                comp.editor = comp._resolve_scintilla(editor)
                comp._apply_annotation_style()
            return comp
        except Exception:
            return None

    def _toggle_inline_completer(self):
        """开关行内补全"""
        comp = getattr(self, 'inline_completer', None)
        if comp is None:
            self.api.show_status("行内补全不可用", 3000, "warning")
            return
        now = not comp.enabled
        comp.set_enabled(now)
        try:
            QSettings("QingCao", "AI").setValue("inline_completion", now)
        except Exception:
            pass
        if now and not self._ensure_client():
            comp.set_enabled(False)
            return
        self.api.show_status(
            "AI 行内补全已%s。按 Ctrl+Alt+Space 请求建议，"
            "Ctrl+Alt+Return 接受。" % ("开启" if now else "关闭"),
            5000, "info")

    def _on_inline_request(self):
        """快捷键：请求行内补全"""
        comp = getattr(self, 'inline_completer', None)
        if comp is None:
            return
        if not comp.enabled:
            self.api.show_status(
                "AI 行内补全未开启：工具 → AI 助手 → ⌨ 切换行内补全",
                4000, "info")
            return
        if not self._ensure_client():
            return
        comp = self._sync_inline_editor()
        if comp is None:
            self.api.show_status("没有可用的编辑器", 3000, "warning")
            return
        if not comp.request_now(force=True):
            # 未发起：可能光标列数不足或正在请求
            if comp._busy:
                self.api.show_status("正在请求补全…", 2000, "info")
            else:
                self.api.show_status(
                    "请先把光标移到已有代码行之后（至少 3 列）",
                    4000, "info")

    def _on_inline_accept(self):
        """快捷键：接受行内补全建议"""
        comp = getattr(self, 'inline_completer', None)
        if comp is None or not comp.has_suggestion():
            return
        if comp.accept_suggestion():
            self.api.show_status("已插入 AI 补全（Ctrl+Z 可撤销）",
                                 3000, "success")

    # --------------------------------------------------------
    # 命令面板集成
    # --------------------------------------------------------
    def _register_commands(self):
        """把 AI 动作注册到命令面板（Ctrl+Shift+P 可搜索）

        设计说明：
            命令面板是"不想找菜单"用户的最快入口。这里注册的都是
            **已有动作**的别名，复用同一条流式实现（带缓存、多轮、
            结果可插入），不另起一套逻辑。

            额外注册一个「快速问答」命令，它走 `quick_*` 那条
            **非 UI 的编程式 API**，把结果直接写入剪贴板 ——
            适合"只想拿一段文字、不想开对话框"的场景。
        """
        cmds = [
            ("ai.explain", "AI: 解释代码", self._on_explain),
            ("ai.refactor", "AI: 重构代码", self._on_refactor),
            ("ai.fix", "AI: 修复 Bug", self._on_fix),
            ("ai.comment", "AI: 添加注释", self._on_comment),
            ("ai.docstring", "AI: 生成 Docstring", self._on_docstring),
            ("ai.tests", "AI: 生成单元测试", self._on_tests),
            ("ai.optimize", "AI: 性能优化", self._on_optimize),
            ("ai.review", "AI: Code Review", self._on_review),
            ("ai.summary", "AI: 代码摘要", self._on_summary),
            ("ai.quick_explain", "AI: 快速解释（结果复制到剪贴板）",
             self._on_quick_explain),
            ("ai.clear_cache", "AI: 清空结果缓存", self._on_clear_cache),
            ("ai.cache_stats", "AI: 查看缓存统计", self._on_cache_stats),
        ]
        for name, desc, cb in cmds:
            try:
                self.api.register_command(name, cb, description=desc)
            except Exception as e:
                self.api.log("注册命令 %s 失败: %s" % (name, e), "error")

    def _on_quick_explain(self):
        """走 quick_* 编程式 API：不开对话框，结果写剪贴板

        这条路径与 UI 的流式路径共用同一套 PROMPT_EXPLAIN 模板，
        因此结果语义一致；区别只是"交付方式"（剪贴板 vs 对话框）。
        """
        code, lang, _fp = self._get_context()
        if not code.strip():
            self.api.show_message("无代码", "请先打开文件或选中代码。")
            return
        if not self._ensure_client():
            return
        try:
            from core.ai_client import quick_explain
            # 用当前已配置的客户端，避免 quick_* 再读一遍设置
            set_ai_client(self._client)
            text = quick_explain(code, lang=lang)
        except Exception as e:
            self.api.show_message("AI 快速解释失败", str(e))
            return
        if not text:
            self.api.show_status("AI 未返回内容", 3000, "warning")
            return
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass
        self.api.show_status(
            "AI 解释已复制到剪贴板（%d 字）" % len(text), 5000, "success")

    def _on_clear_cache(self):
        """清空 AI 结果缓存"""
        try:
            cache = get_result_cache()
            if cache is None:
                self.api.show_status("缓存不可用", 3000, "warning")
                return
            n = cache.stats().get("entries", 0)
            cache.clear()
            self.api.show_status("已清空 AI 结果缓存（%d 条）" % n,
                                 4000, "success")
        except Exception as e:
            self.api.log("清空缓存失败: %s" % e, "error")

    def _on_cache_stats(self):
        """显示缓存统计"""
        try:
            cache = get_result_cache()
            if cache is None:
                self.api.show_message("AI 缓存", "缓存不可用。")
                return
            self.api.show_message(
                "AI 结果缓存",
                cache.stats_text() + "\n\n"
                "说明：键由 provider/model/temperature/max_tokens/"
                "system/提示词共同决定，任一项改变都不会命中旧结果。\n"
                "缓存仅存于内存，退出即清空。\n\n"
                "如需强制重新生成，在 工具 → AI 助手 → ⚙ 配置 AI 中"
                "取消勾选「复用结果缓存」。")
        except Exception as e:
            self.api.log("读取缓存统计失败: %s" % e, "error")

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
                        token_tier: str = "short",
                        **format_kwargs):
        """
        执行 AI 动作的通用方法。

        参数:
            prompt_template: 提示词模板（含 {code}, {lang} 等占位符）
            title: 对话框标题
            system_prompt: 系统提示词
            token_tier: 输出预算档位（tiny/short/medium/large）——
                原先所有动作都固定用 4096，对"解释代码"这类只输出
                一两段文字的任务会白等更久、也更费 token。
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

        # ---- 选择承载窗口 ----
        #
        # 两种模式：
        #   * 会话模式（默认）：复用同一个**非模态**窗口。
        #     好处是切换标签/继续操作时窗口与上下文都不丢，
        #     并且可以在同一窗口里连续执行多个动作形成对话。
        #   * 每次新建对话框：受"独立会话窗口"首选项控制，保留旧行为
        #     （模态，一个动作一个窗口）。
        main_window = self.api._host_window()
        use_session = self._session_window_enabled()
        if use_session:
            dlg = self._get_or_create_session(main_window)
            # 在已有内容后追加分隔，标识本次动作
            if dlg._result_text.strip():
                dlg._result_text += "\n\n---\n\n**▶ %s**\n\n" % title
            else:
                dlg._result_text = "**▶ %s**\n\n" % title
            dlg._chunk_start = None
            dlg._chunk_buf = ''
            try:
                dlg.browser.setMarkdown(dlg._result_text)
            except Exception:
                dlg.browser.setPlainText(dlg._result_text)
        else:
            dlg = AIResultDialog(
                title=title,
                main_window=main_window,
                enable_insert=True,
                parent=main_window,
            )
            self._active_dialogs.append(dlg)

        # 追问所需的状态：client、system、原始代码、token 档位
        dlg._client = self._client
        dlg._code_context = code
        dlg._max_tokens = tokens_for(token_tier)
        dlg._system_prompt = system_prompt
        dlg._action_title = title

        # ---- 结果缓存 ----
        #
        # 同一段代码 + 同一动作常被重复请求（切标签回来、误关重开、
        # 反复"再解释一次"）。命中缓存可省一次 HTTP 请求与相应费用。
        # 注意：**多轮追问不使用缓存**（上下文不同），只有首轮查。
        cache = get_result_cache()
        cache_key = None
        if cache is not None and self._cache_enabled():
            try:
                from core.ai_cache import AIResultCache
                cache_key = AIResultCache.make_key(
                    self._client, prompt, system_prompt, dlg._max_tokens)
            except Exception:
                cache_key = None
            if cache_key:
                hit = cache.get(cache_key)
                if hit:
                    dlg.show_cached(hit)
                    if use_session:
                        self._present_session(dlg)
                    else:
                        dlg.exec_()
                        if dlg in self._active_dialogs:
                            self._active_dialogs.remove(dlg)
                    return

        # 创建 Worker（首轮：默认记住上下文，方便直接追问）
        worker = AIWorker(
            self._client, prompt, system_prompt,
            parent=dlg,
            use_history=True,
            max_tokens=dlg._max_tokens,
        )
        # 首次成功结果写回缓存
        if cache_key:
            def _store(text, _key=cache_key, _c=cache):
                try:
                    _c.put(_key, text or "")
                except Exception:
                    pass
            worker.finished_ok.connect(_store)

        dlg.set_worker(worker)
        worker.start()

        if use_session:
            # 非模态：立即把窗口呈现给用户，不阻塞调用方。
            # 这样用户可以切标签、做别的操作，窗口与上下文都保留。
            self._present_session(dlg)
        else:
            # 旧行为：模态对话框，阻塞到关闭
            dlg.exec_()
            if dlg in self._active_dialogs:
                self._active_dialogs.remove(dlg)

    # --------------------------------------------------------
    # 会话窗口
    # --------------------------------------------------------
    def _session_window_enabled(self) -> bool:
        """是否复用同一个会话窗口（首选项，默认开启）"""
        try:
            return QSettings("QingCao", "AI").value(
                "session_window", True, type=bool)
        except Exception:
            return True

    def _get_or_create_session(self, main_window):
        """取回或创建持久会话窗口

        窗口中转的关键点：把 `exec_()`（模态阻塞）换成 `show()`，
        这样"切标签丢失上下文"的问题自然消失 —— 窗口一直开着，
        客户端历史也一直保留。
        """
        dlg = getattr(self, '_session_window', None)
        if dlg is not None:
            try:
                # 已销毁则重建
                dlg.isVisible()
            except RuntimeError:
                dlg = None
                self._session_window = None
        if dlg is None:
            dlg = AIResultDialog(
                title="AI 对话",
                main_window=main_window,
                enable_insert=True,
                parent=main_window,
            )
            # 非模态：不阻塞调用方
            dlg.setModal(False)
            dlg.setWindowTitle("AI 对话（多轮，可继续追问）")
            # 立刻绑定当前客户端，使"新会话/追问"在首轮动作之前
            # 也能正常工作（不能等到 _run_ai_action 才赋值）
            dlg._client = self._client
            self._session_window = dlg
            # 关闭时只隐藏，保留上下文；真正销毁交给 on_deactivate
            dlg.finished.connect(lambda _r: None)
        return dlg

    def _present_session(self, dlg):
        """把会话窗口显示到前台"""
        try:
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _on_open_session_window(self):
        """菜单/命令：打开 AI 对话窗口"""
        if not self._ensure_client():
            return
        main_window = self.api._host_window()
        dlg = self._get_or_create_session(main_window)
        if not dlg._result_text.strip():
            dlg._result_text = (
                "**AI 对话窗口**\n\n"
                "· 用菜单里的任意 AI 动作开始（结果会出现在这里）\n"
                "· 然后可在下方输入框连续追问，上下文会自动带上\n"
                "· 窗口不会阻塞编辑器，切换标签也不会丢上下文\n"
                "· 点「＋ 新会话」清空上下文开始新话题\n")
            try:
                dlg.browser.setMarkdown(dlg._result_text)
            except Exception:
                dlg.browser.setPlainText(dlg._result_text)
        self._present_session(dlg)

    def _cache_enabled(self) -> bool:
        """是否启用 AI 结果缓存（首选项，默认开启）"""
        try:
            return QSettings("QingCao", "AI").value(
                "result_cache", True, type=bool)
        except Exception:
            return True

    # --------------------------------------------------------
    # 具体动作
    # --------------------------------------------------------
    def _on_explain(self):
        """解释代码"""
        self._run_ai_action(
            PROMPT_EXPLAIN,
            "💡 解释代码",
            "你是资深开发者，用中文简洁地解释代码逻辑，分点说明。",
            token_tier='short',
        )

    def _on_refactor(self):
        """重构代码"""
        self._run_ai_action(
            PROMPT_REFACTOR,
            "🔧 重构代码",
            "你是重构专家，保持功能不变，提升可读性和可维护性。",
            token_tier='medium',
        )

    def _on_fix(self):
        """修复 Bug"""
        self._run_ai_action(
            PROMPT_FIX,
            "🐛 修复 Bug",
            "你是调试专家，找出代码中的 bug 并修复。",
            token_tier='medium',
        )

    def _on_comment(self):
        """添加注释"""
        self._run_ai_action(
            PROMPT_COMMENT,
            "💬 添加注释",
            "你是文档专家，为代码添加清晰的中文注释。",
            token_tier='medium',
        )

    def _on_docstring(self):
        """生成 Docstring"""
        self._run_ai_action(
            PROMPT_DOCSTRING,
            "📖 生成 Docstring",
            "你是 Python 文档专家，使用 Google 风格 docstring。",
            style="Google",
            token_tier='short',
        )

    def _on_tests(self):
        """生成单元测试"""
        self._run_ai_action(
            PROMPT_TESTS,
            "🧪 生成单元测试",
            "你是测试工程师，生成完整的单元测试。",
            framework="pytest",
            token_tier='large',
        )

    def _on_optimize(self):
        """性能优化"""
        self._run_ai_action(
            PROMPT_OPTIMIZE,
            "⚡ 性能优化",
            "你是性能优化专家，优化代码性能但保持功能不变。",
            token_tier='medium',
        )

    def _on_review(self):
        """Code Review"""
        self._run_ai_action(
            PROMPT_REVIEW,
            "🔍 Code Review",
            "你是资深开发者，用中文分点指出代码中的问题。",
            token_tier='medium',
        )

    def _on_summary(self):
        """代码摘要"""
        self._run_ai_action(
            PROMPT_SUMMARY,
            "📝 代码摘要",
            "用中文简洁总结代码的核心功能。",
            token_tier='tiny',
        )

    def _on_convert(self, dst_lang: str):
        """转换语言"""
        self._run_ai_action(
            PROMPT_CONVERT,
            f"🔄 转换为 {dst_lang}",
            "你是多语言专家，保持代码功能等价地转换语言。",
            dst_lang=dst_lang,
            token_tier='large',
        )

    # --------------------------------------------------------
    # AI 菜单（快捷键 Ctrl+Shift+A）
    # --------------------------------------------------------
    def _show_ai_menu(self):
        """显示 AI 快速菜单"""
        try:
            main_window = self.api._host_window()
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
            main_window = self.api._host_window()
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