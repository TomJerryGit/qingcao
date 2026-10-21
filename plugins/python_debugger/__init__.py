# -*- coding: utf-8 -*-
"""Python 调试器插件（D3）—— 真正可用的编辑器内调试器。

## 路线选择：标准库 `bdb` + stdio JSON 管道（不是 debugpy / DAP）

理由：
1. **零第三方依赖**：`bdb` 是 Python 标准库，装完编辑器就能用；debugpy
   需要用户自己 `pip install`，且要处理"没装"的分支。
2. **可控**：`python -m pdb` 的输出是给人看的文本，解析脆弱；本插件用
   自写的 `driver.py`（bdb 子类）走**逐行 JSON 协议**，命令/事件都是
   结构化数据，主机侧完全可控、可单测。
3. **不会留孤儿**：被调试代码就在驱动子进程内部执行，宿主 kill 掉这个
   子进程 = 杀掉被调试程序；驱动还会在 stdin EOF（宿主崩溃）时自杀。

## 用户路径（每条都有测试）

| 路径 | 实现 | 测试 |
|---|---|---|
| 设断点 → 停在断点行并高亮 | `driver.user_line` → `break_hit` → `_on_break` → `proxy.highlight_debug_line` | `test_debugger.py::TestBreakpoints*` / `TestSessionProtocol::test_break_event_*` |
| 单步 over/into/out | `DebugSession.step_over/into/out` → driver `set_next/set_step/set_return` | `TestSessionCommands` |
| 继续 | `DebugSession.continue_` | `TestSessionCommands` |
| 查看局部变量 | driver `frame_locals` → `locals` 事件 → 面板树 | `TestDriverFormatting` / `TestPanel` |
| 终止且不留孤儿 | `DebugSession.stop()`（quit→wait→terminate→wait→kill→wait）+ stdin EOF 自杀 | `TestSessionStop` |
| 错误场景用户可见 | `_require_python_file` / `_ensure_saved` / `check_backend` | `TestPluginGuards` |
"""
import atexit
import importlib.util
import logging
import os
import subprocess
import sys

from app.plugins import PluginBase


logger = logging.getLogger(__name__)


# ============================================================
# 子模块加载
# ============================================================
def _load_sibling(name):
    """按**文件路径**加载同目录子模块。

    PluginLoader 用 `spec_from_file_location` 以合成模块名
    (`qingcao_plugin_python_debugger`) 加载本文件，因此本插件没有包
    上下文 —— `from .session import DebugSession` 会 ImportError。
    这里用文件路径显式加载，宿主加载与直接 import 两种方式都能工作。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, name + ".py")
    module_name = f"qingcao_plugin_python_debugger_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载调试子模块: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


_session_module = _load_sibling("session")
_panel_module = _load_sibling("panel")

DebugSession = _session_module.DebugSession
DebuggerPanel = _panel_module.DebuggerPanel
check_backend = _session_module.check_backend


# ============================================================
# 进程收尾兜底：无论插件是否被正常停用，都别留下调试进程
# ============================================================
_LIVE_SESSIONS = []


def _stop_all_sessions():
    for session in list(_LIVE_SESSIONS):
        try:
            session.stop()
        except Exception:
            pass
    del _LIVE_SESSIONS[:]


atexit.register(_stop_all_sessions)


# ============================================================
# 插件
# ============================================================
class Plugin(PluginBase):
    NAME = "python_debugger"
    VERSION = "2.0.0"
    DESCRIPTION = "基于标准库 bdb 的编辑器内 Python 调试器"
    AUTHOR = "hedongwei"

    #: 快捷键刻意避开宿主已占用的 F5 / F9 / F11 / Shift+F11 / F12：
    #:   F5  = 运行当前文件（宿主）
    #:   F7  = 启动调试（本插件）
    #:   F9  = 切换断点（由编辑器控件自己处理，不注册全局 QAction，
    #:         避免同键被 QShortcut 与 keyPressEvent 双重处理）
    RUN_SHORTCUT = "F6"
    DEBUG_SHORTCUT = "F7"
    CONTINUE_SHORTCUT = "F8"
    STEP_OVER_SHORTCUT = "F10"
    STEP_INTO_SHORTCUT = "Shift+F10"
    STEP_OUT_SHORTCUT = "Ctrl+F10"

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def on_activate(self):
        # v2.4 扩展点（防御式：测试桩 FakeApi 可能没有扩展点 API）
        try:
            register = getattr(self.api, "register_settings_schema", None)
            if callable(register):
                register([
                    {"key": "confirm_kill", "label": "结束调试前确认",
                     "type": "bool", "default": True},
                    {"key": "max_stack_frames", "label": "调用栈最多帧数",
                     "type": "int", "default": 50, "min": 5, "max": 500},
                ])
            add_item = getattr(self.api, "add_status_item", None)
            if callable(add_item):
                self._status = add_item("调试: 就绪")
        except Exception:
            pass

        self._session = None
        self._panel = None
        self._watched_proxies = set()

        self.api.log(f"Python 调试器已激活（bdb 后端 v{self.VERSION}）")
        self._register_menus()

    def _register_menus(self):
        """注册"工具 → Python 调试"子菜单。"""
        add = self.api.add_menu
        add("工具/Python 调试/调试当前文件",
            self.debug_current, shortcut=self.DEBUG_SHORTCUT)
        add("工具/Python 调试/运行当前文件",
            self.run_current, shortcut=self.RUN_SHORTCUT)
        add("工具/Python 调试/带参数运行...", self.run_with_args)
        add("工具/Python 调试/── 调试控制 ──", self._show_control_hint)
        add("工具/Python 调试/继续", self.debug_continue,
            shortcut=self.CONTINUE_SHORTCUT)
        add("工具/Python 调试/单步跳过 (over)", self.debug_step_over,
            shortcut=self.STEP_OVER_SHORTCUT)
        add("工具/Python 调试/单步进入 (into)", self.debug_step_into,
            shortcut=self.STEP_INTO_SHORTCUT)
        add("工具/Python 调试/单步跳出 (out)", self.debug_step_out,
            shortcut=self.STEP_OUT_SHORTCUT)
        add("工具/Python 调试/── 断点 ──", self._show_control_hint)
        add("工具/Python 调试/切换断点（F9 或单击行号）",
            self.toggle_breakpoint)
        add("工具/Python 调试/清除所有断点", self.clear_breakpoints)
        add("工具/Python 调试/── 查看 ──", self._show_control_hint)
        add("工具/Python 调试/显示调试面板", self.show_panel)
        add("工具/Python 调试/查看局部变量", self.show_locals)
        add("工具/Python 调试/查看调用栈", self.show_stack)
        add("工具/Python 调试/终止调试", self.stop_debug)

    def on_deactivate(self):
        session = self._session
        self._session = None
        if session is not None:
            try:
                session.stop()
            except Exception:
                pass
            try:
                if session in _LIVE_SESSIONS:
                    _LIVE_SESSIONS.remove(session)
            except Exception:
                pass

        panel = self._panel
        self._panel = None
        if panel is not None:
            try:
                panel.close()
                panel.deleteLater()
            except Exception:
                pass

        self._watched_proxies = set()
        try:
            self.api.log("Python 调试器插件已停用")
        except Exception:
            pass

    def _show_control_hint(self):
        self.api.show_status(
            "调试控制：F8 继续 / F10 跳过 / Shift+F10 进入 / Ctrl+F10 跳出",
            4000,
        )

    # --------------------------------------------------------
    # 前置校验（错误场景必须**用户可见**）
    # --------------------------------------------------------
    def _require_python_file(self, action="调试"):
        """返回 (filepath, None)；不满足条件时返回 (None, 用户可见提示)。"""
        proxy = self.api.current_editor()
        if proxy is None:
            return None, f"没有打开的编辑器，无法{action}。"

        filepath = ""
        try:
            filepath = self.api.get_current_filepath() or ""
        except Exception:
            filepath = ""

        if not filepath:
            return None, (
                f"请先保存文件再{action}：当前标签还没有磁盘路径"
                "（未保存的文件无法交给调试进程）。"
            )
        if not filepath.lower().endswith((".py", ".pyw")):
            return None, (
                f"只有 Python 文件可以{action}："
                f"当前是 {os.path.basename(filepath)}。"
            )
        if not os.path.isfile(filepath):
            return None, f"文件不存在，无法{action}：{filepath}"
        return filepath, None

    def _ensure_saved(self, proxy):
        """确保磁盘内容与编辑器一致。返回 (ok, message)。"""
        try:
            modified = bool(getattr(proxy, "is_modified", False))
        except Exception:
            modified = False
        if not modified:
            return True, ""

        try:
            saved = bool(self.api.save_current_file())
        except Exception as exc:
            logger.warning("自动保存失败: %s", exc)
            saved = False

        if saved:
            return True, "文件已自动保存"
        return False, (
            "文件有未保存的修改，且自动保存失败；"
            "请先按 Ctrl+S 手动保存后再调试。"
        )

    def _notify_error(self, title, message):
        """统一错误出口：日志 + 状态栏 + 对话框（都失败也不崩）。"""
        logger.warning("[python_debugger] %s: %s", title, message)
        try:
            self.api.show_status(str(message), 6000, "error")
        except Exception:
            pass
        try:
            self.api.show_message(title, str(message), "error")
        except Exception:
            pass

    # --------------------------------------------------------
    # 调试会话
    # --------------------------------------------------------
    def debug_current(self):
        """启动调试会话（D3 主入口）。"""
        try:
            proxy = self.api.current_editor()
            filepath, problem = self._require_python_file("调试")
            if problem:
                self._notify_error("无法调试", problem)
                return False

            ok, message = self._ensure_saved(proxy)
            if not ok:
                self._notify_error("无法调试", message)
                return False

            backend_ok, backend_message = check_backend()
            if not backend_ok:
                self._notify_error("调试后端不可用", backend_message)
                return False

            # 同一时间只允许一个调试会话
            if self._session is not None:
                self.stop_debug()

            session = DebugSession(self.api.get_main_window())
            self._session = session
            _LIVE_SESSIONS.append(session)

            session.output_received.connect(self._on_output)
            session.break_hit.connect(self._on_break)
            session.finished.connect(self._on_finished)
            session.failed.connect(self._on_failed)

            if not session.start(filepath):
                # session.failed 已经给出用户可见原因
                self._session = None
                try:
                    _LIVE_SESSIONS.remove(session)
                except ValueError:
                    pass
                return False

            self._send_breakpoints()
            self._watch_breakpoints()
            self.show_panel()
            if self._panel is not None:
                self._panel.set_status(
                    f"调试中：{os.path.basename(filepath)}"
                )
            count = len(self._collect_breakpoints())
            self.api.show_status(
                f"调试已启动: {os.path.basename(filepath)}"
                f"（断点文件 {count} 个）",
                3000,
                "success",
            )
            return True
        except Exception as exc:
            logger.exception("启动调试失败")
            self._notify_error("调试启动失败", str(exc))
            return False

    def _collect_breakpoints(self):
        """从**所有**打开的编辑器收集断点 → {路径: [0 基行号]}。"""
        result = {}
        try:
            proxies = self.api.all_editors() or []
        except Exception:
            proxies = []
        for proxy in proxies:
            try:
                filepath = ""
                document = getattr(proxy, "document", None)
                if document is not None:
                    filepath = getattr(document, "filepath", "") or ""
                if not filepath:
                    continue
                getter = getattr(proxy, "get_breakpoints", None)
                if not callable(getter):
                    continue
                lines = list(getter() or [])
                if lines:
                    result[filepath] = lines
            except Exception as exc:
                logger.debug("收集断点失败: %s", exc)
        return result

    def _send_breakpoints(self):
        session = self._session
        if session is None or not session.is_running:
            return False
        return session.set_breakpoints(self._collect_breakpoints())

    def _watch_breakpoints(self):
        """把编辑器的断点增删实时同步给调试进程（幂等）。"""
        if self._session is None:
            return
        try:
            proxies = self.api.all_editors() or []
        except Exception:
            proxies = []
        for proxy in proxies:
            key = id(proxy)
            if key in self._watched_proxies:
                continue
            signal = getattr(proxy, "breakpoints_changed", None)
            if signal is None:
                continue
            try:
                signal.connect(self._on_breakpoints_changed)
                self._watched_proxies.add(key)
            except Exception:
                pass

    def _on_breakpoints_changed(self, _lines=None):
        if self._session is not None and self._session.is_running:
            self._send_breakpoints()

    # ---- 调试控制 ----
    def _require_session(self, action):
        session = self._session
        if session is None or not session.is_running:
            self.api.show_status(f"当前没有正在进行的调试会话（{action}）",
                                 3000, "warning")
            return None
        return session

    def debug_continue(self):
        session = self._require_session("继续")
        if session is None:
            return False
        return session.continue_()

    def debug_step_over(self):
        session = self._require_session("单步跳过")
        if session is None:
            return False
        return session.step_over()

    def debug_step_into(self):
        session = self._require_session("单步进入")
        if session is None:
            return False
        return session.step_into()

    def debug_step_out(self):
        session = self._require_session("单步跳出")
        if session is None:
            return False
        return session.step_out()

    def stop_debug(self):
        """终止调试并确保不留孤儿进程。"""
        session = self._session
        if session is None:
            self.api.show_status("当前没有调试会话", 2000)
            return False
        try:
            exited = session.stop()
        except Exception as exc:
            logger.warning("终止调试失败: %s", exc)
            exited = False
        self._session = None
        self._watched_proxies = set()
        try:
            if session in _LIVE_SESSIONS:
                _LIVE_SESSIONS.remove(session)
        except Exception:
            pass
        self._clear_debug_highlights()
        if self._panel is not None:
            self._panel.set_status("已终止调试" if exited else "调试进程未能确认退出")
        self.api.show_status(
            "调试已终止" if exited else "调试进程未能确认退出（详见日志）",
            3000,
        )
        return True

    # --------------------------------------------------------
    # 事件回调
    # --------------------------------------------------------
    def _on_output(self, stream, text):
        if self._panel is not None:
            self._panel.append_output(text)

    def _on_break(self, filepath, line):
        """停在某文件某行（line 为 **0 基**）→ 编辑器内高亮 + 切标签。"""
        try:
            self._clear_debug_highlights()
            proxy = self._find_proxy_by_path(filepath)
            if proxy is not None:
                highlighter = getattr(proxy, "highlight_debug_line", None)
                if callable(highlighter):
                    highlighter(line)
                self._focus_editor(proxy)
            else:
                self.api.show_status(
                    f"已暂停于 {filepath}:{line + 1}（该文件未打开）", 5000
                )

            if self._panel is not None:
                payload = None
                if self._session is not None:
                    payload = self._session.last_paused
                payload = payload or {"file": filepath, "line": line + 1}
                self._panel.show_paused(payload)
        except Exception as exc:
            logger.debug("高亮调试行失败: %s", exc)

    def _on_finished(self, code):
        self._clear_debug_highlights()
        self._watched_proxies = set()
        if self._panel is not None:
            self._panel.set_status(f"调试结束（退出码 {code}）")
        self.api.show_status(f"调试结束（退出码 {code}）", 4000)
        self._session = None

    def _on_failed(self, message):
        self._notify_error("调试错误", message)

    # --------------------------------------------------------
    # 断点入口（宿主侧实现，这里只是菜单入口）
    # --------------------------------------------------------
    def toggle_breakpoint(self):
        proxy = self.api.current_editor()
        if proxy is None or not hasattr(proxy, "toggle_breakpoint"):
            self.api.show_status("没有活动的编辑器", 3000, "warning")
            return False
        # 行号越界时 toggle_breakpoint 返回 False（markerAdd 对越界行是
        # 静默失败的），这里如实转达，不能报"成功"。
        toggled = bool(proxy.toggle_breakpoint())
        lines = (
            proxy.get_breakpoints()
            if hasattr(proxy, "get_breakpoints") else []
        )
        if not toggled:
            self.api.show_status("当前位置无法设置断点（行号越界）",
                                 3000, "warning")
            return False
        self.api.show_status(f"当前文件断点：{len(lines)} 个", 2500)
        return True

    def clear_breakpoints(self):
        cleared = 0
        try:
            proxies = self.api.all_editors() or []
        except Exception:
            proxies = []
        for proxy in proxies:
            clearer = getattr(proxy, "clear_breakpoints", None)
            if callable(clearer):
                try:
                    cleared += int(clearer() or 0)
                except Exception:
                    pass
        self.api.show_status(f"已清除 {cleared} 个断点", 2500)
        return cleared

    # --------------------------------------------------------
    # 面板与查看
    # --------------------------------------------------------
    def show_panel(self):
        if self._panel is None:
            try:
                self._panel = DebuggerPanel(
                    session=self._session,
                    parent=self.api.get_main_window(),
                )
            except Exception as exc:
                self._notify_error("无法打开调试面板", str(exc))
                return None
        try:
            self._panel.show()
            self._panel.raise_()
        except Exception:
            pass
        return self._panel

    def show_locals(self):
        session = self._require_session("查看局部变量")
        if session is None:
            return False
        self.show_panel()
        return session.request_locals()

    def show_stack(self):
        session = self._require_session("查看调用栈")
        if session is None:
            return False
        self.show_panel()
        return session.request_stack()

    # --------------------------------------------------------
    # 普通运行（不调试）—— 保留原能力
    # --------------------------------------------------------
    def run_current(self):
        """运行当前文件（宿主 F5 会调用到这里）。"""
        filepath, problem = self._require_python_file("运行")
        if problem:
            self._notify_error("无法运行", problem)
            return False
        return self._spawn(filepath, [], "运行")

    def run_with_args(self):
        """带参数运行（不调试）。"""
        filepath, problem = self._require_python_file("运行")
        if problem:
            self._notify_error("无法运行", problem)
            return False
        args, ok = self.api.ask_string(
            "运行参数", "命令行参数（空格分隔）:", ""
        )
        if not ok:
            return False
        return self._spawn(filepath, args.split(), "运行")

    def _spawn(self, filepath, args, action):
        """普通运行：**新控制台**里跑，方便交互式输入。

        注意：调试走的是管道（不会弹黑框），这里的 CREATE_NEW_CONSOLE
        只用于"只运行不调试"的场景。
        """
        try:
            command = [sys.executable, filepath] + [str(a) for a in args]
            cwd = os.path.dirname(filepath) or os.getcwd()
            kwargs = {"cwd": cwd}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NEW_CONSOLE", 0
                )
            process = subprocess.Popen(command, **kwargs)
            # 普通运行**刻意不持有子进程句柄**：用户在新控制台里交互，
            # 关掉编辑器不应连带杀死它（这与调试路径"绝不遗留进程"
            # 的要求正好相反，两条路径分开处理）。
            del process
            self.api.show_status(
                f"{action}: {os.path.basename(filepath)}", 2500, "success"
            )
            return True
        except Exception as exc:
            self._notify_error(f"{action}失败", str(exc))
            return False

    # --------------------------------------------------------
    # 工具
    # --------------------------------------------------------
    def _find_proxy_by_path(self, filepath):
        try:
            target = os.path.normcase(os.path.abspath(filepath))
        except Exception:
            return None
        try:
            proxies = self.api.all_editors() or []
        except Exception:
            proxies = []
        for proxy in proxies:
            document = getattr(proxy, "document", None)
            current = getattr(document, "filepath", None) if document else None
            if not current:
                continue
            try:
                if os.path.normcase(os.path.abspath(current)) == target:
                    return proxy
            except Exception:
                continue
        return None

    def _focus_editor(self, proxy):
        try:
            window = self.api.get_main_window()
            tabs = getattr(window, "tabs", None)
            if tabs is None:
                return
            for index in range(tabs.count()):
                widget = tabs.widget(index)
                if getattr(widget, "proxy", None) is proxy:
                    tabs.setCurrentIndex(index)
                    return
        except Exception:
            pass

    def _clear_debug_highlights(self):
        try:
            proxies = self.api.all_editors() or []
        except Exception:
            proxies = []
        for proxy in proxies:
            clearer = getattr(proxy, "clear_debug_line", None)
            if callable(clearer):
                try:
                    clearer()
                except Exception:
                    pass
