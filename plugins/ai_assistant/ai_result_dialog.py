# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""AI 结果对话框（v2.24 拆出）。"""

from .ai_common import *  # noqa: F401,F403,F405
from .ai_worker import AIWorker


class AIResultDialog(QDialog):
    """
    AI 结果展示对话框。

    显示 AI 返回的文本，支持:
    - 复制
    - 替换选中代码
    - 插入到光标处
    - 取消
    """

    def __init__(self, title: str, main_window, enable_insert: bool = True, parent=None):
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
        self._filepath = ""
        self._chunk_start = None
        self._chunk_buf = ""
        self._wait_timer = None
        self._wait_start = None
        self._wait_phase = ""
        self._first_chunk_at = None
        self._stream_chars = 0

        # ---- 按文件归档的会话 ----
        #
        # 单一窗口 + 内部会话表。为什么这样做：
        #   编辑器里常常多个文件交替提问，如果只有一个上下文，
        #   聊 A 文件的内容会被带到 B 文件的提问里，既费 token
        #   也污染回答。这里按 filepath 归档，切换文件时换出/换入
        #   「显示文本 + 代码上下文 + 对话历史」。
        #
        # 键：文件的绝对路径；未保存的新文件用 "(未命名)" 作为键。
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._active_key = ""
        # 生成期间被切走的会话：其继续到达的片段只累积、不显示，
        # 等切回来时一次性呈现（避免片段串到别的文件窗口里）。
        self._background_bufs: Dict[str, str] = {}

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 状态标签
        self.status_label = QLabel("正在生成...")
        self.status_label.setStyleSheet("color: #f0ad4e; padding: 4px; font-size: 12px;")
        layout.addWidget(self.status_label)

        # 当前会话对应的文件（多文件归档时提示用户"在跟哪个文件对话"）
        self.session_label = QLabel("")
        self.session_label.setStyleSheet("color: #9d9d9d; padding: 0 4px 2px 4px; font-size: 11px;")
        self.session_label.setVisible(False)
        layout.addWidget(self.session_label)
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
            "继续追问（回车发送）—— 例如「把上面的代码改成用 for 循环」"
        )
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
            "取消勾选则每次都是独立提问。"
        )
        follow_row.addWidget(self.multi_turn_check)

        self.new_session_btn = QPushButton("＋ 新会话")
        self.new_session_btn.setToolTip(
            "清空对话上下文并开始新话题。\n上一个话题的记录会留在窗口里，但不再发送给模型。"
        )
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
        self.status_label.setStyleSheet("color: #f0ad4e; padding: 4px; font-size: 12px;")
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
                "%s… 已等待 %.1f 秒（模型思考中，首字输出较慢属正常）" % (phase, elapsed)
            )
        else:
            speed = ""
            if elapsed > 0:
                speed = " · %.0f 字/秒" % (self._stream_chars / elapsed)
            self.status_label.setText(
                "接收中… %.1f 秒 · 已收到 %d 字%s" % (elapsed, self._stream_chars, speed)
            )

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
        self._base_qss = """
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
"""
        self.setStyleSheet(self._base_qss)

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
            client = getattr(self, "_client", None)
            if client is not None and hasattr(client, "reset_history"):
                client.reset_history()
                cleared = True
        except Exception:
            cleared = False
        # 同步清掉本会话归档里的历史，否则切走再切回来又会被还原
        if self._active_key in self._sessions:
            self._sessions[self._active_key]["history"] = []
        self._background_bufs.pop(self._active_key, "")
        # 清掉追加缓冲，避免后续片段拼到旧文本上
        self._chunk_start = None
        self._chunk_buf = ""
        self._result_text += "\n\n---\n\n**（新会话开始，上下文已清空）**\n\n"
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)
        if cleared:
            self.status_label.setText("已开始新会话 · 上下文已清空")
        else:
            # 不要静默：没有客户端时上下文其实没被清，必须让用户知道
            self.status_label.setText("已开始新会话（注意：未绑定 AI 客户端，上下文未清空）")
        self.status_label.setStyleSheet("color: #4ec9b0; padding: 4px; font-size: 12px;")
        self.follow_edit.setFocus()

    # --------------------------------------------------------
    # 按文件归档的会话
    # --------------------------------------------------------
    @staticmethod
    def session_key(filepath: str) -> str:
        """把文件路径规范成会话键

        未保存的新文件统一归到 "(未命名)"；路径做绝对化与大小写归一
        （Windows 下 `A.PY` 与 `a.py` 应是同一个文件）。
        """
        p = (filepath or "").strip()
        if not p:
            return "(未命名)"
        try:
            return os.path.normcase(os.path.abspath(p))
        except Exception:
            return p

    def _save_active_session(self):
        """把当前显示状态存回会话表（切换文件前调用）"""
        if not self._active_key:
            return
        self._sessions[self._active_key] = {
            "text": self._result_text,
            "code": self._code_context,
            "system": self._system_prompt,
            "filepath": getattr(self, "_filepath", "") or "",
            "title": self._action_title,
            "history": list(getattr(self._client, "_history", []) or []),
        }

    def switch_to_file(self, filepath: str, title: str = ""):
        """切换到（或新建）某个文件的会话

        需要换出/换入三样东西，缺一不可：
          * 窗口显示的文本（`_result_text`）
          * 代码上下文（追问时要附带）
          * 对话历史（存在 client 上，按文件隔离）
        """
        key = self.session_key(filepath)
        if key == self._active_key:
            # 同一文件：只需刷新标题与上下文
            self._filepath = filepath or ""
            if title:
                self._action_title = title
            return self

        # 1) 存下当前会话
        self._save_active_session()

        # 2) 切到目标会话（没有就新建空的）
        sess = self._sessions.get(key)
        if sess is None:
            sess = {
                "text": self._header_for(filepath),
                "code": "",
                "system": "",
                "filepath": filepath or "",
                "title": title,
                "history": [],
            }
            self._sessions[key] = sess

        self._active_key = key
        self._result_text = sess.get("text", "")
        self._code_context = sess.get("code", "")
        self._system_prompt = sess.get("system", "") or self._system_prompt
        self._filepath = sess.get("filepath", filepath or "")
        if title:
            self._action_title = title

        # 3) 恢复该文件的历史（历史挂在 client 上，按文件换入换出）
        client = getattr(self, "_client", None)
        if client is not None and hasattr(client, "_history"):
            try:
                client._history = list(sess.get("history", []) or [])
            except Exception:
                pass

        # 4) 如果这个会话在后台生成过，把累积的片段补进来
        pending = self._background_bufs.pop(key, "")
        if pending:
            self._result_text += pending

        # 5) 刷新界面
        self._chunk_start = None
        self._chunk_buf = ""
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)
        self._update_session_label()
        return self

    @staticmethod
    def _header_for(filepath: str) -> str:
        """新会话的欢迎内容"""
        if filepath:
            import os as _os

            name = _os.path.basename(filepath)
            return (
                "**▶ 会话：%s**\n\n"
                "· 该文件拥有**独立的对话上下文**，不会与其他文件混淆\n"
                "· 用 AI 动作开始，或用下方输入框直接追问\n" % name
            )
        return "**▶ 会话：(未命名文件)**\n\n· 保存文件后，该会话会自动归到对应文件名下\n"

    def _update_session_label(self):
        """刷新"当前文件"提示"""
        try:
            sess = self._sessions.get(self._active_key, {})
            fp = sess.get("filepath", "") or ""
            n = len(self._sessions)
            if fp:
                import os as _os

                txt = "当前会话：%s" % _os.path.basename(fp)
            else:
                txt = "当前会话：(未命名文件)"
            if n > 1:
                txt += "　·　共 %d 个文件会话（各自独立）" % n
            self.session_label.setText(txt)
            self.session_label.setVisible(True)
        except Exception:
            pass

    def _session_count(self) -> int:
        return len(self._sessions)

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

        self.status_label.setText("✓ 来自缓存（未发起新请求）· 输入追问可继续对话")
        self.status_label.setStyleSheet("color: #4ec9b0; padding: 4px; font-size: 12px;")
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
            client = getattr(self, "_client", None)
            if client is not None and hasattr(client, "_history"):
                sys_p = getattr(self, "_system_prompt", "") or ""
                code = getattr(self, "_code_context", "") or ""
                if code.strip():
                    client._history.extend(
                        [
                            {"role": "user", "content": "（缓存命中，原始代码略）"},
                            {"role": "assistant", "content": self._result_text},
                        ]
                    )
                    client._trim_history()
        except Exception:
            pass

    def set_worker(self, worker: AIWorker):
        """绑定 Worker（首轮）"""
        self._worker = worker
        self._system_prompt = getattr(worker, "system", "") or ""
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
        code = getattr(self, "_code_context", "") or ""
        if not code.strip():
            return question
        return "最初分析的代码：\n```\n%s\n```\n\n%s" % (code, question)

    def _on_follow_up(self):
        """发送追问（在同一对话框内继续对话）"""
        if self._worker is not None and self._worker.isRunning():
            return  # 上一轮还没结束
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
        # 记录本片段属于哪个文件会话（生成中切文件时的守卫依据）
        self._chunk_session_key = self._active_key
        worker = AIWorker(
            self._client,
            self._build_follow_prompt(question),
            self._system_prompt,
            parent=self,
            use_history=use_history,
            max_tokens=getattr(self, "_max_tokens", None),
        )
        # 追问只累积新片段：清空当前累积，避免与上一轮拼接错乱
        self._result_text = self._result_text  # 保留历史显示
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
        tail = full_text or ""
        # 片段已逐个追加过；这里只做收尾状态
        if not tail and len(self._result_text) <= getattr(self, "_chunk_start", 0):
            self._result_text += "（无输出）"
        try:
            self.browser.setMarkdown(self._result_text)
        except Exception:
            self.browser.setPlainText(self._result_text)

        elapsed = 0.0
        if getattr(self, "_wait_start", None):
            elapsed = time.time() - self._wait_start
        self._stop_waiting()
        self.status_label.setText("✓ 完成 · 总耗时 %.1f 秒" % elapsed if elapsed else "✓ 完成")
        self.status_label.setStyleSheet("color: #7ec850; padding: 4px; font-size: 12px;")
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

        # 会话守卫：生成期间用户可能切到了别的文件。
        # 此时本片段属于**发起请求时的那个会话**，不能显示在当前窗口里
        # （否则 A 文件的回答会出现在 B 文件的会话中）。
        # 先累积到后台缓冲，等用户切回该会话时再一次性呈现。
        #
        # 注意：双方都必须经过 session_key() 归一化后再比较。
        # `_active_key` 是归一化过的（normcase 会把 Windows 路径小写化），
        # 若拿原始路径去比，`D:\a.py` 与 `d:\a.py` 会被误判成两个会话，
        # 结果是**同会话的片段被丢进后台缓冲** → 表现为"AI 没输出"。
        origin = self.session_key(getattr(self, "_chunk_session_key", ""))
        if origin and origin != self._active_key:
            self._background_bufs[origin] = self._background_bufs.get(origin, "") + text
            return

        start = getattr(self, "_chunk_start", None)
        if start is None:
            self._result_text += text
        else:
            self._result_text = self._result_text[:start] + (getattr(self, "_chunk_buf", "") + text)
            self._chunk_buf = getattr(self, "_chunk_buf", "") + text
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
        self.status_label.setStyleSheet("color: #7ec850; padding: 4px; font-size: 12px;")
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
        if getattr(self, "_wait_start", None):
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
        self.status_label.setStyleSheet("color: #f14c4c; padding: 4px; font-size: 12px;")
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
        pattern = re.compile(r"```[^\n]*\n(.*?)\n?```", re.DOTALL)
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
            self.status_label.setStyleSheet("color: #7ec850; padding: 4px; font-size: 12px;")
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
            proxy.sc.SendScintilla(proxy.sc.SCI_INSERTTEXT, pos, code.encode("utf-8"))
            self.status_label.setText("✓ 已插入到光标处")
            self.status_label.setStyleSheet("color: #7ec850; padding: 4px; font-size: 12px;")
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
