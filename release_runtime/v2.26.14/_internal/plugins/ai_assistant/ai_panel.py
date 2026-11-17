# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""Ollama 面板与状态桥（v2.24 拆出）。"""

from .ai_common import *  # noqa: F401,F403,F405


class _OllamaStatusBridge(QObject):
    """把后台线程算出的 Ollama 状态摘要桥回主线程

    ★ 实测缺陷（cProfile，v2.2 性能优化）：

        `_refresh_ollama_status()` 原在 **UI 线程**同步调用
        `panel.status_summary()`，而它内部会做两次 HTTP：

            status_text()  → /api/version  超时 4s
            list_models()  → /api/tags     超时 15s

        实测启动后第一次刷新**阻塞 UI 4.1 秒**（本机 Ollama 在线也如此；
        Ollama 未启动时按超时会更久），期间窗口完全无响应。

        `PluginBase` 继承 `object` 而非 `QObject`，因此不能在插件类上
        定义 `pyqtSignal` —— 用这个独立桥梁对象（QObject）从 daemon
        线程安全地发回主线程。
    """

    ready = pyqtSignal(str)


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
        # 关闭中标志：后台线程据此跳过信号发送，避免"对象已销毁"的
        # RuntimeError（见 _safe_emit 的说明）
        self._closing = False
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

    # --------------------------------------------------------
    # 线程安全的信号发送
    # --------------------------------------------------------
    def _safe_emit(self, signal, *args) -> bool:
        """在后台线程完成后安全地发信号。

        为什么需要（真实缺陷）：
            刷新/拉取用的是 **daemon 线程**，它们不会阻止进程退出，
            也不保证在面板析构前结束。若面板已经被 Qt 销毁，而线程仍在
            `signal.emit(...)`，会抛：

                RuntimeError: wrapped C/C++ object of type OllamaPanel
                              has been deleted

            这会在关闭编辑器时打出 traceback（pytest 里表现为
            PytestUnhandledThreadExceptionWarning）。

        防护分两层：
            1. `_closing` 标志 —— 关闭时置位，线程据此直接跳过发送；
            2. `except RuntimeError` —— 兜住"标志检查与 emit 之间对象被
               销毁"的竞态窗口。
        """
        if getattr(self, "_closing", False):
            return False
        try:
            signal.emit(*args)
            return True
        except RuntimeError:
            # 底层 C++ 对象已销毁：属于正常退出路径，静默忽略
            return False
        except Exception:
            return False

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
                ok, status, models, running = (False, "探测异常: %s" % e, [], [])
            # 面板可能已被销毁 —— 必须走安全发送
            panel._safe_emit(panel._refresh_done, ok, status, models, running)

        th = threading.Thread(target=_worker, daemon=True, name="ollama-refresh")
        th.start()
        self._refresh_thread = th

    def _on_refresh_done(self, ok, status, models, running):
        """刷新线程完成后的 UI 更新（在主线程执行）"""
        self._busy = False
        self.refresh_btn.setEnabled(True)
        self._set_status(ok, status)
        self._populate(models, running)

    def _populate(self, models: List[Dict[str, Any]], running: List[Dict[str, Any]]):
        running_names = {r["name"] for r in running}
        self.model_list.clear()
        self._models = models
        for m in models:
            loaded = "  ● 已加载" if m["name"] in running_names else ""
            extra = "/".join(x for x in (m["parameter_size"], m["quantization"]) if x)
            item = QListWidgetItem(
                "%s   [%s]%s\n     %s%s"
                % (
                    m["name"],
                    m["size_text"],
                    loaded,
                    (extra + "   ") if extra else "",
                    m["modified_at"],
                )
            )
            item.setData(Qt.UserRole, m["name"])
            item.setToolTip(
                "名称: %s\n大小: %s\n参数: %s\n量化: %s\n家族: %s\n修改: %s"
                % (
                    m["name"],
                    m["size_text"],
                    m["parameter_size"] or "-",
                    m["quantization"] or "-",
                    m["family"] or "-",
                    m["modified_at"],
                )
            )
            self.model_list.addItem(item)

        n = len(models)
        nr = len(running)
        self.detail_label.setText(
            "共 %d 个模型%s。双击可复制名称。" % (n, ("，内存中已加载 %d 个" % nr) if nr else "")
        )
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
                self,
                "Ollama",
                "连接成功。\n\n服务状态：%s\nOpenAI 兼容端点：%s"
                % (status, self._client.openai_base_url()),
            )
        else:
            QMessageBox.warning(
                self,
                "Ollama 未连接",
                "无法连接 Ollama 服务。\n\n%s\n\n"
                "请确认：\n"
                "  1. 已安装 Ollama（https://ollama.com/download）\n"
                "  2. 服务已启动：在终端运行 `ollama serve`\n"
                "  3. 地址正确：%s" % (status, self._client.host),
            )

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
            self, "拉取 Ollama 模型", "模型名称（例如 qwen2.5:7b、deepseek-r1:8b、llama3.2）："
        )
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
                # 面板可能在拉取过程中被销毁 —— 走安全发送
                panel._safe_emit(panel._pull_progress, pct, str(ev.get("status") or ""))
                return not getattr(panel, "_pull_cancelled", False)

            ok2, msg = panel._client.pull_model(name, progress=on_event)
            panel._safe_emit(panel._pull_done, ok2, msg)

        th = threading.Thread(target=_worker, daemon=True, name="ollama-pull")
        th.start()
        self._pull_thread = th

    def _on_pull_progress(self, pct, status):
        """拉取进度（主线程）"""
        if pct:
            self.progress.setValue(pct)
        self.detail_label.setText("%s  %s" % (status, getattr(self, "_pull_name", "")))

    def _on_pull_done(self, ok2, msg):
        """拉取结束（主线程）"""
        name = getattr(self, "_pull_name", "")
        self._busy = False
        self.pull_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.detail_label.setText("%s：%s" % (name, msg))
        self.refresh()
        if ok2:
            QMessageBox.information(self, "Ollama", "模型 %s 拉取完成。" % name)
        else:
            QMessageBox.warning(self, "拉取失败", "%s\n%s" % (name, msg))

    def _on_delete(self):
        name = self._selected_name()
        if not name:
            return
        if (
            QMessageBox.question(
                self,
                "删除模型",
                "确定删除本地模型 %s 吗？\n\n此操作会释放其占用的磁盘空间，"
                "且不可撤销（需要时可用「拉取模型」重新下载）。" % name,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
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
            self,
            "已应用",
            "AI 配置已更新：\n\n  提供商：Ollama (本地)\n  模型：%s\n"
            "  端点：%s\n\n下次使用 AI 功能即生效。" % (name, self._client.openai_base_url()),
        )

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
        """等待后台线程结束并阻止其继续发信号。

        面板用的是 daemon `threading.Thread`，因此**不会**出现
        `QThread` 那种"运行中被析构 → qFatal"的问题；但 daemon 线程
        **不会阻塞进程退出**，也不保证在面板析构前结束 ——
        若它在对象销毁后才 `emit`，会抛
        `RuntimeError: wrapped C/C++ object ... has been deleted`。

        因此这里**先置 `_closing` 标志**（线程据此跳过发送），再 join。
        """
        self._closing = True
        for attr in ("_refresh_thread", "_pull_thread"):
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
