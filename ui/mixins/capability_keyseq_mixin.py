# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""按键序列/多键快捷键（v2.25 从 capability_wiring 拆出）。"""

from ui.mixins.capability_wiring_common import *  # noqa: F401,F403


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
        self._owner_ref = weakref.ref(owner) if owner is not None else (lambda: None)

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
            if getattr(owner, "_closing", False):
                return False
            handler = getattr(owner, "_handle_keyseq_event", None)
            if handler is None:
                return False
            return bool(handler(obj, event))
        except (RuntimeError, ReferenceError):
            # 窗口的 C++ 对象已销毁 → 安静放行
            return False
        except Exception:
            return False


class KeySequenceMixin:
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
            filt = getattr(self, "_keyseq_app_filter", None)
            if filt is not None and _KEYSEQ_APP_FILTER is filt:
                try:
                    app = QApplication.instance()
                    if app is not None:
                        app.removeEventFilter(filt)
                except Exception:
                    pass
                _KEYSEQ_APP_FILTER = None
            self._keyseq_app_filter = None
            mgr = getattr(self, "key_sequence_manager", None)
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

            mgr = getattr(self, "act_mgr", None)
            actions = getattr(mgr, "actions", {}) or {}

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
                    problems.append(
                        (
                            " ".join(keys),
                            "前缀键 %s 已被动作占用: %s" % (prefix, shortcut_owners[prefix][:3]),
                        )
                    )
                # 处理器必须存在
                if not callable(getattr(self, handler_name, None)):
                    problems.append((" ".join(keys), "缺少处理器 %s" % handler_name))
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

            mgr = getattr(self, "key_sequence_manager", None)
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
