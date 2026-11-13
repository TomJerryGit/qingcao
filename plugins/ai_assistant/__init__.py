# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""AI 助手插件（v2.24 拆分：common/worker/dialog/config/panel）。"""

from .ai_common import *  # noqa: F401,F403,F405
from .ai_config_dialog import AIConfigDialog  # noqa: F401
from .ai_inline_mixin import InlineCompleterMixin  # noqa: E402
from .ai_ollama_mixin import OllamaPanelMixin  # noqa: E402
from .ai_panel import OllamaPanel, _OllamaStatusBridge  # noqa: F401
from .ai_result_dialog import AIResultDialog  # noqa: F401
from .ai_worker import AIWorker  # noqa: F401


class Plugin(OllamaPanelMixin, InlineCompleterMixin, PluginBase):
    """
    AI 助手插件。

    继承 PluginBase，实现 on_activate / on_deactivate。
    """

    NAME = PLUGIN_NAME
    VERSION = PLUGIN_VERSION
    DESCRIPTION = PLUGIN_DESCRIPTION
    AUTHOR = "TomJerry"
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
        # Ollama 状态刷新：后台线程 + 信号桥（避免 UI 线程做 HTTP）
        self._ollama_status_thread = None
        self._ollama_status_bridge = None
        self._plugin_closing = False

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def on_activate(self):
        """激活时调用"""
        self.api.log(f"AI 助手 v{self.VERSION} 已激活")

        # 检查依赖
        if not _AI_CLIENT_OK:
            self.api.show_status("AI 助手：core.ai_client 不可用", 5000, "error")
            return

        if not _requests_ok():
            self.api.show_status(
                "AI 助手：缺少 requests 库，请运行 pip install requests", 5000, "warning"
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
    def on_deactivate(self):
        """卸载时调用"""
        # 停止内联补全（清建议 + 作废在途请求）
        try:
            comp = getattr(self, "inline_completer", None)
            if comp is not None:
                comp.cancel()
                comp.set_enabled(False)
        except Exception:
            pass
        self.inline_completer = None

        # 停止 Ollama 状态定时器 + 等待后台线程结束
        #
        # 先置 `_plugin_closing`：后台线程据此跳过 emit，
        # 避免桥对象/窗口销毁后仍发信号（RuntimeError）。
        self._plugin_closing = True
        try:
            if getattr(self, "_ollama_timer", None) is not None:
                self._ollama_timer.stop()
                self._ollama_timer = None
        except Exception:
            pass
        try:
            th = getattr(self, "_ollama_status_thread", None)
            if th is not None and th.is_alive():
                th.join(2.0)
        except Exception:
            pass
        self._ollama_status_thread = None
        try:
            bridge = getattr(self, "_ollama_status_bridge", None)
            if bridge is not None:
                bridge.ready.disconnect()
        except Exception:
            pass
        self._ollama_status_bridge = None
        try:
            panel = getattr(self, "ollama_panel", None)
            if panel is not None:
                panel._stop_threads()
        except Exception:
            pass
        self.ollama_panel = None
        self._ollama_dock = None

        # 关闭会话窗口
        try:
            sess = getattr(self, "_session_window", None)
            if sess is not None:
                sess.close()
        except Exception:
            pass
        self._session_window = None

        # 关闭所有活动对话框
        #
        # ★ QThread 清理债（pytest 段错误根因）：
        #   对话框持有 AIWorker(QThread)（parent=dlg）。若对话框在
        #   worker 仍在运行时被销毁，QThread 析构会 qFatal →
        #   实测段错误。这里先 cancel + wait，超时再 terminate，
        #   确保线程停稳后才 close/销毁对话框。
        for dlg in list(self._active_dialogs):
            worker = getattr(dlg, "_worker", None)
            if worker is not None:
                try:
                    worker.cancel()
                except Exception:
                    pass
                try:
                    if not worker.wait(3000):
                        worker.terminate()
                        worker.wait(1000)
                except Exception:
                    pass
                try:
                    dlg._worker = None
                except Exception:
                    pass
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
            ("工具/AI 助手/💬 打开 AI 对话窗口", self._on_open_session_window, None),
            ("工具/AI 助手/💡 解释代码", self._on_explain, "Ctrl+Alt+E"),
            ("工具/AI 助手/🔧 重构代码", self._on_refactor, "Ctrl+Alt+Shift+R"),
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
                    None,
                )
                if action:
                    self._menus.append(action)
            except Exception:
                pass

        # 配置菜单
        try:
            config_action = self.api.add_menu("工具/AI 助手/⚙ 配置 AI...", self._on_configure, None)
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
            ("ai.quick_explain", "AI: 快速解释（结果复制到剪贴板）", self._on_quick_explain),
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
        self.api.show_status("AI 解释已复制到剪贴板（%d 字）" % len(text), 5000, "success")

    def _on_clear_cache(self):
        """清空 AI 结果缓存"""
        try:
            cache = get_result_cache()
            if cache is None:
                self.api.show_status("缓存不可用", 3000, "warning")
                return
            n = cache.stats().get("entries", 0)
            cache.clear()
            self.api.show_status("已清空 AI 结果缓存（%d 条）" % n, 4000, "success")
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
                "取消勾选「复用结果缓存」。",
            )
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
            self.api.show_message("AI 不可用", "core.ai_client 模块不可用。\n请确认项目结构完整。")
            return False

        if self._client is None:
            self._client = load_ai_client_from_settings()

        if self._client is None:
            reply = self.api.ask_yes_no("未配置 AI", "AI 客户端尚未配置。\n\n是否现在配置？")
            if reply:
                self._on_configure()
            return False

        return True

    def _run_ai_action(
        self,
        prompt_template: str,
        title: str,
        system_prompt: str,
        token_tier: str = "short",
        **format_kwargs,
    ):
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
            self.api.show_message("无代码", "请先打开文件或选中代码。")
            return

        # 格式化提示词
        try:
            prompt = prompt_template.format(code=code, lang=lang, src_lang=lang, **format_kwargs)
        except KeyError as e:
            self.api.log(f"提示词格式化失败（缺少 {e}）", "error")
            # 使用默认值
            prompt = prompt_template.format(
                code=code,
                lang=lang,
                src_lang=lang,
                dst_lang="Python",
                style="Google",
                framework="pytest",
            )

        # ---- 按文件切换会话 ----
        #
        # 每个文件一个独立上下文，避免"聊 A 文件的内容带进 B 文件的提问"。
        session_key = AIResultDialog.session_key(filepath)

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
            # 切到该文件的会话（会换出/换入显示文本、上下文与历史）
            dlg._client = self._client
            dlg.switch_to_file(filepath, title)
            # 在已有内容后追加分隔，标识本次动作
            if dlg._result_text.strip():
                dlg._result_text += "\n\n---\n\n**▶ %s**\n\n" % title
            else:
                dlg._result_text = "**▶ %s**\n\n" % title
            dlg._chunk_start = None
            dlg._chunk_buf = ""
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
                    self._client, prompt, system_prompt, dlg._max_tokens
                )
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

        # 记录本片段属于哪个会话（生成中切文件时的守卫依据）
        dlg._chunk_session_key = session_key

        # 创建 Worker（首轮：默认记住上下文，方便直接追问）
        worker = AIWorker(
            self._client,
            prompt,
            system_prompt,
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
            return QSettings("QingCao", "AI").value("session_window", True, type=bool)
        except Exception:
            return True

    def _get_or_create_session(self, main_window):
        """取回或创建持久会话窗口

        窗口中转的关键点：把 `exec_()`（模态阻塞）换成 `show()`，
        这样"切标签丢失上下文"的问题自然消失 —— 窗口一直开着，
        客户端历史也一直保留。
        """
        dlg = getattr(self, "_session_window", None)
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
                "· 点「＋ 新会话」清空上下文开始新话题\n"
            )
            try:
                dlg.browser.setMarkdown(dlg._result_text)
            except Exception:
                dlg.browser.setPlainText(dlg._result_text)
        self._present_session(dlg)

    def _cache_enabled(self) -> bool:
        """是否启用 AI 结果缓存（首选项，默认开启）"""
        try:
            return QSettings("QingCao", "AI").value("result_cache", True, type=bool)
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
            token_tier="short",
        )

    def _on_refactor(self):
        """重构代码"""
        self._run_ai_action(
            PROMPT_REFACTOR,
            "🔧 重构代码",
            "你是重构专家，保持功能不变，提升可读性和可维护性。",
            token_tier="medium",
        )

    def _on_fix(self):
        """修复 Bug"""
        self._run_ai_action(
            PROMPT_FIX,
            "🐛 修复 Bug",
            "你是调试专家，找出代码中的 bug 并修复。",
            token_tier="medium",
        )

    def _on_comment(self):
        """添加注释"""
        self._run_ai_action(
            PROMPT_COMMENT,
            "💬 添加注释",
            "你是文档专家，为代码添加清晰的中文注释。",
            token_tier="medium",
        )

    def _on_docstring(self):
        """生成 Docstring"""
        self._run_ai_action(
            PROMPT_DOCSTRING,
            "📖 生成 Docstring",
            "你是 Python 文档专家，使用 Google 风格 docstring。",
            style="Google",
            token_tier="short",
        )

    def _on_tests(self):
        """生成单元测试"""
        self._run_ai_action(
            PROMPT_TESTS,
            "🧪 生成单元测试",
            "你是测试工程师，生成完整的单元测试。",
            framework="pytest",
            token_tier="large",
        )

    def _on_optimize(self):
        """性能优化"""
        self._run_ai_action(
            PROMPT_OPTIMIZE,
            "⚡ 性能优化",
            "你是性能优化专家，优化代码性能但保持功能不变。",
            token_tier="medium",
        )

    def _on_review(self):
        """Code Review"""
        self._run_ai_action(
            PROMPT_REVIEW,
            "🔍 Code Review",
            "你是资深开发者，用中文分点指出代码中的问题。",
            token_tier="medium",
        )

    def _on_summary(self):
        """代码摘要"""
        self._run_ai_action(
            PROMPT_SUMMARY,
            "📝 代码摘要",
            "用中文简洁总结代码的核心功能。",
            token_tier="tiny",
        )

    def _on_convert(self, dst_lang: str):
        """转换语言"""
        self._run_ai_action(
            PROMPT_CONVERT,
            f"🔄 转换为 {dst_lang}",
            "你是多语言专家，保持代码功能等价地转换语言。",
            dst_lang=dst_lang,
            token_tier="large",
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
                        self.api.show_status("AI 配置已更新", 2000, "success")
                    else:
                        self.api.show_status("AI 配置保存失败，请检查", 3000, "warning")
                except Exception as e:
                    self.api.log(f"重新加载客户端失败: {e}", "error")
        except Exception as e:
            self.api.log(f"打开配置对话框失败: {e}", "error")
            import traceback

            traceback.print_exc()

    # ============================================================
    # 模块测试
    # ============================================================

    def refresh_theme(self, theme):
        """主题切换：适配面板基样式 + 子控件内联 QSS（v2.14）"""
        try:
            from PyQt5.QtWidgets import QWidget

            from infrastructure.theme_loader import adapt_qss_colors

            base = getattr(self, "_base_qss", "")
            if base:
                self.setStyleSheet(adapt_qss_colors(base, theme))
            for w in self.findChildren(QWidget):
                qss = w.styleSheet()
                if qss:
                    w.setStyleSheet(adapt_qss_colors(qss, theme))
        except Exception:
            pass


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
