# -*- coding: utf-8 -*-
"""AI 助手 Ollama 面板逻辑（v2.26 从 __init__ 拆出）。"""

import threading  # noqa: F401

from PyQt5.QtCore import QTimer  # noqa: F401

from .ai_common import *  # noqa: F401,F403,F405
from .ai_panel import OllamaPanel, _OllamaStatusBridge  # noqa: F401


class OllamaPanelMixin:
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
                "Ollama 管理",
                self.ollama_panel,
                area="right",
                visible=False,
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
        #
        # ★ 状态刷新走**后台线程**（见 `_refresh_ollama_status`）：
        #   `status_summary()` 内含两次 HTTP（4s + 15s 超时），
        #   实测同步执行会阻塞 UI 4.1 秒。这里先建好信号桥。
        self._plugin_closing = False
        # v2.4 状态栏常驻项：Ollama 状态（由后台信号桥更新）
        self._status_item = None
        try:
            self._status_item = self.api.add_status_item("🦙 Ollama: -")
        except Exception:
            self._status_item = None
        try:
            self._ollama_status_bridge = _OllamaStatusBridge()
            self._ollama_status_bridge.ready.connect(self._on_ollama_status_ready)
        except Exception as e:
            self._ollama_status_bridge = None
            self.api.log("创建 Ollama 状态桥失败: %s" % e, "error")

        # ---- v2.4 设置 schema（工具 → 插件设置）----
        try:
            self.api.register_settings_schema(
                [
                    {
                        "key": "status_refresh_seconds",
                        "label": "Ollama 状态刷新间隔(秒)",
                        "type": "int",
                        "default": 60,
                        "min": 15,
                        "max": 600,
                    },
                    {
                        "key": "enable_inline",
                        "label": "启用内联补全",
                        "type": "bool",
                        "default": True,
                    },
                ]
            )
        except Exception:
            pass
        try:
            interval_s = int(self.api.get_config("status_refresh_seconds", 60))
        except Exception:
            interval_s = 60
        try:
            if not bool(self.api.get_config("enable_inline", True)):
                comp = getattr(self, "inline_completer", None)
                if comp is not None:
                    comp.set_enabled(False)
        except Exception:
            pass

        try:
            self._ollama_timer = QTimer(self.ollama_panel)
            self._ollama_timer.setInterval(max(15, interval_s) * 1000)
            self._ollama_timer.timeout.connect(self._refresh_ollama_status)
            self._ollama_timer.start()
        except Exception as e:
            self._ollama_timer = None
            self.api.log("创建 Ollama 状态定时器失败: %s" % e, "error")

        # 启动后延迟做一次状态提示（后台线程执行，不阻塞启动）
        try:
            QTimer.singleShot(3000, self._refresh_ollama_status)
        except Exception:
            pass

    def _toggle_ollama_panel(self):
        """显示/隐藏 Ollama 面板"""
        dock = getattr(self, "_ollama_dock", None)
        if dock is None:
            self.api.show_status("Ollama 面板未注册（可能缺少 dialog 权限）", 4000, "warning")
            return
        try:
            if dock.isVisible():
                dock.hide()
            else:
                dock.show()
                dock.raise_()
                panel = getattr(self, "ollama_panel", None)
                if panel is not None:
                    panel.refresh()
        except Exception as e:
            self.api.log("切换 Ollama 面板失败: %s" % e, "error")

    def _check_ollama_status(self):
        """菜单触发的状态检查（改用宿主 v2.3 的 run_background）

        插件自己 `threading.Thread` + 手工投递容易在窗口销毁后 emit 崩溃；
        `api.run_background` 用 QObject 信号桥保证回调回主线程，
        且随插件卸载自动取消。
        """
        panel = getattr(self, "ollama_panel", None)
        if panel is None:
            return
        try:
            panel.test_connection()
        except Exception:
            pass
        try:
            self.api.run_background(
                panel.status_summary,
                on_done=lambda summary: self.api.show_status("🦙 %s" % summary, 3000, "info"),
                on_error=lambda msg: self.api.log("Ollama 状态检查失败: %s" % msg, "warning"),
                name="ollama-status",
            )
        except Exception as e:
            self.api.log("启动后台状态检查失败: %s" % e, "error")

    def _refresh_ollama_status(self):
        """刷新状态栏摘要（**后台线程**，绝不在 UI 线程做 HTTP）

        缺陷与修复说明见 `_OllamaStatusBridge` / `_on_ollama_status_ready`。
        """
        panel = getattr(self, "ollama_panel", None)
        if panel is None or getattr(self, "_plugin_closing", False):
            return

        # 上一次刷新还没结束就跳过（Ollama 无响应时避免线程堆积）
        th = getattr(self, "_ollama_status_thread", None)
        if th is not None and th.is_alive():
            return

        bridge = getattr(self, "_ollama_status_bridge", None)
        if bridge is None:
            return

        def _work():
            try:
                summary = panel.status_summary()
            except Exception:
                return
            if getattr(self, "_plugin_closing", False):
                return
            try:
                bridge.ready.emit(summary)
            except RuntimeError:
                # 桥对象已销毁（插件卸载中）
                pass

        try:
            th = threading.Thread(target=_work, daemon=True, name="ollama-status")
            self._ollama_status_thread = th
            th.start()
        except Exception as e:
            self.api.log("启动 Ollama 状态线程失败: %s" % e, "error")

    def _on_ollama_status_ready(self, summary: str):
        """后台线程算完，回到主线程更新状态栏"""
        if getattr(self, "_plugin_closing", False):
            return
        try:
            if self._status_item is not None:
                self._status_item.setText("🦙 %s" % summary)
            self.api.show_status("🦙 %s" % summary, 3000, "info")
        except Exception:
            pass
