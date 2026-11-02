# -*- coding: utf-8 -*-
"""面板懒加载与注册（从 MainWindow 抽取，v2.18）"""

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


class PanelRegistryMixin:
    """面板懒加载与注册（从 MainWindow 抽取，v2.18）"""

    def _build_docks(self):
        """构建所有可停靠面板"""
        # 面板引用（初始为 None）
        self.outline = None
        self.outline_enhanced = None
        self.outline_enhanced_dock = None
        self.dir_tree = None
        self.dir_tree_dock = None
        self.minimap = None
        self.minimap_dock = None
        self.gsearch = None
        self.console = None
        self.search_bar = None
        self.plugins_panel = None
        self.perf_monitor = None

        # P1-3: 记录哪些面板已经构造过（惰性构造用）
        self._panels_built = set()

        # 设置角落
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        # 构造"开箱即有"的常用面板。
        #
        # 必须在这里（而不是等用户点菜单）完成，原因有二：
        #   1. 会话恢复 `_restore_session` 在 200ms 后执行，它按
        #      `findChildren(QDockWidget)` 恢复可见性 —— 面板必须已存在；
        #   2. 会话**保存**会采集已存在的面板；若一个都没有，就会把
        #      用户布局覆盖成空（见 app/session.py 的 _capture_docks）。
        #
        # 注意：各构造器末尾保留了旧版的 `hide()`（面板默认不显示）。
        # 因此这里构造后需要**显式显示**，否则界面依旧是空的。
        for name in self._default_panels_for_screen():
            try:
                if self._ensure_panel(name):
                    self._show_panel(name)
            except Exception as e:
                print(f"[MainWindow] 默认面板 {name} 构造失败: {e}")

    def _default_panels_for_screen(self):
        """按当前屏幕的**逻辑可用区域**决定"开箱面板"数量

        ★ 高 DPI 验证发现（真实桌面 200% 截图）：

            1920x1080 物理屏在 200% 缩放下只有 **960x540 逻辑像素**。
            此时仍默认铺开 4 个面板（左目录树 + 底全局搜索 +
            右插件 + 底性能监控），编辑器区域被挤到**只剩 3 行文本**，
            全局搜索面板的单选项还被裁掉一半 —— 界面基本没法用。

            这是"高 DPI ≈ 小屏"的普遍情况（1080p 笔记本开 150%~200%
            很常见，4K 开 200% 也只有 1920x1080 逻辑）。

        策略（简单、可预期）：
          * 逻辑可用区域 >= 1280x720 → 保持原本的完整默认面板集；
          * 否则 → **只开左侧目录树**，其余面板由用户按需从
            「视图 → 面板」打开（各自记住可见性，会话恢复也会覆盖）。

        注意：会话恢复（`_restore_session`）在此之后执行，会按用户上次
        保存的布局重新显示面板 —— 因此本策略只影响"首次/无会话"的默认。
        """
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            scr = app.primaryScreen() if app is not None else None
            if scr is not None:
                geo = scr.availableGeometry()
                if geo.width() < 1280 or geo.height() < 720:
                    print("[MainWindow] 逻辑屏幕 %dx%d 偏小（高 DPI/小屏），"
                          "仅默认打开目录树" % (geo.width(), geo.height()))
                    return ('dir_tree',)
        except Exception as e:
            print(f"[MainWindow] 检测屏幕尺寸失败: {e}")
        return self._DEFAULT_PANELS

    def _show_panel(self, name: str) -> bool:
        """显示指定面板（按属性名，兼容"面板本身是 dock"与"面板包在 dock 里"两种形式）

        为什么要单独一个方法：各面板的封装形式不统一 ——
        `outline`/`gsearch`/`console`/`plugins_panel`/`perf_monitor`
        本身就是 QDockWidget，而 `dir_tree`/`minimap` 是
        `QDockWidget` 包住一个内容控件（`dir_tree_dock`/`minimap_dock`）。
        """
        target = getattr(self, name, None)
        if target is None:
            return False
        if name in ("dir_tree", "minimap"):
            target = getattr(self, name + "_dock", None) or target
        try:
            target.setVisible(True)
            # 折叠状态下 setVisible 不会真正展开，这里确保还原
            if hasattr(target, "show"):
                target.show()
            return True
        except Exception as e:
            print(f"[MainWindow] 显示面板 {name} 失败: {e}")
            return False

    def _ensure_panel(self, name: str) -> bool:
        """确保指定面板已构造。

        参数:
            name: 面板属性名（见 _LAZY_PANELS）

        返回:
            面板当前是否可用（构造失败或名称非法时为 False）
        """
        if name not in self._LAZY_PANELS:
            print(f"[MainWindow] 未知面板: {name}")
            return False
        # 已构造过（可能构造失败留下 None）
        if name in self._panels_built:
            return getattr(self, name, None) is not None

        self._panels_built.add(name)
        builder = getattr(self, f'_build_panel_{name}', None)
        if builder is None:
            return False
        try:
            builder()
        except Exception as e:
            print(f"[MainWindow] 面板 {name} 构造失败: {e}")
            setattr(self, name, None)
            return False
        panel = getattr(self, name, None)
        # 惰性构造的面板在构造函数里写死了深色 QSS；
        # 启动主题已确定时必须立刻套用，否则首次打开会呈现"一块黑矩形"
        # （真实桌面验证复现过的缺陷）。
        self.apply_theme_to_widget(panel)
        return panel is not None

    def _build_panel_outline(self):
        """构造基础版大纲面板"""
        try:
            from ui.outline_panel import OutlinePanel
            self.outline = OutlinePanel(self)
            self.outline.setObjectName("OutlinePanel")
            self.outline.symbol_clicked.connect(self._on_symbol_clicked)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.outline)
        except Exception as e:
            print(f"[MainWindow] OutlinePanel 加载失败: {e}")
            self.outline = None

    def _build_panel_outline_enhanced(self):
        """构造增强版大纲面板

        P3-8 重构后 outline_panel_enhanced.py 已合并到
        outline_panel.py，通过 OutlinePanel(enhanced=True) 启用
        增强功能（面包屑、类型筛选、排序切换、跟随光标、3 列树）。
        """
        try:
            from ui.outline_panel import OutlinePanel
            self.outline_enhanced = OutlinePanel(self, enhanced=True)
            self.outline_enhanced.setObjectName("OutlineEnhancedDock")
            self.outline_enhanced.symbol_clicked.connect(
                self._on_symbol_clicked
            )
            self.addDockWidget(
                Qt.LeftDockWidgetArea, self.outline_enhanced
            )
            # 默认隐藏（避免与基础版重叠）
            self.outline_enhanced.hide()
        except Exception as e:
            print(f"[MainWindow] 增强大纲加载失败: {e}")
            self.outline_enhanced = None

    def _build_panel_dir_tree(self):
        """构造目录树面板"""
        try:
            from ui.directory_tree import DirectoryTree
            self.dir_tree = DirectoryTree()
            self.dir_tree.file_double_clicked.connect(
                self._on_file_from_tree
            )
            self.dir_tree.file_opened.connect(self._on_file_from_tree)

            self.dir_tree_dock = QDockWidget("项目", self)
            self.dir_tree_dock.setObjectName("DirectoryTreeDock")
            self.dir_tree_dock.setWidget(self.dir_tree)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dir_tree_dock)
        except Exception as e:
            print(f"[MainWindow] DirectoryTree 加载失败: {e}")
            self.dir_tree = None
            self.dir_tree_dock = None

    def _build_panel_minimap(self):
        """构造 Minimap 面板（安全模式，失败不影响启动）"""
        try:
            from ui.minimap import Minimap
            self.minimap = Minimap()

            self.minimap_dock = QDockWidget("Minimap", self)
            self.minimap_dock.setObjectName("MinimapDock")
            self.minimap_dock.setWidget(self.minimap)
            self.minimap_dock.setMinimumWidth(80)
            self.minimap_dock.setMaximumWidth(200)
            self.addDockWidget(Qt.RightDockWidgetArea, self.minimap_dock)
        except Exception as e:
            print(f"[MainWindow] Minimap 加载失败: {e}")
            self.minimap = None
            self.minimap_dock = None

    def _build_panel_gsearch(self):
        """构造全局搜索面板"""
        try:
            from ui.global_search_panel import GlobalSearchPanel
            self.gsearch = GlobalSearchPanel(self)
            self.gsearch.setObjectName("GlobalSearchPanel")
            self.gsearch.match_activated.connect(
                self._on_search_match_activated
            )
            # P2-C5: 连接 replace_requested
            # 原实现只连 match_activated，"全部替换"按钮点了没反应。
            # P0-3: 信号现携带第 4 个参数（SearchOptions）——
            # 面板勾选的"正则/大小写/全词/转义/多行"必须传到替换端，
            # 否则正则搜索会按字面量替换（详见 _on_global_replace）。
            self.gsearch.replace_requested.connect(
                self._on_global_replace
            )
            self.addDockWidget(Qt.BottomDockWidgetArea, self.gsearch)
            self.gsearch.hide()
        except Exception as e:
            print(f"[MainWindow] GlobalSearchPanel 加载失败: {e}")
            self.gsearch = None

    def _build_panel_problems(self):
        """构造问题面板（显示 LSP 诊断）

        背景（消费者/生产者缺口）：
            `ui/problems_panel.py` 实现了完整 UI 且会从
            `core.problems.get_problem_manager()` 读取问题，但
            `set_file_problems()` 原先**全仓零调用** —— 面板挂上去也永远
            空白。生产者已在 `core/editor.py::_publish_problems` 补上
            （`_on_lsp_diagnostics` 尾部），这里把面板接进视图。
        """
        try:
            from ui.problems_panel import ProblemsPanel
            self.problems = ProblemsPanel(self)
            self.problems.setObjectName("ProblemsPanel")
            self.addDockWidget(Qt.BottomDockWidgetArea, self.problems)
            self.problems.hide()
        except Exception as e:
            print(f"[MainWindow] ProblemsPanel 加载失败: {e}")
            self.problems = None

    def _build_panel_console(self):
        """构造 Python 控制台面板"""
        try:
            from ui.python_console import PythonConsole
            self.console = PythonConsole(self)
            self.console.setObjectName("PythonConsole")
            self.addDockWidget(Qt.BottomDockWidgetArea, self.console)
            self.console.hide()
        except Exception as e:
            print(f"[MainWindow] PythonConsole 加载失败: {e}")
            self.console = None

    def _build_panel_plugins_panel(self):
        """构造插件面板"""
        try:
            from ui.plugins_panel import PluginsPanel
            # plugin_manager 稍后才创建，先创建面板，之后设置
            self.plugins_panel = PluginsPanel(
                main_window=self,
                plugin_manager=None,
            )
            self.plugins_panel.setObjectName("PluginsPanel")
            self.addDockWidget(
                Qt.RightDockWidgetArea, self.plugins_panel
            )
            self.plugins_panel.hide()
        except Exception as e:
            print(f"[MainWindow] PluginsPanel 加载失败: {e}")
            self.plugins_panel = None

    def _build_panel_perf_monitor(self):
        """构造性能监控面板"""
        try:
            from ui.perf_monitor import PerfMonitor
            self.perf_monitor = PerfMonitor(self)
            self.perf_monitor.setObjectName("PerfMonitor")
            self.addDockWidget(
                Qt.BottomDockWidgetArea, self.perf_monitor
            )
            self.perf_monitor.hide()
        except Exception as e:
            print(f"[MainWindow] PerfMonitor 加载失败: {e}")
            self.perf_monitor = None

    def _build_panel_search_bar(self):
        """构造搜索栏"""
        try:
            from ui.panels import SearchBar
            self.search_bar = SearchBar(self)
            self.search_bar.setObjectName("SearchBar")
            self.addToolBar(Qt.BottomToolBarArea, self.search_bar)
            self.search_bar.hide()
        except Exception as e:
            print(f"[MainWindow] SearchBar 加载失败: {e}")
            self.search_bar = None

    def _suppress_panel_qss(self):
        """HC 模式：保存并清空面板自定义 QSS，让系统调色板生效"""
        try:
            from PyQt5.QtWidgets import QWidget
            if getattr(self, "_hc_saved_qss", None):
                return
            saved = []
            for w in self.findChildren(QWidget):
                if w is self:
                    continue
                qss = w.styleSheet()
                if qss:
                    saved.append((w, qss))
                    w.setStyleSheet("")
            self._hc_saved_qss = saved
        except Exception:
            pass

    def _restore_panel_qss(self):
        """退出 HC 模式：恢复面板原始 QSS"""
        try:
            for w, qss in getattr(self, "_hc_saved_qss", []) or []:
                try:
                    w.setStyleSheet(qss)
                except Exception:
                    continue
            self._hc_saved_qss = []
        except Exception:
            pass

    def _toggle_plugins_panel(self, checked):
        """切换插件面板"""
        if self._ensure_panel('plugins_panel') and self.plugins_panel:
            self.plugins_panel.setVisible(checked)

    def _toggle_problems_panel(self, checked):
        """切换问题面板（LSP 诊断列表）"""
        if self._ensure_panel('problems') and self.problems:
            self.problems.setVisible(checked)

    def _show_plugins_panel(self):
        """显示插件管理面板"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel('plugins_panel')
            if self.plugins_panel:
                self.plugins_panel.show()
                self.plugins_panel.raise_()
                if hasattr(self.plugins_panel, 'refresh'):
                    self.plugins_panel.refresh()
        except Exception as e:
            self._show_error("插件面板失败", str(e))
