# -*- coding: utf-8 -*-
"""
青草编辑器 - 能力接线 Mixin（P0-4/5/6/10 + P1 入口重排）
========================================================

本模块集中"把已实现但零引用的能力接到 UI 上"的代码，独立于
`ui/main_window.py`，避免与其它改动互相冲突。

接线清单（每项都注明"此前为何用不到"）：

| 能力 | 源 | 接线方式 |
|---|---|---|
| 本地格式化 | `core/formatter.py`（Black/autopep8/clang-format） | 工具菜单「格式化文档」 |
| LSP 状态/安装向导 | `ui/lsp_panel.py`（548 行） | 面板：LSP |
| 撤销历史 | `ui/undo_history_panel.py`（229 行） | 面板：撤销历史 |
| 崩溃统计 | `core/crash_stats.py`（240 行） | 帮助菜单「崩溃统计」 |
| 导出 PDF/HTML | `core/exporter.py`（157 行） | 文件菜单「导出」 |

**设计约束**：所有方法都做了防御性 `try/except` 与 `hasattr` 检查 ——
因为面板/引擎可能在打包产物中缺失（`build.py` 的 hiddenimports 会静默
跳过不存在模块），缺一个能力不该让整个菜单构建失败。
"""

import logging
import os
import weakref

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QApplication


logger = logging.getLogger(__name__)

# 应用级按键过滤器（模块级单例，弱引用持有窗口）
#
# ★ 为什么不能把 MainWindow 直接 installEventFilter 到 QApplication
#   （实测崩溃，务必看）：
#
#       `app.installEventFilter(self)` 之后，QApplication 持有 MainWindow 的
#       C++ 指针。在主窗口**被销毁**（关窗/测试 teardown / GC）后，
#       QApplication 仍会在下一次事件派发时调用该过滤器的 `eventFilter`，
#       而此时 Python 对象已析构 → **访问违例（0xC0000005）**。
#
#       实测复现：`pytest tests/test_p1_features.py` 单跑必崩
#       （6 个测试全通过后在 teardown 段错误）；把本模块的初始化临时注释掉
#       则完整通过 —— 因果已确认。
#
#   改为：独立的 `_KeySequenceAppFilter`（弱引用窗口）+ 窗口侧只做
#   `_handle_keyseq_event`，窗口没了过滤器安全返回 False。
_KEYSEQ_APP_FILTER = None


class _KeySequenceAppFilter(QObject):
    """应用级按键过滤器：把按键转交当前窗口的多键序列管理器

    用 weakref 持有窗口 —— 窗口销毁后 `owner_ref()` 返回 None，
    过滤器直接放行，绝不会访问已析构对象。
    """

    def __init__(self, owner):
        super().__init__()
        self._owner_ref = weakref.ref(owner)

    def set_owner(self, owner):
        """切换归属窗口（多窗口/测试场景复用同一个过滤器）"""
        self._owner_ref = weakref.ref(owner) if owner is not None else \
            (lambda: None)

    def eventFilter(self, obj, event):
        """转交给归属窗口处理；任何异常都放行

        ★ 性能（profile 实测）：这是**应用级**事件过滤器，鼠标移动、
        重绘、布局等**所有**事件都会先到这里。原实现先做 weakref +
        两次 getattr + 方法调用，再到 `_handle_keyseq_event` 里才判断
        `event.type() != KeyPress` —— 主题应用期间一次 polish 就产生
        13,139 个事件，白付 **0.147 秒**；平时每个事件也固定多花
        ~11µs（影响拖拽/滚动跟手感）。

        修复：**先判断事件类型**，非按键事件一次 C 调用即放行。
        """
        try:
            if event.type() != QEvent.KeyPress:
                return False
            owner = self._owner_ref() if self._owner_ref else None
            if owner is None:
                return False
            if getattr(owner, '_closing', False):
                return False
            handler = getattr(owner, '_handle_keyseq_event', None)
            if handler is None:
                return False
            return bool(handler(obj, event))
        except (RuntimeError, ReferenceError):
            # 窗口的 C++ 对象已销毁 → 安静放行
            return False
        except Exception:
            return False


class CapabilityWiringMixin:
    """能力接线 Mixin —— 由 MainWindow 继承

    依赖属性：``self.tabs``、``self.status_bar``、``self.panel_menu``、
    ``self.tools_menu``、``self.file_menu``、``self.help_menu``、
    ``self._ensure_panel``
    """

    # ========================================================
    # P0-4：本地格式化（core/formatter.py 此前零引用）
    # ========================================================
    def _setup_format_menu(self):
        """在工具菜单挂「格式化文档」子菜单"""
        try:
            from core.formatter import get_formatter_registry

            available = [f.name for f in get_formatter_registry()
                         .list_available()]
        except Exception:
            available = []

        try:
            self.format_menu = self.tools_menu.addMenu("🪄 格式化文档")
        except Exception as e:
            if logger:
                logger.debug("创建格式化菜单失败: %s", e)
            return

        # 始终提供"自动选择"，即使当前机器一个格式化器都没装 ——
        # 菜单项存在但点击时给出明确安装提示，比菜单项凭空消失好。
        self._add_action(self.format_menu, "自动选择可用格式化器",
                         "Ctrl+Alt+Shift+F", self._format_document)
        if available:
            self.format_menu.addSeparator()
            for name in available:
                label = {
                    "black": "Black（Python）",
                    "autopep8": "autopep8（Python）",
                    "clang-format": "clang-format（C/C++/Java/JS）",
                }.get(name, name)
                self._add_action(
                    self.format_menu, label, None,
                    lambda _checked=False, n=name: self._format_document(n),
                )
        else:
            self.format_menu.addSeparator()
            act = self._add_action(
                self.format_menu, "（未检测到本地格式化器）", None, None
            )
            try:
                if act is not None:
                    act.setEnabled(False)
                    act.setToolTip(
                        "安装方式：pip install black 或 pip install autopep8"
                    )
            except Exception:
                pass

    # ========================================================
    # 快捷键序列（core/key_sequence_manager.py）
    # ========================================================
    # 注册的序列（VSCode 风格；**前缀键 Ctrl+K 全仓无单键绑定**，已 grep 确认）
    KEY_SEQUENCES = (
        # (按键序列, 处理器名, 说明)
        (("Ctrl+K", "Ctrl+S"), "_save_all", "保存全部"),
        (("Ctrl+K", "Ctrl+W"), "_close_all_tabs", "关闭所有标签"),
        (("Ctrl+K", "Ctrl+C"), "_toggle_comment", "注释切换"),
        (("Ctrl+K", "Ctrl+F"), "_format_document", "格式化文档"),
        (("Ctrl+K", "Ctrl+T"), "_show_snapshot_dialog", "会话快照"),
        (("Ctrl+K", "Ctrl+D"), "_show_file_diff", "对比文件"),
    )

    def _setup_key_sequences(self):
        """接线 `core/key_sequence_manager.py`（VSCode 风格多键序列）

        ## 此前状态
        `core/key_sequence_manager.py`（190 行）实现了完整的
        "前缀键等待 + 超时取消 + 序列触发"，但**零引用** ——
        用户按 `Ctrl+K` 没有任何反应。

        ## 为什么必须谨慎（前缀键会"吃掉"按键）
        按下前缀键时序列管理器会返回 True（消费该键），随后才等待第二键。
        如果它错误地消费了**普通编辑按键**，用户会觉得"键盘坏了"。
        因此本实现有三道闸：

          1. **只处理带 Ctrl/Alt 的键**（`_key_string_for_event` 里判断）——
             纯字母/数字/退格不可能被吞；
          2. **只在焦点位于编辑器时处理** —— 对话框/输入框里的按键不受影响；
          3. **有模态窗口时不处理** —— 避免抢走确认框的按键。

        另有 `key_sequence_conflicts()` 供测试与启动自检，
        确保**前缀键本身没有单键绑定**（否则 Ctrl+K 会被两条路径同时响应）。
        """
        try:
            from core.key_sequence_manager import KeySequenceManager

            mgr = KeySequenceManager(self)
            self.key_sequence_manager = mgr

            # 状态栏提示（"Ctrl+K ... 等待第二个键"）
            try:
                mgr.status_changed.connect(self._on_key_sequence_status)
            except Exception:
                pass

            registered = []
            for keys, handler_name, desc in self.KEY_SEQUENCES:
                handler = getattr(self, handler_name, None)
                if not callable(handler):
                    # 处理器缺失（该能力未接线）→ 跳过，不让整个初始化失败
                    print(f"[KeySeq] 跳过 {keys}：缺少处理器 {handler_name}")
                    continue
                mgr.register(list(keys), handler, description=desc)
                registered.append((keys, handler_name, desc))

            self._key_sequences_registered = registered

            # 装事件过滤器（应用级，但只处理编辑器焦点）
            #
            # ★ 必须用**独立过滤器对象** + weakref，不能把 self 装上去 ——
            #   原因见模块顶部 `_KEYSEQ_APP_FILTER` 的说明（实测访问违例）。
            global _KEYSEQ_APP_FILTER
            app = QApplication.instance()
            if app is not None:
                if _KEYSEQ_APP_FILTER is None:
                    _KEYSEQ_APP_FILTER = _KeySequenceAppFilter(self)
                    app.installEventFilter(_KEYSEQ_APP_FILTER)
                else:
                    _KEYSEQ_APP_FILTER.set_owner(self)
                self._keyseq_app_filter = _KEYSEQ_APP_FILTER

            print("[KeySeq] 已启用 %d 条多键序列" % len(registered))
        except Exception as e:
            print(f"[MainWindow] 启用快捷键序列失败: {e}")
            self.key_sequence_manager = None

    def _teardown_key_sequences(self):
        """关窗时卸载按键过滤器（避免 QApplication 持有失效窗口）"""
        try:
            global _KEYSEQ_APP_FILTER
            filt = getattr(self, '_keyseq_app_filter', None)
            if filt is not None and _KEYSEQ_APP_FILTER is filt:
                try:
                    app = QApplication.instance()
                    if app is not None:
                        app.removeEventFilter(filt)
                except Exception:
                    pass
                _KEYSEQ_APP_FILTER = None
            self._keyseq_app_filter = None
            mgr = getattr(self, 'key_sequence_manager', None)
            if mgr is not None:
                try:
                    mgr.cancel()
                except Exception:
                    pass
        except Exception:
            pass

    def _on_key_sequence_status(self, text: str):
        """把序列等待状态显示到状态栏"""
        try:
            if text:
                self.status_bar.showMessage(text, 3000)
        except Exception:
            pass

    def key_sequence_conflicts(self):
        """检查多键序列是否与现有单键快捷键冲突

        返回:
            [(sequence, conflict_reason), ...]；空列表表示无冲突

        规则：
          * **前缀键**（如 `Ctrl+K`）自身不能有单键绑定 ——
            否则按下它时既触发单键动作、又被序列管理器消费，行为不确定；
          * 完整序列（多键）不会与 QAction 单键冲突（Qt 不支持多键序列）。
        """
        problems = []
        try:
            from PyQt5.QtWidgets import QAction
            mgr = getattr(self, 'act_mgr', None)
            actions = getattr(mgr, 'actions', {}) or {}

            # 收集全窗口所有带快捷键的动作（含未注册到 ActionManager 的）
            shortcut_owners = {}
            for act in self.findChildren(QAction):
                try:
                    if act.shortcut().isEmpty():
                        continue
                    key = act.shortcut().toString()
                except Exception:
                    continue
                shortcut_owners.setdefault(key, []).append(act.text())

            for keys, handler_name, desc in self.KEY_SEQUENCES:
                prefix = keys[0]
                if prefix in shortcut_owners:
                    problems.append((
                        " ".join(keys),
                        "前缀键 %s 已被动作占用: %s"
                        % (prefix, shortcut_owners[prefix][:3])
                    ))
                # 处理器必须存在
                if not callable(getattr(self, handler_name, None)):
                    problems.append((
                        " ".join(keys),
                        "缺少处理器 %s" % handler_name
                    ))
            _ = actions
        except Exception as e:
            problems.append(("<检查失败>", str(e)))
        return problems

    def _key_string_for_event(self, obj, event) -> str:
        """把 QKeyEvent 转成序列管理器的键名；不值得处理的键返回空串

        三重过滤（见 `_setup_key_sequences` 的说明）：
          1. 必须有 Ctrl 或 Alt（否则普通输入会被吞）；
          2. 事件目标必须是编辑器（QsciScintilla）；
          3. 不能有模态窗口。

        ★ 缺陷修正（实测发现）：第一版用 `app.activeWindow().focusWidget()`
        判断焦点，这在两种情况下会**完全失效**：

          * headless/offscreen（没有"活动窗口"概念）→ `activeWindow()` 为 None；
          * 窗口刚显示、或焦点在浮动面板时 → 取不到编辑器。

        结果就是"多键序列根本不触发"。正确做法是用事件过滤器收到的
        `obj` —— 那才是**真正接收该按键的控件**，再退回 `focusWidget()`。
        """
        try:
            from PyQt5.QtCore import Qt

            mods = event.modifiers()
            if not (mods & Qt.ControlModifier or mods & Qt.AltModifier):
                return ""

            app = QApplication.instance()
            if app is not None and app.activeModalWidget() is not None:
                return ""

            from PyQt5.Qsci import QsciScintilla

            target = obj
            if not isinstance(target, QsciScintilla):
                # 事件目标不是编辑器时，再看当前焦点
                focus = app.focusWidget() if app is not None else None
                if not isinstance(focus, QsciScintilla):
                    return ""
                target = focus
            _ = target

            from core.key_sequence_manager import key_event_to_string
            return key_event_to_string(event)
        except Exception:
            return ""

    def _handle_keyseq_event(self, obj, event):
        """处理按键事件：识别多键序列（其余事件一律放行）

        注意：本方法**不叫** `eventFilter`、也**不**由 MainWindow 直接
        安装到 QApplication（那样会因窗口销毁后 QApplication 仍持有指针
        而访问违例）。实际安装的是 `_KeySequenceAppFilter`，它用 weakref
        找到本窗口再调到这里。
        """
        try:
            from PyQt5.QtCore import QEvent

            if event.type() != QEvent.KeyPress:
                return False

            mgr = getattr(self, 'key_sequence_manager', None)
            if mgr is None:
                return False

            key = self._key_string_for_event(obj, event)
            if not key:
                return False

            if mgr.handle_key(key):
                # 命中前缀或完整序列 → 消费该按键
                event.accept()
                return True
            return False
        except (RuntimeError, ReferenceError):
            return False
        except Exception:
            return False

    # ========================================================
    # 插件扩展点宿主侧实现（v2.3）
    # ========================================================
    def register_plugin_completion_provider(self, provider, language_ids=None,
                                            plugin_name=""):
        """登记插件补全提供者（由 PluginAPI.register_completion_provider 调用）"""
        try:
            providers = getattr(self, '_plugin_completion_providers', None)
            if providers is None:
                providers = []
                self._plugin_completion_providers = providers
            providers.append({
                'provider': provider,
                'languages': [str(x).lower() for x in (language_ids or [])],
                'plugin': plugin_name or 'unknown',
            })
            return True
        except Exception as e:
            print(f"[MainWindow] 注册插件补全提供者失败: {e}")
            return False

    def unregister_plugin_completion_provider(self, plugin_name: str):
        """注销某插件的全部补全提供者（插件卸载时）"""
        providers = getattr(self, '_plugin_completion_providers', None)
        if not providers:
            return
        try:
            self._plugin_completion_providers = [
                p for p in providers if p.get('plugin') != plugin_name
            ]
        except Exception:
            pass

    def collect_plugin_completions(self, prefix: str, language: str = "",
                                   filepath: str = "", limit: int = 50):
        """收集所有插件补全候选（供编辑器调用）

        语言匹配规则：
            * 提供者 language_ids 为空 → 对所有语言生效；
            * 否则语言键（如 "python"）或扩展名（如 ".py"）命中即可。
        """
        out = []
        providers = getattr(self, '_plugin_completion_providers', None) or []
        if not providers or not prefix:
            return out
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()
        for entry in providers:
            try:
                langs = entry.get('languages') or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get('provider')
                if not callable(fn):
                    continue
                items = fn(prefix, language=lang, filepath=filepath) or []
                for item in items:
                    if isinstance(item, dict):
                        word = (item.get('insert_text')
                                or item.get('label') or '')
                    else:
                        word = str(item)
                    word = word.strip()
                    if word and word not in out:
                        out.append(word)
                        if len(out) >= limit:
                            return out
            except Exception as e:
                print(f"[MainWindow] 插件补全提供者异常"
                      f"({entry.get('plugin')}): {e}")
        return out

    # ========================================================
    # 插件扩展点 v2.4：hover / 右键菜单 / 代码操作 / 状态栏 / 设置
    # ========================================================
    def _ensure_plugin_extension_registries(self):
        for attr, factory in (
                ('_plugin_hover_providers', list),
                ('_plugin_context_actions', list),
                ('_plugin_code_action_providers', list),
                ('_plugin_status_items', list),
                ('_plugin_settings_schemas', dict),
                ('_plugin_symbol_providers', list)):
            if not hasattr(self, attr):
                setattr(self, attr, factory())

    def register_plugin_hover_provider(self, provider, language_ids=None,
                                       plugin_name=""):
        """登记插件 hover 提供者"""
        self._ensure_plugin_extension_registries()
        self._plugin_hover_providers.append({
            'provider': provider,
            'languages': [str(x).lower() for x in (language_ids or [])],
            'plugin': plugin_name or 'unknown',
        })
        return True

    def collect_plugin_hover(self, filepath: str, line: int, col: int,
                             language: str = "") -> str:
        """收集插件 hover 文本（按语言过滤，多个提供者用空行分隔）"""
        self._ensure_plugin_extension_registries()
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()
        parts = []
        for entry in self._plugin_hover_providers:
            try:
                langs = entry.get('languages') or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get('provider')
                if not callable(fn):
                    continue
                text = fn(line, col, filepath=filepath, language=lang)
                if text:
                    parts.append(str(text).strip())
            except Exception as e:
                print(f"[MainWindow] hover 提供者失败"
                      f"({entry.get('plugin')}): {e}")
        return "\n\n".join(p for p in parts if p)[:4000]

    def add_plugin_editor_context_action(self, label: str, callback,
                                         plugin_name=""):
        """登记插件编辑器右键菜单项"""
        self._ensure_plugin_extension_registries()
        if not callable(callback):
            return False
        self._plugin_context_actions.append({
            'label': label,
            'callback': callback,
            'plugin': plugin_name or 'unknown',
        })
        return True

    def collect_editor_context_actions(self, editor=None):
        """取当前插件的右键菜单项（返回副本，安全迭代）"""
        self._ensure_plugin_extension_registries()
        return list(self._plugin_context_actions)

    def register_plugin_code_action_provider(self, provider,
                                             language_ids=None,
                                             plugin_name=""):
        """登记插件代码操作提供者"""
        self._ensure_plugin_extension_registries()
        self._plugin_code_action_providers.append({
            'provider': provider,
            'languages': [str(x).lower() for x in (language_ids or [])],
            'plugin': plugin_name or 'unknown',
        })
        return True

    def collect_code_actions(self, filepath: str, line: int, col: int,
                             language: str = ""):
        """收集代码操作（统一结构：title/callback/kind）"""
        self._ensure_plugin_extension_registries()
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()
        out = []
        for entry in self._plugin_code_action_providers:
            try:
                langs = entry.get('languages') or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get('provider')
                if not callable(fn):
                    continue
                items = fn(line, col, filepath=filepath, language=lang) or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = item.get('title') or item.get('label')
                    callback = item.get('callback') or item.get('run')
                    if title and callable(callback):
                        out.append({'title': str(title),
                                    'kind': str(item.get('kind', '')),
                                    'callback': callback,
                                    'plugin': entry.get('plugin')})
            except Exception as e:
                print(f"[MainWindow] 代码操作提供者失败"
                      f"({entry.get('plugin')}): {e}")
        return out

    def show_plugin_code_actions(self, editor) -> bool:
        """弹出代码操作菜单并执行选中项（右键菜单入口）"""
        try:
            from PyQt5.QtWidgets import QMenu
            line, col = editor.getCursorPosition()
            actions = self.collect_code_actions(
                getattr(getattr(editor, 'document', None), 'filepath', '') or '',
                line, col,
                language=getattr(editor, '_completion_language', lambda: "")())
            if not actions:
                return False
            menu = QMenu(self)
            for action in actions:
                label = action['title']
                if action['kind']:
                    label = "%s（%s）" % (label, action['kind'])
                act = menu.addAction(label)
                act.triggered.connect(
                    lambda _checked=False, cb=action['callback']: cb())
            menu.exec_(editor.mapToGlobal(editor.cursorRect().bottomRight()))
            return True
        except Exception as e:
            print(f"[MainWindow] 代码操作菜单失败: {e}")
            return False

    def register_plugin_symbol_provider(self, provider, language_ids=None,
                                        plugin_name=""):
        """登记插件符号提供者（大纲面板合并）"""
        self._ensure_plugin_extension_registries()
        self._plugin_symbol_providers.append({
            'provider': provider,
            'languages': [str(x).lower() for x in (language_ids or [])],
            'plugin': plugin_name or 'unknown',
        })
        return True

    def collect_plugin_symbols(self, text: str, filepath: str = "",
                               language: str = "", limit: int = 5000):
        """收集插件符号（规范化为 dict 列表，含 children）"""
        self._ensure_plugin_extension_registries()
        lang = (language or "").lower()
        ext = os.path.splitext(filepath or "")[1].lower()

        def _norm(items, depth=0):
            out = []
            if depth > 8 or not items:
                return out
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get('name') or item.get('label')
                if not name:
                    continue
                node = {
                    'name': str(name),
                    'type': str(item.get('type') or item.get('kind')
                                or 'unknown'),
                    'line': int(item.get('line') or 0),
                    'col': int(item.get('col') or 0),
                    'end_line': int(item.get('end_line') or 0),
                    'indent': int(item.get('indent') or depth),
                    'signature': str(item.get('signature') or ''),
                }
                children = _norm(item.get('children') or [], depth + 1)
                if children:
                    node['children'] = children
                out.append(node)
                if len(out) >= limit:
                    break
            return out

        collected = []
        for entry in getattr(self, '_plugin_symbol_providers', []):
            try:
                langs = entry.get('languages') or []
                if langs and lang not in langs and ext not in langs:
                    continue
                fn = entry.get('provider')
                if not callable(fn):
                    continue
                items = fn(text, filepath=filepath, language=lang) or []
                collected.extend(_norm(items))
                if len(collected) >= limit:
                    break
            except Exception as e:
                print(f"[MainWindow] symbol provider 失败"
                      f"({entry.get('plugin')}): {e}")
        # B-3b：合并沙箱插件的符号（只读代理；失败/降级自动跳过）
        try:
            getter = getattr(self, '_get_sandboxed_plugins', None)
            if callable(getter):
                for sp in getter().values():
                    try:
                        items = sp.symbols(
                            text, filepath or "", lang) or []
                        collected.extend(_norm(items))
                    except Exception:
                        continue
        except Exception:
            pass
        return collected[:limit]

    def register_plugin_settings_schema(self, plugin_name: str, schema):
        """登记插件设置 schema（供设置面板/文档展示；对话框由插件 API 生成）"""
        self._ensure_plugin_extension_registries()
        self._plugin_settings_schemas[plugin_name or 'unknown'] = list(schema)
        return True

    def unregister_plugin_extras(self, plugin_name: str):
        """注销某插件的全部 v2.4 扩展点（插件卸载时）"""
        self._ensure_plugin_extension_registries()
        for attr in ('_plugin_hover_providers',
                     '_plugin_code_action_providers',
                     '_plugin_context_actions',
                     '_plugin_symbol_providers'):
            current = getattr(self, attr, [])
            setattr(self, attr, [
                e for e in current if e.get('plugin') != plugin_name])
        schemas = getattr(self, '_plugin_settings_schemas', {})
        schemas.pop(plugin_name, None)

    def add_plugin_status_item(self, widget):
        """把控件加到状态栏右侧（返回控件，由调用方负责移除）"""
        try:
            if self.statusBar() is None:
                return None
            self.statusBar().addPermanentWidget(widget)
            return widget
        except Exception as e:
            print(f"[MainWindow] 添加状态栏项失败: {e}")
            return None

    # ========================================================
    # 面板：LSP 状态 / 撤销历史（对应孤立 UI 文件）
    # ========================================================
    def _build_panel_lsp(self):
        """构造 LSP 面板（`ui/lsp_panel.py` 此前零实例化）

        该模块还包含 `LspInstallerDialog`（语言服务器安装向导）——
        用户启用 LSP 失败时，这里能引导安装，而不是只给一句
        "请 pip install ..." 的状态栏文字。

        ⚠️ 属性名必须是 **`self.lsp`**：`MainWindow._ensure_panel(name)`
        会做 `getattr(self, name)`，而 name 来自 `_LAZY_PANELS`（'lsp'）。
        用别的名字（如 `lsp_panel`）会让 `_ensure_panel('lsp')` 返回 False。
        """
        try:
            from ui.lsp_panel import LspPanel
            # 注意签名是 `(main_window=None, parent=None)` —— 主窗口要按
            # **关键字**传，否则会被当成 main_window 而不是 parent。
            self.lsp = LspPanel(main_window=self, parent=self)
            try:
                self.lsp.setObjectName("LspPanel")
            except Exception:
                pass
            self.addDockWidget(self._right_dock_area(), self.lsp)
            self.lsp.hide()
            try:
                if hasattr(self.lsp, 'set_installer'):
                    from core.lsp_installer import LspInstaller
                    self.lsp.set_installer(LspInstaller())
            except Exception:
                pass
        except Exception as e:
            print(f"[MainWindow] LspPanel 加载失败: {e}")
            self.lsp = None

    def _build_panel_undo_history(self):
        """构造撤销历史面板（`ui/undo_history_panel.py` 此前零实例化）

        ⚠️ 属性名必须是 **`self.undo_history`**（理由同上）。
        """
        try:
            from ui.undo_history_panel import UndoHistoryPanel
            self.undo_history = UndoHistoryPanel(main_window=self, parent=self)
            try:
                self.undo_history.setObjectName("UndoHistoryPanel")
            except Exception:
                pass
            self.addDockWidget(self._bottom_dock_area(), self.undo_history)
            self.undo_history.hide()
            self._connect_undo_history()
        except Exception as e:
            print(f"[MainWindow] UndoHistoryPanel 加载失败: {e}")
            self.undo_history = None

    def _connect_undo_history(self):
        """把当前标签的撤销栈变化实时喂给撤销历史面板"""
        try:
            proxy = self.tabs.current_proxy()
            panel = getattr(self, 'undo_history', None)
            if proxy is None or panel is None:
                return
            if getattr(proxy, '_undo_history_connected', False):
                return
            um = getattr(proxy, 'undo_manager', None)
            if um is None:
                return

            def _refresh(*_a):
                try:
                    if hasattr(panel, 'refresh'):
                        panel.refresh()
                except Exception:
                    pass

            try:
                um.stack_changed.connect(_refresh)
                proxy._undo_history_connected = True
            except Exception:
                pass
            for setter in ('set_manager', 'set_undo_manager'):
                if hasattr(panel, setter):
                    try:
                        getattr(panel, setter)(um)
                    except Exception:
                        pass
                    break
        except Exception as e:
            if logger:
                logger.debug("连接撤销历史面板失败: %s", e)

    # --------------------------------------------------------
    # 面板菜单接线（由 Lead 在 main_window 里调用一次）
    # --------------------------------------------------------
    def _append_panel_menu_items(self, panels: list) -> list:
        """向面板子菜单追加"LSP / 撤销历史"两项

        参数:
            panels: `_build_panel_menu` 里已有的 (名称, action, slot) 列表

        返回:
            追加后的列表（便于链式调用）
        """
        panels.append(("LSP 状态", "panel.lsp",
                       self._toggle_lsp_panel))
        panels.append(("撤销历史", "panel.undo_history",
                       self._toggle_undo_history_panel))
        return panels

    def _toggle_lsp_panel(self, checked):
        """切换 LSP 面板"""
        if self._ensure_panel('lsp') and getattr(self, 'lsp', None):
            self.lsp.setVisible(checked)

    def _toggle_undo_history_panel(self, checked):
        """切换撤销历史面板"""
        if self._ensure_panel('undo_history') and \
                getattr(self, 'undo_history', None):
            self.undo_history.setVisible(checked)
            if checked:
                self._connect_undo_history()

    def _right_dock_area(self):
        """右侧停靠区（避免各面板各自 import Qt 常量）"""
        try:
            from PyQt5.QtCore import Qt
            return Qt.RightDockWidgetArea
        except Exception:
            return 2

    def _bottom_dock_area(self):
        """底部停靠区"""
        try:
            from PyQt5.QtCore import Qt
            return Qt.BottomDockWidgetArea
        except Exception:
            return 8

    # ========================================================
    # P0-10：导出（core/exporter.py 此前零引用）
    # ========================================================
    def _setup_export_menu(self):
        """在文件菜单挂「导出」子菜单

        兑现 `requirements.txt` 里"文件 → 导出 → PDF"的承诺
        （此前文档写了、菜单里却没有）。
        """
        try:
            self.export_menu = self.file_menu.addMenu("📤 导出")
        except Exception as e:
            if logger:
                logger.debug("创建导出菜单失败: %s", e)
            return

        self._add_action(self.export_menu, "导出为 PDF…", None,
                         self._export_current_as_pdf)
        self._add_action(self.export_menu, "导出为 HTML…", None,
                         self._export_current_as_html)
        self._add_action(self.export_menu, "导出为 Markdown…", None,
                         self._export_current_as_markdown)

        # reportlab 是可选依赖：缺失时禁用 PDF 项并说明原因
        try:
            import reportlab  # noqa: F401
            pdf_ok = True
        except Exception:
            pdf_ok = False
        if not pdf_ok:
            try:
                acts = self.export_menu.actions()
                if acts:
                    acts[0].setEnabled(False)
                    acts[0].setToolTip(
                        "需要 reportlab：pip install reportlab"
                    )
            except Exception:
                pass

    def _export_current(self, fmt: str):
        """导出当前文件（fmt: 'pdf' / 'html' / 'md'）

        对接 `core/exporter.py` 的**模块级函数**（不是类）：
        `to_html(text, title, language)` / `to_pdf(text, output_path, title)`
        / `to_markdown(...)`。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            from PyQt5.QtWidgets import QFileDialog

            ext = {"pdf": "pdf", "html": "html", "md": "md"}[fmt]
            default = f"导出.{ext}"
            filters = {
                "pdf": "PDF (*.pdf)",
                "html": "HTML (*.html)",
                "md": "Markdown (*.md)",
            }[fmt]
            path, _ = QFileDialog.getSaveFileName(
                self, "导出",
                os.path.join(os.path.dirname(
                    proxy.document.filepath or ""), default),
                filters,
            )
            if not path:
                return

            import core.exporter as exporter
            text = proxy.get_text()
            title = os.path.basename(proxy.document.filepath or "未命名")
            language = "text"
            try:
                language = getattr(proxy.document.meta, "language", "text") \
                    or "text"
            except Exception:
                pass

            if fmt == "pdf":
                ok = exporter.to_pdf(text, path, title=title)
                if isinstance(ok, tuple):        # 可能返回 (ok, msg)
                    ok = ok[0]
            elif fmt == "html":
                content = exporter.to_html(text, title=title,
                                           language=language)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                ok = True
            else:
                content = exporter.to_markdown(text, title=title,
                                               language=language)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                ok = True

            self.status_bar.showMessage(
                f"已导出: {os.path.basename(path)}" if ok
                else "导出失败（详见日志）", 5000
            )
        except ImportError as e:
            self.status_bar.showMessage(
                f"导出失败：缺少依赖（{e}）。PDF 需要 reportlab："
                f"pip install reportlab", 9000
            )
        except Exception as e:
            print(f"[MainWindow] 导出失败: {e}")
            try:
                self.status_bar.showMessage(f"导出失败: {e}", 8000)
            except Exception:
                pass

    def _export_current_as_pdf(self):
        self._export_current("pdf")

    def _export_current_as_html(self):
        self._export_current("html")

    def _export_current_as_markdown(self):
        self._export_current("md")

    # ========================================================
    # P0-6：崩溃统计（core/crash_stats.py 此前零引用）
    # ========================================================
    def _show_crash_stats(self):
        """显示崩溃统计（`CrashStats` 有能力、此前无入口）

        `crash_stats.py` 提供 `get_total_count` / `get_top_exceptions` /
        `get_recent_count` / `should_notify` / `cleanup_old` —— 这些信息
        对"这个版本是不是经常崩"的判断很有用，但此前完全看不到。
        """
        try:
            from PyQt5.QtWidgets import QMessageBox

            from core.crash_stats import CrashStats
            stats = CrashStats()
            total = stats.get_total_count()
            if not total:
                QMessageBox.information(
                    self, "崩溃统计", "没有记录到崩溃。"
                )
                return
            top = stats.get_top_exceptions(5)
            recent = stats.get_recent_count(7)
            lines = [
                f"累计崩溃次数：{total}",
                f"最近 7 天：{recent}",
                "",
                "最常见异常：",
            ]
            for item in (top or []):
                try:
                    name, cnt = item[0], item[1]
                except Exception:
                    name, cnt = str(item), ""
                lines.append(f"  {cnt} 次  {name}")
            summary = stats.get_summary()
            if summary:
                lines.append("")
                lines.append("汇总：")
                for k, v in list(summary.items())[:8]:
                    lines.append(f"  {k}: {v}")
            QMessageBox.information(self, "崩溃统计", "\n".join(lines))
        except Exception as e:
            print(f"[MainWindow] 崩溃统计失败: {e}")
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "崩溃统计", f"读取失败: {e}")
            except Exception:
                pass

    # ========================================================
    # 代码模板（core/code_templates.py）
    # ========================================================
    def _new_from_template(self):
        """从模板新建文件（`ui/template_picker_dialog.py`）

        `core/code_templates.py`（240 行）提供了 8 个真实模板：
        Python 类 / 函数 / 测试 / 主程序、JS 函数 / 类、`.gitignore`、`README`。
        此前**零引用**，用户只能每次手敲 class 骨架。
        """
        try:
            from ui.template_picker_dialog import show_template_picker

            text, filename = show_template_picker(self)
            if text is None:
                return

            # 直接建标签（**不要**调 `_new_file()` —— 那会再弹一次
            # "选择文件类型"对话框，用户在模板对话框里已经选过了）
            title = filename or "未命名"
            editor = self.tabs.add_tab(title)
            if editor is None:
                self.status_bar.showMessage("新建标签失败", 4000)
                return
            proxy = getattr(editor, 'proxy', None)
            if proxy is None:
                self.status_bar.showMessage("新建标签失败（无编辑器）", 4000)
                return
            proxy.set_text(text)

            # 切到编辑区
            try:
                if self.central_stack:
                    self.central_stack.setCurrentIndex(0)
            except Exception:
                pass

            self.status_bar.showMessage(
                "已从模板生成「%s」，保存时请确认文件名" % title, 6000
            )
        except Exception as e:
            print(f"[MainWindow] 从模板新建失败: {e}")
            try:
                self.status_bar.showMessage(f"从模板新建失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 会话快照（core/snapshot.py + ui/snapshot_manager_dialog.py）
    # ========================================================
    def _show_snapshot_dialog(self):
        """打开会话快照对话框

        `core/snapshot.py`（191 行）+ `ui/snapshot_manager_dialog.py`（154 行）
        此前**零引用**。功能：把"当前所有打开的文件 + 光标位置 + 窗口布局"
        存成快照，随时一键恢复 —— 对应真实的"切任务再切回来"场景。

        注意：恢复会**关闭当前所有标签**，因此对话框里已加"未保存修改保护"
        （先统一提示保存/放弃/取消，避免逐个模态框导致半恢复状态）。
        """
        try:
            from ui.snapshot_manager_dialog import SnapshotDialog

            dlg = SnapshotDialog(self, self)
            dlg.exec_()
        except Exception as e:
            print(f"[MainWindow] 会话快照失败: {e}")
            try:
                self.status_bar.showMessage(f"会话快照失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 代码片段库（ui/snippet_market_dialog.py + core/snippet_market.py）
    # ========================================================
    def _show_snippet_library(self):
        """打开代码片段库（本地片段包）

        ## 从"网络市场"改为"本地库"的原因

        原实现是网络市场客户端，`MARKET_API` 指向
        `https://api.github.com/repos/qingcao-editor/snippets/contents`
        —— **实测该地址返回 HTTP 404，仓库不存在**。
        接上 UI 也只会显示 4 条硬编码示例，"市场"是假的。

        现改为扫描本地片段包目录（默认 `<应用根>/data/snippet_packs`，
        可自选目录）：零运维、零信任风险（不执行第三方下载内容），
        核心价值（复用别人写好的片段）不变。
        """
        try:
            from ui.snippet_market_dialog import SnippetMarketDialog

            dlg = SnippetMarketDialog(self)
            dlg.exec_()
        except Exception as e:
            print(f"[MainWindow] 代码片段库失败: {e}")
            try:
                self.status_bar.showMessage(f"代码片段库失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 性能剖析（core/profiler.py + ui/profiler_panel.py）
    # ========================================================
    def _show_profiler(self):
        """打开性能剖析对话框（`ui/profiler_panel.py`）

        ## 这两个模块此前是零引用的
        `core/profiler.py`（67 行，cProfile 封装）与
        `ui/profiler_panel.py`（166 行，完整对话框）此前**零引用**，
        用户完全看不到 —— 而"某个插件让编辑器变慢"正是最常见的困扰。

        ## ★ 使用局限（必须如实告知，否则用户会误读报告）
        `cProfile` 只统计 **Python 帧**。Qt 的 C++ 事件循环、Scintilla 的
        绘制/排版耗时**都不会出现在报告里**。因此本工具适合排查：

        * 插件的 Python 回调慢（如 AI 请求解析、日志格式化）；
        * 搜索/正则匹配慢（`core/search.py`）；
        * 大文件解析/语法分析慢。

        **不适合**用来测"编辑器滚动卡不卡""窗口重绘慢不慢" ——
        那类问题请看「工具 → 📊 性能监控」（`ui/perf_monitor.py`），
        它读的是进程级 CPU/内存与 Scintilla 的行数/字节数。
        """
        try:
            from ui.profiler_panel import ProfilerDialog
            dlg = ProfilerDialog(self)
            try:
                dlg.setToolTip(
                    "cProfile 只统计 Python 帧：Qt 事件循环与 Scintilla 的\n"
                    "绘制/排版耗时不在报告里。\n"
                    "适合排查插件回调 / 搜索 / 解析慢；\n"
                    "要看整体流畅度请用「工具 → 📊 性能监控」。"
                )
            except Exception:
                pass
            dlg.exec_()
        except Exception as e:
            print(f"[MainWindow] 性能剖析失败: {e}")
            try:
                self.status_bar.showMessage(f"性能剖析失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # P1-7：差异化能力入口提升（用户找不到 = 差异化不存在）
    # ========================================================
    def _setup_feature_menu(self):
        """建「AI / Git / 调试」一级可见的入口聚合菜单

        背景（P1-7）：
            AI、Git、调试器这三条**差异化主线**目前分散在插件注册路径
            （`工具/Git/...`、AI 助手自己的菜单）。试用者很容易以为
            "这编辑器没有这些能力"。因此这里做一个聚合入口把它们
            提升为一级可见 —— 只做**导航**，不重复实现功能。
        """
        try:
            menu = self._make_menu("⭐ 特色功能")
            anchor = getattr(self, '_view_menu_action', None) or \
                self.view_menu.menuAction()
            # ⚠️ 实测坑：`QMenuBar.insertMenu()` 返回的是 **QAction**
            #   （即菜单的 menuAction），不是 QMenu。原实现把返回值直接
            #   赋给 `self.feature_menu`，后续 `addSeparator()` 就抛
            #   `AttributeError: 'QAction' object has no attribute
            #   'addSeparator'`，整个 MainWindow 构造失败。
            self.menuBar().insertMenu(anchor, menu)
            self.feature_menu = menu
        except Exception:
            try:
                self.feature_menu = self.menuBar().addMenu("⭐ 特色功能")
            except Exception as e:
                if logger:
                    logger.debug("创建特色功能菜单失败: %s", e)
                return

        # AI：直接列出 AI 助手插件**真实注册**的命令（命令面板里同源）
        self._add_plugin_commands_submenu(
            "🤖 AI 助手（ai_assistant）", "ai_assistant", "ai"
        )
        self.feature_menu.addSeparator()
        self._add_plugin_commands_submenu(
            "🔀 Git（git_deep）", "git_deep", "git"
        )
        self.feature_menu.addSeparator()
        # 调试：**复用工具菜单里已存在的 F5 动作**，绝不新建。
        #
        # ⚠️ 实测教训：先前这里用 `_add_action(..., "▶ 运行当前文件", "F5", ...)`
        #   新建了一个 QAction，于是全仓出现**两个 F5** ——
        #   `tests/test_shortcuts.py::test_f5_is_run_current_file` 与
        #   `test_no_duplicate_non_empty_shortcuts` 立刻失败，Qt 也会判定
        #   ambiguous shortcut 导致 F5 彻底失效。
        #   正确做法是把已有 QAction 加进本菜单（同一动作可在多菜单出现）。
        run_action = self._find_action_with_text("▶ 运行当前文件")
        if run_action is not None:
            self.feature_menu.addAction(run_action)
        else:
            self._add_action(self.feature_menu, "▶ 运行当前文件", None,
                             self._debug_run)
        self._add_action(self.feature_menu, "⚙ 在当前行切换断点", None,
                         self._debug_breakpoint)
        self.feature_menu.addSeparator()
        self._add_action(self.feature_menu, "🧠 LSP 状态 / 安装向导", None,
                         self._show_panel_lsp)
        self._add_action(self.feature_menu, "📊 问题（LSP 诊断）", None,
                         lambda: self._show_panel('problems'))

    def _find_action_with_text(self, text: str):
        """在整个菜单栏里按文本找已存在的 QAction（用于跨菜单复用同一动作）

        **优先返回带快捷键的那个**：实测菜单栏里可能存在**同名**动作
        （一个是真正的命令、带快捷键；另一个是无快捷键的展示项）。
        随便取第一个可能取到无快捷键的那个，导致复用失败。

        实现要点（实测坑）：不能用 `menuBar().findChildren(QAction)` ——
        菜单里的 QAction 的 parent 是**主窗口**，而不是 QMenuBar，
        因此 `findChildren` 一个都找不到（会静默返回 None，
        于是又新建一个动作，F5 就变成两个）。必须**遍历 QMenu 树**。

        为什么要复用：同一动作出现在多个菜单是正常的（VSCode 也如此），
        但**不能新建第二个带相同快捷键的 QAction** —— 那会让 Qt 报
        ambiguous shortcut，按键直接失效（实测 F5 就是这样失效的）。
        """
        try:
            from PyQt5.QtWidgets import QMenu
            found = []
            menus = list(self.findChildren(QMenu))
            # 递归展开子菜单（QMenu 的菜单项本身也是 QAction/QMenu）
            seen = set()
            stack = list(menus) + [self.menuBar()]
            while stack:
                menu = stack.pop()
                if id(menu) in seen:
                    continue
                seen.add(id(menu))
                try:
                    actions = menu.actions()
                except Exception:
                    continue
                for act in actions:
                    if act.text() == text:
                        found.append(act)
                    sub = act.menu()
                    if sub is not None:
                        stack.append(sub)
            for act in found:
                if not act.shortcut().isEmpty():
                    return act          # 带快捷键的优先
            return found[0] if found else None
        except Exception as e:
            if logger:
                logger.debug("按文本查找动作失败(%s): %s", text, e)
        return None

    def _plugin_commands(self, plugin_name: str):
        """取出某插件**已注册**的命令（键形如 `plugin.<插件>.<命令>`）

        真实链路（已核实 `app/plugins.py:1426-1433`）：
            `PluginAPI.register_command()` 会创建 QAction 并以
            `plugin.{plugin_name}.{name}` 注册到 `win.act_mgr`
            （`ActionManager.register`）。命令面板 `_load_plugin_commands()`
            正是按 `name.startswith("plugin.")` 从同一个 `act_mgr.actions`
            里取的 —— 因此本菜单与命令面板**同源**，不会出现
            "菜单里有、命令面板里没有"的偏差。

        返回: [(完整命令名, QAction), ...]，按名称排序
        """
        out = []
        try:
            mgr = getattr(self, 'act_mgr', None)
            actions = getattr(mgr, 'actions', None) if mgr else None
            if not actions:
                return out
            prefix = "plugin.%s." % plugin_name
            for key, action in actions.items():
                if isinstance(key, str) and key.startswith(prefix):
                    out.append((key, action))
        except Exception as e:
            if logger:
                logger.debug("枚举插件命令失败: %s", e)
        return sorted(out, key=lambda kv: kv[0])

    def _add_plugin_commands_submenu(self, title: str, plugin_name: str,
                                     icon_key: str = ""):
        """把某插件注册的命令加成一个子菜单

        **找不到命令时如实说明**，而不是放一个点了没反应的菜单项 ——
        这正是 P1-7 想解决的问题（用户找不到 ≠ 没有；但也不能假装有）。
        """
        try:
            sub = self.feature_menu.addMenu(title)
        except Exception:
            return
        cmds = self._plugin_commands(plugin_name)
        if not cmds:
            # 注意：不能用 `_add_action(..., slot=None)` —— 它内部会执行
            # `action.triggered.connect(None)`，PyQt 直接抛
            # `TypeError: argument 1 has unexpected type 'NoneType'`。
            # 这里手工建一个**禁用**的占位项，明确告诉用户为什么是空的。
            try:
                from PyQt5.QtWidgets import QAction as _QAction
                act = _QAction("（该插件未注册命令，或未启用）", self)
                act.setEnabled(False)
                act.setToolTip(
                    "请到「工具 → 插件管理」确认 %s 已启用" % plugin_name
                )
                sub.addAction(act)
            except Exception as e:
                if logger:
                    logger.debug("添加占位菜单项失败: %s", e)
            return
        for name, action in cmds:
            short = name.rsplit(".", 1)[-1]
            label = action.text() or short
            sc = ""
            try:
                sc = action.shortcut().toString() if action.shortcut() else ""
            except Exception:
                sc = ""
            # 直接复用插件原来的 QAction（trigger 即执行其 callback），
            # 不新建包装 —— 避免出现"两个动作、两条冲突快捷键"。
            self._add_action(sub, label, sc or None, action.trigger)

    def _make_menu(self, title):
        """创建一个 QMenu（抽出来便于异常处理）"""
        from PyQt5.QtWidgets import QMenu
        return QMenu(title, self)

    def _invoke_plugin_command(self, plugin_name: str):
        """触发某插件注册的**第一个**命令（找不到时给出明确提示）

        保留此方法供聚合入口使用；实现改为走 `_plugin_commands()`
        （此前用的 `act_mgr.list_plugin_commands()` **不存在**，
        导致这条聚合入口一点就报"未找到"）。
        """
        try:
            cmds = self._plugin_commands(plugin_name)
            if cmds:
                cmds[0][1].trigger()
                return True
            self.status_bar.showMessage(
                f"插件「{plugin_name}」未注册命令或未启用："
                f"请到「工具 → 插件管理」确认", 8000
            )
        except Exception as e:
            print(f"[MainWindow] 调用插件命令失败: {e}")
        return False

    def _toggle_ai_inline(self):
        """开关 AI 行内补全（`ui/ai_inline_completer.py`）"""
        try:
            completer = getattr(self, 'ai_inline_completer', None)
            if completer is None:
                self.status_bar.showMessage(
                    "AI 行内补全不可用：请先在插件中配置 AI 服务商"
                    "（工具 → 插件管理 → AI 助手）", 8000
                )
                return
            enabled = getattr(completer, 'enabled', False)
            if hasattr(completer, 'set_enabled'):
                completer.set_enabled(not enabled)
                self.status_bar.showMessage(
                    f"AI 行内补全已{'关闭' if enabled else '开启'}", 3000
                )
        except Exception as e:
            print(f"[MainWindow] 切换 AI 行内补全失败: {e}")

    def _debug_run(self):
        """启动调试（复用已有能力，找不到就明确提示）"""
        try:
            if hasattr(self, '_run_current_file'):
                self._run_current_file()
            else:
                self.status_bar.showMessage("调试不可用", 3000)
        except Exception as e:
            print(f"[MainWindow] 启动调试失败: {e}")

    def _debug_breakpoint(self):
        """切换当前行断点"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                return
            if hasattr(proxy, 'toggle_breakpoint'):
                proxy.toggle_breakpoint()
                n = len(proxy.get_breakpoints()) \
                    if hasattr(proxy, 'get_breakpoints') else 0
                self.status_bar.showMessage(f"当前断点数: {n}", 3000)
            else:
                self.status_bar.showMessage("该编辑器不支持断点", 3000)
        except Exception as e:
            print(f"[MainWindow] 切换断点失败: {e}")

    def _show_panel_lsp(self):
        """打开 LSP 面板"""
        try:
            if self._ensure_panel('lsp') and getattr(self, 'lsp', None):
                self.lsp.setVisible(True)
                self.lsp.raise_()
        except Exception as e:
            print(f"[MainWindow] 打开 LSP 面板失败: {e}")

    # ========================================================
    # 启动主题（修复"面板永远深色"）
    # ========================================================
    def apply_startup_theme(self):
        """启动时把**已保存的主题**应用到所有面板

        ## 真实桌面验证发现的缺陷

        打包版在真实桌面截图里，编辑器是浅色护眼主题，而所有停靠面板
        （目录树、全局搜索、性能监控……）却是**纯黑/深色**——
        左侧目录树甚至只是"一块黑矩形"，看起来像面板坏了。

        根因：
          * `main.load_theme()` 启动时只对 `QApplication` 设了 QSS；
          * 各面板在构造函数的 `_apply_style()` 里写死深色 QSS，
            **会覆盖 app 级 QSS**；
          * 真正能把面板 QSS 按主题换算的函数是
            `ThemeLoader.notify_widgets()`（它调用各面板的
            `refresh_theme()` → `adapt_qss_colors()`），
            但此前**只在用户手动切换主题时**调用，启动时从不调用。

        修复：主窗口构造完成后调用本方法 —— 读 `theme_name` 设置，
        应用 QSS 并 `notify_widgets(self, theme)`，让面板与编辑器一致。
        """
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QApplication

            from infrastructure.theme_loader import ThemeLoader

            settings = QSettings("QingCao", "Editor")
            name = settings.value("theme_name", "", type=str)
            loader = ThemeLoader()
            theme = None
            if name:
                try:
                    theme = loader.load_by_name(name)
                except Exception as e:
                    print(f"[Theme] 启动加载主题失败 {name}: {e}")
            if theme is None:
                # 没有保存过主题 → 用内置暗夜（与 main.load_theme 的回退一致）
                try:
                    from infrastructure.theme_loader import BuiltinThemes
                    theme = BuiltinThemes.dark_night()
                except Exception:
                    theme = None
            if theme is None:
                return None

            app = QApplication.instance()
            if app is not None:
                try:
                    # lazy=True：只 polish 可见控件；隐藏面板的 QSS
                    # 在它们首次显示时再套（见 theme_loader 的
                    # `_LazyThemeApplier`），避免启动时对几十个隐藏面板
                    # 逐个 setStyleSheet + unpolish/polish（实测 0.4~0.6s）。
                    loader.apply_qss(app, theme, lazy=True)
                except Exception as e:
                    print(f"[Theme] 启动 apply_qss 失败: {e}")

            # 关键：通知所有面板按主题换算 QSS
            try:
                loader.notify_widgets(self, theme)
            except Exception as e:
                print(f"[Theme] 启动 notify_widgets 失败: {e}")

            # 插件/第三方面板若无 refresh_theme，统一递归适配其硬编码 QSS
            try:
                adapt = getattr(self, "adapt_widget_styles", None)
                if callable(adapt):
                    adapt(self, theme)
            except Exception as e:
                print(f"[Theme] 启动子控件样式适配失败: {e}")

            self._startup_theme = theme
            return theme
        except Exception as e:
            print(f"[MainWindow] 启动主题应用失败: {e}")
            return None
