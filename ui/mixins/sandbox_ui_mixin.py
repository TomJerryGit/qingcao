# -*- coding: utf-8 -*-
"""沙箱插件 UI/诊断（从 MainWindow 抽取，v2.18）"""

import hashlib
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.mixins.capability_wiring_mixin import CapabilityWiringMixin
from ui.mixins.edit_ops_mixin import EditOpsMixin
from ui.mixins.file_ops_mixin import FileOpsMixin
from ui.mixins.project_mixin import ProjectMixin
from ui.mixins.status_bar_mixin import StatusBarMixin


logger = logging.getLogger("QingCao")


class SandboxUIMixin:
    """沙箱插件 UI/诊断（从 MainWindow 抽取，v2.18）"""

    def _apply_sandbox_configs(self):
        """启动时把已保存的插件配置下发到沙箱插件（P1 第3步）"""
        try:
            from infrastructure.plugin_sandbox_manager import load_plugin_config
        except Exception:
            return 0
        count = 0
        for name, sp in (self._get_sandboxed_plugins() or {}).items():
            try:
                schema = sp.config_schema()
                if not schema:
                    continue
                values = load_plugin_config(name, schema)
                if sp.config_apply(values):
                    count += 1
            except Exception:
                continue
        return count

    def _sandbox_live_enabled(self):
        try:
            from PyQt5.QtCore import QSettings
            return bool(QSettings("QingCao", "Editor").value(
                "sandbox_live_diagnostics", False, type=bool))
        except Exception:
            return False

    def _set_sandbox_live_diagnostics(self, enabled):
        """实时沙箱诊断开关（默认关，避免不必要的子进程调用）"""
        try:
            from PyQt5.QtCore import QSettings
            s = QSettings("QingCao", "Editor")
            s.setValue("sandbox_live_diagnostics", bool(enabled))
            s.sync()
        except Exception:
            pass
        try:
            self.status_bar.showMessage(
                "实时沙箱诊断: %s" % ("开启" if enabled else "关闭"), 2500)
        except Exception:
            pass

    def _schedule_sandbox_diagnostics(self):
        """编辑后 500ms 防抖，只触发一次诊断"""
        if not self._sandbox_live_enabled():
            return
        try:
            if not hasattr(self, "_sandbox_diag_timer"):
                from PyQt5.QtCore import QTimer
                self._sandbox_diag_timer = QTimer(self)
                self._sandbox_diag_timer.setSingleShot(True)
                self._sandbox_diag_timer.setInterval(500)
                self._sandbox_diag_timer.timeout.connect(
                    self._run_live_sandbox_diagnostics)
            self._sandbox_diag_timer.start()
        except Exception:
            pass

    def _run_live_sandbox_diagnostics(self):
        try:
            if not self._sandbox_live_enabled():
                return 0
            try:
                proxy = self.tabs.current_proxy()
                text = proxy.get_text() if proxy is not None else ""
                if len(text) > self._live_diag_limit():
                    if not getattr(self, "_live_diag_skip_notified",
                                   False):
                        self._live_diag_skip_notified = True
                        self.status_bar.showMessage(
                            "文件过大（>5MB），已跳过实时沙箱诊断", 4000)
                    return 0
                self._live_diag_skip_notified = False
            except Exception:
                pass
            return self.run_sandboxed_diagnostics(all_files=False)
        except Exception:
            return 0

    def _hook_sandbox_live_tab(self, index):
        """为打开的编辑器接上编辑事件 → 防抖诊断"""
        try:
            ed = self.tabs.widget(index)
            if ed is None or not hasattr(ed, "modified_changed"):
                return
            ed.modified_changed.connect(
                lambda *a: self._schedule_sandbox_diagnostics())
        except Exception:
            pass

    def _sandbox_config_saved(self, plugin_name, values):
        """保存配置并即时生效（v2.11.0 P0 配置热更新）"""
        try:
            from infrastructure.plugin_sandbox_manager import save_plugin_config
        except Exception:
            return False
        sp = (self._get_sandboxed_plugins() or {}).get(plugin_name)
        if sp is None:
            return False
        try:
            schema = sp.config_schema()
            saved = save_plugin_config(plugin_name, schema, values)
            ok = bool(sp.config_apply(saved))
        except Exception as e:
            self.status_bar.showMessage("插件配置保存失败: %s" % e, 3000)
            return False
        try:
            self.run_sandboxed_diagnostics()
        except Exception:
            pass
        try:
            self.refresh_sandbox_plugin_menus(quiet=True)
        except Exception:
            pass
        try:
            from infrastructure.instance_broadcast import notify_config_changed
            notify_config_changed(plugin_name)
        except Exception:
            pass
        self._refresh_sandbox_status()
        self.status_bar.showMessage(
            "插件配置已保存%s: %s"
            % ("并即时生效" if ok else "（下发失败）", plugin_name), 3000)
        return ok

    def open_sandbox_plugin_settings(self, plugin_name):
        """按插件 config_schema 动态渲染设置对话框（P1 第3步）"""
        try:
            from PyQt5.QtWidgets import (
                QCheckBox,
                QDialog,
                QDialogButtonBox,
                QDoubleSpinBox,
                QFormLayout,
                QLineEdit,
                QPlainTextEdit,
                QSpinBox,
                QVBoxLayout,
                QWidget,
            )

            from infrastructure.plugin_sandbox_manager import load_plugin_config, save_plugin_config
        except Exception:
            return False
        plugins = self._get_sandboxed_plugins()
        sp = plugins.get(plugin_name)
        if sp is None:
            self.status_bar.showMessage("插件不可用: %s" % plugin_name, 3000)
            return False
        schema = sp.config_schema()
        if not schema:
            self.status_bar.showMessage("插件未声明配置: %s" % plugin_name,
                                        3000)
            return False
        values = load_plugin_config(plugin_name, schema)
        dlg = QDialog(self)
        dlg.setWindowTitle("插件设置 - %s" % plugin_name)
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
        widgets = {}
        for key, spec in schema.items():
            typ = str(spec.get("type") or "str")
            label = str(spec.get("label") or key)
            val = values.get(key, spec.get("default"))
            if typ == "bool":
                w = QCheckBox()
                w.setChecked(bool(val))
            elif typ == "int":
                w = QSpinBox()
                w.setRange(-1000000, 1000000)
                w.setValue(int(val or 0))
            elif typ == "float":
                w = QDoubleSpinBox()
                w.setRange(-1000000.0, 1000000.0)
                w.setDecimals(3)
                w.setValue(float(val or 0.0))
            elif typ == "str_list":
                w = QPlainTextEdit()
                w.setPlainText("\n".join(str(x) for x in (val or [])))
                w.setFixedHeight(80)
            else:
                w = QLineEdit(str(val or ""))
            widgets[key] = (typ, w)
            form.addRow(label, w)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec_() != QDialog.Accepted:
            return False
        result = {}
        for key, (typ, w) in widgets.items():
            if typ == "bool":
                result[key] = w.isChecked()
            elif typ == "int":
                result[key] = w.value()
            elif typ == "float":
                result[key] = w.value()
            elif typ == "str_list":
                result[key] = [s for s in
                               w.toPlainText().splitlines() if s.strip()]
            else:
                result[key] = w.text()
        return self._sandbox_config_saved(plugin_name, result)

    def _invoke_sandbox_menu(self, plugin_name, menu_id):
        """执行沙箱插件菜单回调并反馈状态"""
        try:
            plugins = self._get_sandboxed_plugins()
            sp = plugins.get(plugin_name)
            if sp is None:
                self.status_bar.showMessage("插件不可用: %s" % plugin_name,
                                            3000)
                return False
            ok = bool(sp.invoke_menu(menu_id))
            status = ""
            try:
                status = sp.status_text() or ""
            except Exception:
                status = ""
            msg = "插件 %s: %s%s" % (
                plugin_name, "成功" if ok else "失败",
                (" · " + status) if status else "")
            self.status_bar.showMessage(msg, 3000)
            try:
                self.run_sandboxed_diagnostics()
            except Exception:
                pass
            self._refresh_sandbox_status()
            return ok
        except Exception as e:
            try:
                self.status_bar.showMessage("插件菜单调用失败: %s" % e, 3000)
            except Exception:
                pass
            return False

    def refresh_sandbox_plugin_menus(self, quiet=False):
        """按沙箱插件声明重建「插件菜单」子菜单（P1 第3步）"""
        try:
            from PyQt5.QtWidgets import QAction
            tools_menu = getattr(self, "tools_menu", None)
            if tools_menu is None:
                return 0
            old = getattr(self, "_sandbox_menu", None)
            if old is not None:
                old.clear()
                tools_menu.removeAction(old.menuAction())
            specs = self._sandbox_menu_specs()
            sub = tools_menu.addMenu("🧩 插件菜单")
            self._sandbox_menu = sub
            if not specs:
                act = QAction("（无可用沙箱插件）", self)
                act.setEnabled(False)
                sub.addAction(act)
            else:
                for spec in specs:
                    label = spec["label"]
                    if spec.get("path"):
                        label = "%s  [%s]" % (label, spec["path"])
                    act = QAction(label, self)
                    name, mid = spec["plugin"], spec["id"]
                    act.triggered.connect(
                        lambda checked=False, n=name, m=mid:
                        self._invoke_sandbox_menu(n, m))
                    sub.addAction(act)
            try:
                for name, sp in (self._get_sandboxed_plugins()
                                 or {}).items():
                    try:
                        if not sp.config_schema():
                            continue
                    except Exception:
                        continue
                    st = QAction("⚙ 设置：%s" % name, self)
                    st.triggered.connect(
                        lambda checked=False, n=name:
                        self.open_sandbox_plugin_settings(n))
                    sub.addAction(st)
            except Exception:
                pass
            sub.addSeparator()
            refresh = QAction("🔄 刷新插件菜单", self)
            refresh.triggered.connect(
                lambda checked=False: self.refresh_sandbox_plugin_menus())
            sub.addAction(refresh)
            if not quiet:
                self.status_bar.showMessage(
                    "插件菜单已刷新: %d 项" % len(specs), 2000)
            return len(specs)
        except Exception as e:
            print(f"[MainWindow] 刷新插件菜单失败: {e}")
            return 0

    def _sandbox_menu_specs(self):
        """收集沙箱插件的菜单声明（第2步：仅数据，不创建 UI）"""
        try:
            from infrastructure.plugin_sandbox_manager import collect_menu_specs
            return collect_menu_specs(self._get_sandboxed_plugins())
        except Exception as e:
            print(f"[MainWindow] 收集沙箱菜单失败: {e}")
            return []

    def ignore_sandboxed_diagnostics(self):
        """把沙箱诊断中的可疑词加入各插件忽略表，然后重跑发布（P2）"""
        try:
            proxy = self.tabs.current_proxy()
        except Exception:
            proxy = None
        if proxy is None:
            self.status_bar.showMessage("没有打开的编辑器", 2500)
            return 0
        try:
            text = proxy.get_text() or ""
        except Exception:
            return 0
        plugins = self._get_sandboxed_plugins()
        if not plugins:
            self.status_bar.showMessage("没有启用的沙箱插件", 2500)
            return 0
        added = 0
        for _name, sp in plugins.items():
            try:
                items = sp.diagnostics(text) or []
            except Exception:
                continue
            words = set()
            for item in items:
                token = str(item.get("message", "")).split("：")[-1].strip()
                if token:
                    words.add(token)
            for word in words:
                try:
                    if sp.add_ignore_word(word):
                        added += 1
                except Exception:
                    continue
        count = self.run_sandboxed_diagnostics()
        self.status_bar.showMessage(
            "沙箱拼写：忽略 %d 个词，剩余诊断 %d 条" % (added, count), 3000)
        return added

    def _refresh_sandbox_status(self):
        """状态栏展示沙箱插件的 status_text（v2.12.0 P1 / v2.14 传文本）"""
        try:
            text = ""
            try:
                proxy = self.tabs.current_proxy()
                if proxy is not None:
                    text = (proxy.get_text() or "")[: 2 * 1024 * 1024]
            except Exception:
                text = ""
            parts = []
            for name, sp in (self._get_sandboxed_plugins() or {}).items():
                try:
                    try:
                        txt = sp.status_text(text) or ""
                    except TypeError:
                        txt = sp.status_text() or ""
                except Exception:
                    txt = ""
                if txt:
                    parts.append("%s: %s" % (name, txt))
            if parts:
                self.status_bar.showMessage(" | ".join(parts)[:120], 4000)
        except Exception:
            pass

    def clear_sandbox_problems(self) -> int:
        """清除所有沙箱来源诊断，保留 LSP/普通插件来源（v2.15）"""
        try:
            from core.problems import get_problem_manager
            manager = get_problem_manager()
        except Exception:
            return 0
        removed = 0
        try:
            files = list(getattr(manager, "problems", {}).items())
            for fp, problems in files:
                keep = [p for p in problems
                        if not str(getattr(p, "source", "")).startswith(
                            "sandbox:")]
                removed += len(problems) - len(keep)
                if len(keep) != len(problems):
                    manager.set_file_problems(fp, keep)
            self.status_bar.showMessage(
                "已清除沙箱诊断 %d 条" % removed, 2500)
        except Exception:
            pass
        return removed

    def _sandbox_diagnostic_targets(self, all_files=True):
        """收集沙箱诊断目标（文件路径, 文本）；all_files=False 只取当前文件"""
        out = []
        try:
            tabs = getattr(self, "tabs", None)
            if tabs is None:
                return out
            if all_files:
                indexes = list(range(tabs.count()))
            else:
                idx = tabs.currentIndex()
                indexes = [idx] if idx >= 0 else []
            for i in indexes:
                try:
                    w = tabs.widget(i)
                except Exception:
                    continue
                proxy = getattr(w, "proxy", None)
                if proxy is None:
                    continue
                try:
                    text = proxy.get_text() or ""
                    doc = getattr(proxy, "document", None)
                    fp = getattr(doc, "filepath", "") or ""
                except Exception:
                    continue
                out.append((fp, text))
            if not out:
                # 兼容：部分测试/降级标签实现只提供 current_proxy
                try:
                    proxy = tabs.current_proxy()
                except Exception:
                    proxy = None
                if proxy is not None:
                    try:
                        text = proxy.get_text() or ""
                        doc = getattr(proxy, "document", None)
                        fp = getattr(doc, "filepath", "") or ""
                    except Exception:
                        text, fp = "", ""
                    out.append((fp, text))
        except Exception:
            pass
        return out

    def run_sandboxed_diagnostics(self, all_files=True):
        """运行沙箱子进程插件诊断并发布到问题面板（v2.15 按文件聚合）

        插件只返回诊断数据；发布/替换逻辑由宿主完成，并按
        `sandbox:<插件名>` 作为来源，避免清掉其它来源（LSP/普通插件）。

        all_files=True 时对所有已打开文件分别诊断并逐文件发布，
        问题面板自然按文件分组展示；实时诊断传 False 只算当前文件。
        """
        plugins = self._get_sandboxed_plugins()
        if not plugins:
            self.status_bar.showMessage("没有启用的沙箱插件", 2500)
            return 0
        targets = self._sandbox_diagnostic_targets(all_files=all_files)
        if not targets:
            self.status_bar.showMessage("没有打开的编辑器", 2500)
            return 0
        try:
            from core.problems import Problem, get_problem_manager
            manager = get_problem_manager()
        except Exception as e:
            self.status_bar.showMessage("问题管理器不可用: %s" % e, 3000)
            return 0
        sources = {"sandbox:%s" % n for n in plugins}
        total = 0
        for fp, text in targets:
            if len(text) > self._live_diag_limit():
                continue
            try:
                existing = list(manager.get_for_file(fp) or [])
                keep = [p for p in existing
                        if getattr(p, "source", "") not in sources]
            except Exception:
                keep = []
            produced = []
            for name, sp in plugins.items():
                try:
                    items = sp.diagnostics(text) or []
                except Exception:
                    continue
                for it in items:
                    try:
                        produced.append(Problem(
                            filepath=fp,
                            line=int(it.get("line", 0) or 0),
                            col=int(it.get("col", 0) or 0),
                            severity=str(it.get("severity", "warning")),
                            message=str(it.get("message", "")),
                            source="sandbox:%s" % name,
                            code=str(it.get("code", "")),
                        ))
                    except Exception:
                        continue
            try:
                manager.set_file_problems(fp, keep + produced)
            except Exception:
                pass
            total += len(produced)
        self.status_bar.showMessage(
            "沙箱诊断: %d 个文件, %d 条" % (len(targets), total), 3000)
        return total

    def _get_sandboxed_plugins(self):
        """惰性创建沙箱插件代理（默认空：只有 manifest 声明的才会出现）"""
        try:
            import os as _os

            from infrastructure.plugin_sandbox_manager import (
                SandboxedPlugin,
                discover_sandboxed_plugins,
            )
            root = (getattr(self, "_sandbox_plugin_dir", None)
                    or _os.environ.get("QINGCAO_SANDBOX_PLUGIN_DIR")
                    or _os.path.join(
                        _os.path.dirname(_os.path.dirname(
                            _os.path.abspath(__file__))), "plugins"))
            for name, path in discover_sandboxed_plugins(root):
                if name not in self._sandboxed_plugins:
                    self._sandboxed_plugins[name] = SandboxedPlugin(path)
        except Exception as e:
            print(f"[MainWindow] 沙箱插件发现失败: {e}")
        return self._sandboxed_plugins

    def _close_sandboxed_plugins(self):
        """关闭所有沙箱子进程（退出时调用，避免孤儿进程）"""
        for sp in list(getattr(self, "_sandboxed_plugins", {}).values()):
            try:
                sp.close()
            except Exception:
                pass
        self._sandboxed_plugins = {}
