# -*- coding: utf-8 -*-
"""AI 行内补全（Ghost Text 风格，基于 Scintilla 注解）

设计取舍
--------
本模块此前是**死代码**：完整实现但从未被实例化，且自带三个缺陷。
本次重写并接线，同时修掉这三个问题：

1. **`_pending` 跨线程写**（原缺陷）
   原实现里 `_pending` 由工作线程复位、主线程读取。用户在工作线程
   返回前敲的字符会被静默丢弃（`on_text_changed` 里 `if self._pending:
   return`）。现改为在**主线程**用信号回调复位。

2. **`QTimer.singleShot(5000, ...)` 不可取消**（原缺陷）
   原实现每显示一次建议就挂一个 5 秒定时器，无法取消，快速连续建议会
   堆积一堆待发回调。现改为复用一个 `singleShot` 定时器（`start()` 会
   自动重置）。

3. **每次按键都可能触发 AI 请求**（原缺陷）
   原实现由 `on_text_changed` 自动触发。AI 请求有延迟也有费用，
   自动触发会打扰输入并产生大量请求。现改为**显式触发**：
   `request_now()`（绑定快捷键），并在首选项里默认**关闭**。

渲染方式
--------
用 **Scintilla 注解**（`SCI_ANNOTATIONSETTEXT`）在当前行下方显示建议，
而不是 CallTip。原因：

* 注解本就是"给某一行加一段提示"设计的，CallTip 是给**函数签名**用的；
* 注解不遮挡光标附近的代码，CallTip 会盖住后面的内容；
* 注解支持独立配色，视觉上更像"灰色幽灵文本"。

接受建议用 `accept_suggestion()` / `clear_suggestion()`，由快捷键或
按钮触发。
"""
import threading

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QColor


# Scintilla 注解样式号（用 STYLE_LASTPREDEFINED 之后的自定义样式）
ANNOTATION_STYLE = 20

# 触发所需的最少列数：太短没有上下文，补全质量低且浪费请求
MIN_PREFIX_CHARS = 3

# 取多少行上文作为上下文
CONTEXT_LINES = 20

# 单次请求最小间隔（秒），避免用户连按快捷键打爆额度
MIN_REQUEST_INTERVAL = 1.0


def is_language_tag(head: str) -> bool:
    """判断某一行是不是代码围栏的语言标记

    例如 ```python / ```javascript / ```c++ 里的 `python` 等。
    这类首行必须被剥掉，否则会被当成补全结果返回。
    """
    h = (head or "").strip().lower()
    if not h or " " in h:
        return False
    if h in _KNOWN_LANGUAGE_TAGS:
        return True
    # 未知但形如标识符（纯字母数字，长度 <= 12）→ 也当作语言标记
    probe = h.replace("+", "").replace("#", "").replace("-", "")
    return probe.isalnum() and 0 < len(h) <= 12


# 常见语言标记（小写）——命中即视为语言名而非代码
_KNOWN_LANGUAGE_TAGS = {
    "python", "py", "javascript", "js", "typescript", "ts", "java",
    "c", "cpp", "c++", "csharp", "c#", "go", "rust", "ruby", "php",
    "swift", "kotlin", "scala", "sql", "bash", "sh", "shell",
    "powershell", "html", "css", "json", "yaml", "yml", "xml",
    "markdown", "md", "text", "plaintext", "diff", "ini", "toml",
}


class AIInlineCompleter(QObject):
    """AI 行内补全器

    用法::

        c = AIInlineCompleter(editor_widget, ai_client)
        c.set_enabled(True)
        c.request_now()            # 用户按快捷键触发
        # 建议以注解形式显示；用户按接受键时：
        c.accept_suggestion()
    """

    # 内部：工作线程 → 主线程
    _result_ready = pyqtSignal(str, int)     # (建议文本, 请求序号)
    _request_failed = pyqtSignal(str, int)

    def __init__(self, editor, ai_client, parent=None):
        """editor 可以是 QsciScintilla，也可以是持有 `.sc` 的 EditorWidget"""
        super().__init__(parent)
        self.editor = self._resolve_scintilla(editor)
        self.ai_client = ai_client
        self.enabled = False

        self._suggestion = ""
        self._annotation_line = -1
        self._busy = False
        self._last_request_time = 0.0
        # 递增序号：丢弃过期响应（用户已移动光标/再次触发）
        self._seq = 0

        # 5 秒后自动清除建议（复用同一个定时器，可被 start() 重置）
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.setInterval(5000)
        self._clear_timer.timeout.connect(self.clear_suggestion)

        self._result_ready.connect(self._on_result)
        self._request_failed.connect(self._on_failed)
        self._apply_annotation_style()

    # --------------------------------------------------------
    # 初始化辅助
    # --------------------------------------------------------
    @staticmethod
    def _resolve_scintilla(editor):
        """兼容 QsciScintilla 与 EditorWidget（后者有 .sc 属性）"""
        if editor is None:
            return None
        for attr in ('sc', 'scintilla'):
            inner = getattr(editor, attr, None)
            if inner is not None and hasattr(inner, 'SendScintilla'):
                return inner
        return editor if hasattr(editor, 'SendScintilla') else None

    def _apply_annotation_style(self):
        """让注解显示为灰色，接近 ghost text 观感"""
        if not self.editor:
            return
        try:
            self.editor.SendScintilla(
                self.editor.SCI_STYLESETFORE, ANNOTATION_STYLE,
                QColor("#7a7a7a").rgb() & 0xFFFFFF)
            self.editor.SendScintilla(
                self.editor.SCI_STYLESETITALIC, ANNOTATION_STYLE, 1)
            # 注解默认样式
            self.editor.SendScintilla(
                self.editor.SCI_ANNOTATIONSETSTYLE, ANNOTATION_STYLE)
        except Exception:
            pass

    # --------------------------------------------------------
    # 开关
    # --------------------------------------------------------
    def set_enabled(self, enabled):
        """启用/禁用；禁用时立即清除已显示的建议"""
        self.enabled = bool(enabled)
        if not self.enabled:
            self.clear_suggestion()
        return self.enabled

    def set_client(self, ai_client):
        """更换 AI 客户端（配置改变后调用）"""
        self.ai_client = ai_client

    def has_suggestion(self) -> bool:
        return bool(self._suggestion)

    def get_suggestion(self) -> str:
        return self._suggestion

    # --------------------------------------------------------
    # 触发
    # --------------------------------------------------------
    def request_now(self, force=False):
        """立即请求补全（用户显式触发时调用）。

        参数:
            force: True 时忽略最小间隔限制

        返回:
            是否真的发起了请求（False 表示未启用/太短/过于频繁/正在忙）
        """
        import time
        if not self.enabled:
            return False
        if not self.editor or not self.ai_client:
            return False
        if self._busy:
            return False
        if not force:
            now = time.time()
            if now - self._last_request_time < MIN_REQUEST_INTERVAL:
                return False

        line, col = self._cursor_position()
        if col < MIN_PREFIX_CHARS:
            return False

        context = self._collect_context(line, col)
        if not context.strip():
            return False

        self.clear_suggestion()
        self._busy = True
        self._last_request_time = time.time()
        self._seq += 1
        seq = self._seq

        # 请求参数：按任务分档，避免动辄输出几千 token
        max_tokens = 256
        try:
            from core.ai_client import tokens_for
            max_tokens = tokens_for("tiny")
        except Exception:
            pass

        panel = self

        def worker():
            try:
                prompt = (
                    "基于以下代码，只输出接下来最可能的一行代码。"
                    "不要解释、不要重复已有内容、不要加代码块标记：\n"
                    "```\n" + context + "\n```\n继续："
                )
                # 优先流式接口（若可用），取前若干字符即可，避免长等待
                parts = []
                if hasattr(panel.ai_client, 'chat_stream'):
                    def on_chunk(t):
                        parts.append(t)
                        return len("".join(parts)) < 200
                    text = panel.ai_client.chat_stream(
                        prompt=prompt,
                        system="你是代码补全引擎，只输出一行补全内容。",
                        callback=on_chunk,
                        max_tokens=max_tokens,
                    )
                    if not text:
                        text = "".join(parts)
                else:
                    text = panel.ai_client._chat(
                        [{"role": "user", "content": prompt}],
                        system="你是代码补全引擎，只输出一行补全内容。")
                text = panel._clean(text or "")
                panel._result_ready.emit(text, seq)
            except Exception as e:
                panel._request_failed.emit(str(e), seq)

        threading.Thread(target=worker, daemon=True,
                         name="ai-inline-complete").start()
        return True

    # 兼容旧调用名（原先由 on_text_changed 自动触发；现在语义等同显式触发）
    def on_text_changed(self):
        """保留兼容：不再自动触发，只做最小间隔检查后请求。

        真正的自动触发由调用方决定（默认关闭）。若调用方仍希望
        "输入即补全"，可连接编辑器 textChanged 到本方法。
        """
        return self.request_now()

    # --------------------------------------------------------
    # 上下文与结果
    # --------------------------------------------------------
    def _cursor_position(self):
        try:
            return self.editor.getCursorPosition()
        except Exception:
            return (0, 0)

    def _collect_context(self, line, col):
        """取当前行之前若干行作为上下文"""
        lines = []
        start = max(0, line - CONTEXT_LINES)
        for i in range(start, line + 1):
            try:
                text = self.editor.text(i)
            except Exception:
                continue
            if i == line:
                text = text[:col]
            lines.append(text)
        return "\n".join(lines)

    @staticmethod
    def _clean(text: str) -> str:
        """清洗模型输出：只留第一行**有效代码**

        处理顺序很重要（这里踩过坑）：

          1. 先**剥掉围栏**并取内部内容。若先把 ``` 全部 `replace` 掉
             再取第一行，会拿到围栏后的**空行** → 结果变空字符串；
             而 ```python 形式还会把语言标记 "python" 当成代码返回。
          2. 再去掉模型可能加的前缀说明。
          3. 最后取第一个**非空**行。
        """
        t = (text or "").strip()
        if not t:
            return ""

        fence = "```"
        if fence in t:
            parts = t.split(fence)
            inner = ""
            for seg in parts[1:]:
                seg = seg.strip()
                if not seg:
                    continue
                # 去掉首行的语言标记（```python / ```javascript / ```c++ …）
                lines = seg.split("\n")
                head = lines[0].strip()
                if is_language_tag(head):
                    seg = "\n".join(lines[1:]).strip()
                if seg:
                    inner = seg
                break
            t = inner if inner else t.replace(fence, "").strip()
            if not t:
                return ""

        # 去掉常见前缀
        for prefix in ("继续：", "补全：", "代码：", "继续:", "补全:", "代码:"):
            if t.startswith(prefix):
                t = t[len(prefix):].strip()

        # 只取第一个非空行
        for ln in t.split("\n"):
            if ln.strip():
                return ln.rstrip()
        return ""

    def _on_result(self, text, seq):
        """主线程：显示建议（在此复位 _busy，避免跨线程写标志）"""
        self._busy = False
        if seq != self._seq:
            return                      # 过期响应
        if not text or not self.editor:
            return
        self._show_suggestion(text)

    def _on_failed(self, err, seq):
        self._busy = False
        if seq != self._seq:
            return
        # 补全失败静默处理：不该在编辑器里弹错误对话框打扰输入
        print("[AIInline] 补全失败: %s" % err)

    # --------------------------------------------------------
    # 显示 / 清除 / 接受
    # --------------------------------------------------------
    def _show_suggestion(self, text):
        if not text or not self.editor:
            return
        line, _col = self._cursor_position()
        self._suggestion = text
        self._annotation_line = line
        try:
            self.editor.SendScintilla(
                self.editor.SCI_ANNOTATIONSETTEXT, line,
                ("→ " + text).encode('utf-8'))
            self.editor.SendScintilla(
                self.editor.SCI_ANNOTATIONSETVISIBLE, 1)
        except Exception:
            pass
        # 5 秒后自动清除（复用定时器，可被下次 show 重置）
        self._clear_timer.start()

    def clear_suggestion(self):
        """清除建议（不改动文档内容）"""
        self._suggestion = ""
        if self.editor:
            try:
                self.editor.SendScintilla(
                    self.editor.SCI_ANNOTATIONCLEARALL)
            except Exception:
                pass
        self._annotation_line = -1
        try:
            self._clear_timer.stop()
        except Exception:
            pass

    def accept_suggestion(self):
        """接受建议：插入到光标处

        通过 Scintilla 的**可撤销**插入实现，因此用户的 Ctrl+Z 能撤销；
        插入后清空建议并刷新撤销记录。
        """
        if not self._suggestion or not self.editor:
            return False
        text = self._suggestion
        try:
            pos = self.editor.SendScintilla(
                self.editor.SCI_GETCURRENTPOS)
            # 用 SCI_INSERTTEXT 保证可被撤销（sc.insert 亦可）
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos, text.encode('utf-8'))
        except Exception:
            return False
        self.clear_suggestion()
        return True

    def cancel(self):
        """取消进行中的请求（丢弃其结果）"""
        self._seq += 1                  # 使在途响应过期
        self._busy = False
        self.clear_suggestion()
