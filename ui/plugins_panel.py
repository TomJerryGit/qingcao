# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
插件管理面板。

本模块由原 ui/plugins_panel.py 与 ui/plugins_widget.py 合并而成（P3-7）。
不再保留 PluginsWidget 类；如需嵌入到其他容器（如首选项页、欢迎页），
可使用 PluginsPanel(compact=True)。

功能:
- 列出所有插件（含状态、版本、权限、错误）
- 启用/禁用、重载、卸载单个插件
- 批量操作（全部启用/禁用、重新加载全部）
- 搜索过滤
- 分类筛选（按 category）
- 查看详情（权限、依赖、错误堆栈）
- 一键打开插件目录
- 事件总线联动
- 紧凑模式（嵌入到对话框等场景）

依赖:
- app.plugin_manager.PluginManager （高层 API）
- app.plugin_manager.PluginInfo    （数据类）
- app.plugin_manager.PluginState   （状态枚举）

作者: TomJerry
"""

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# 事件总线
try:
    from app.event_bus import StatusMessageEvent, bus
except ImportError:
    bus = None


# ============================================================
# 常量
# ============================================================
# 状态 → (图标, 颜色, 显示名)
STATE_DISPLAY = {
    'DISCOVERED':  ('○', '#888888', '已发现'),
    'LOADING':     ('◐', '#f0ad4e', '加载中'),
    'LOADED':      ('◑', '#f0ad4e', '已加载'),
    'ACTIVATED':   ('✓', '#7ec850', '已激活'),
    'ERROR':       ('✗', '#f14c4c', '错误'),
    'DISABLED':    ('⊘', '#888888', '已禁用'),
    'UNLOADED':    ('−', '#888888', '已卸载'),
    'UNKNOWN':     ('?', '#888888', '未知'),
}

# 分类显示
CATEGORY_NAMES = {
    'all': '全部',
    'editor': '编辑器增强',
    'language': '语言支持',
    'theme': '主题',
    'tool': '工具',
    'integration': '集成',
    'other': '其他',
}

# 树列索引（便于统一维护）
COL_ICON = 0
COL_NAME = 1
COL_VERSION = 2
COL_STATE = 3
COL_PERMISSIONS = 4
COL_COUNT = 5


# ============================================================
# 辅助函数
# ============================================================
def _format_permissions(permissions: Optional[List[str]],
                         max_show: int = 3) -> str:
    """
    将权限列表格式化为单行字符串。

    参数:
        permissions: 权限列表
        max_show: 最多显示的数量，超出则用 (+N) 表示

    返回:
        格式化后的字符串，如 "filesystem, network (+2)"
    """
    if not permissions:
        return '-'

    shown = permissions[:max_show]
    result = ', '.join(shown)

    extra = len(permissions) - max_show
    if extra > 0:
        result += f' (+{extra})'

    return result


# ============================================================
# 插件详情对话框
# ============================================================
class PluginDetailDialog(QDialog):
    """插件详情对话框"""

    def __init__(self, info: Any, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle(f"插件详情 - {info.display_name or info.name}")
        self.resize(600, 500)

        layout = QVBoxLayout(self)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(self._build_html())
        browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 12px;
                font-size: 13px;
            }
        """)
        layout.addWidget(browser, 1)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def _build_html(self) -> str:
        info = self.info
        parts = []

        parts.append("<style>")
        parts.append("""
            h2 { color: #7ec850; margin-top: 4px; }
            h3 { color: #7ec850; font-size: 14px;
                 border-bottom: 1px solid #3c3c3c;
                 padding-bottom: 4px; margin-top: 16px; }
            p { margin: 4px 0; }
            code { background-color: #2d2d2d; padding: 1px 4px;
                   border-radius: 3px; font-family: Consolas; }
            .error { color: #f14c4c; }
            .warn { color: #f0ad4e; }
            .ok { color: #7ec850; }
        """)
        parts.append("</style>")

        # 头部
        parts.append(f"<h2>{info.display_name or info.name}</h2>")
        parts.append(f"<p><code>{info.name}</code>  v{info.version}</p>")

        # 基本信息
        parts.append("<h3>基本信息</h3>")
        parts.append("<p>")
        if info.author:
            parts.append(f"作者: {info.author}<br>")
        if info.author_email:
            parts.append(f"邮箱: {info.author_email}<br>")
        parts.append(f"分类: {info.category}<br>")
        parts.append(f"类型: {info.type}<br>")
        parts.append(f"状态: {info.state}")
        parts.append("</p>")

        if info.description:
            parts.append(f"<p>{info.description}</p>")

        # 权限
        if info.permissions:
            parts.append("<h3>权限要求</h3>")
            parts.append("<ul>")
            for perm in info.permissions:
                parts.append(f"<li><code>{perm}</code></li>")
            parts.append("</ul>")

        # 依赖
        if info.dependencies or info.plugin_dependencies:
            parts.append("<h3>依赖</h3>")
            parts.append("<ul>")
            for dep in info.dependencies:
                parts.append(f"<li>Python: <code>{dep}</code></li>")
            for dep in info.plugin_dependencies:
                parts.append(f"<li>插件: <code>{dep}</code></li>")
            parts.append("</ul>")

        # 路径
        if info.directory:
            parts.append("<h3>路径</h3>")
            parts.append(f"<p><code>{info.directory}</code></p>")

        # 错误
        if info.error:
            parts.append("<h3>错误信息</h3>")
            parts.append(f"<p class='error'>{info.error}</p>")

        return "".join(parts)


# ============================================================
# 插件管理面板
# ============================================================
class PluginsPanel(QDockWidget):
    """
    插件管理面板（合并版，P3-7）。

    与 PluginManager 集成，提供 UI 友好的插件管理接口。

    两种用法:
        # 1) 主窗口停靠
        panel = PluginsPanel(main_window=self, plugin_manager=pm)
        self.addDockWidget(Qt.RightDockWidgetArea, panel)

        # 2) 嵌入到其他容器（取代原 PluginsWidget）
        widget = PluginsPanel(plugin_manager=pm, compact=True)
        layout.addWidget(widget)

    参数:
        main_window: 主窗口（用于弹对话框）
        plugin_manager: PluginManager 实例
        parent: 父控件
        compact: True 时进入紧凑模式：
                 - 隐藏 QDockWidget 标题栏
                 - 隐藏"全部启用/禁用"按钮
                 - 隐藏底部状态统计标签
                 - 隐藏插件树中的"权限"列
                 适合嵌入到空间有限的对话框

    信号:
        plugin_toggled(str, bool): 插件启用状态变更（名称, 是否启用）
        plugin_reloaded(str): 插件重载完成
        refresh_requested(): 请求刷新
    """

    plugin_toggled = pyqtSignal(str, bool)
    plugin_reloaded = pyqtSignal(str)
    refresh_requested = pyqtSignal()

    def __init__(self, main_window=None, plugin_manager=None,
                 parent=None, compact: bool = False):
        super().__init__("插件", parent or main_window)

        self.main_window = main_window
        self.plugin_manager = plugin_manager
        self._compact = bool(compact)

        self.setObjectName("PluginsPanel")
        self.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        )

        # 缓存
        self._all_infos: List[Any] = []
        self._filtered_infos: List[Any] = []
        self._current_category = "all"
        self._search_text = ""

        # 构建 UI
        self._build_ui()
        self._apply_style()

        # 紧凑模式：隐藏标题栏（方便嵌入）
        if self._compact:
            try:
                self.setTitleBarWidget(QWidget())
            except Exception:
                pass

        # 连接 PluginManager 信号（如果可用）
        self._connect_manager_signals()

        # 初始刷新
        QTimer.singleShot(100, self.refresh)

    # ========================================================
    # UI 构建
    # ========================================================
    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ---- 工具条 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        # 刷新
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("🔄")
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)

        # 全部启用（紧凑模式隐藏）
        self.enable_all_btn = QToolButton()
        self.enable_all_btn.setText("✓")
        self.enable_all_btn.setToolTip("全部启用")
        self.enable_all_btn.setFixedSize(24, 24)
        self.enable_all_btn.clicked.connect(self._enable_all)
        toolbar.addWidget(self.enable_all_btn)

        # 全部禁用（紧凑模式隐藏）
        self.disable_all_btn = QToolButton()
        self.disable_all_btn.setText("⊘")
        self.disable_all_btn.setToolTip("全部禁用")
        self.disable_all_btn.setFixedSize(24, 24)
        self.disable_all_btn.clicked.connect(self._disable_all)
        toolbar.addWidget(self.disable_all_btn)

        # 打开插件目录
        self.open_dir_btn = QToolButton()
        self.open_dir_btn.setText("📁")
        self.open_dir_btn.setToolTip("打开插件目录")
        self.open_dir_btn.setFixedSize(24, 24)
        self.open_dir_btn.clicked.connect(self._open_plugin_dir)
        toolbar.addWidget(self.open_dir_btn)

        toolbar.addStretch()

        # 状态统计（紧凑模式隐藏）
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self.stats_label)

        # 紧凑模式下隐藏批量操作与统计
        if self._compact:
            self.enable_all_btn.hide()
            self.disable_all_btn.hide()
            self.stats_label.hide()

        layout.addLayout(toolbar)

        # ---- 搜索 + 分类 ----
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索插件...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        filter_bar.addWidget(self.search_edit, 1)

        self.category_combo = QComboBox()
        for key, name in CATEGORY_NAMES.items():
            self.category_combo.addItem(name, key)
        self.category_combo.currentIndexChanged.connect(
            self._on_category_changed
        )
        filter_bar.addWidget(self.category_combo)

        layout.addLayout(filter_bar)

        # ---- 插件树（5 列，含权限） ----
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "插件", "版本", "状态", "权限"])
        self.tree.setColumnWidth(COL_ICON, 24)
        self.tree.setColumnWidth(COL_NAME, 160)
        self.tree.setColumnWidth(COL_VERSION, 60)
        self.tree.setColumnWidth(COL_STATE, 70)
        self.tree.setColumnWidth(COL_PERMISSIONS, 150)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        # 紧凑模式：隐藏权限列
        if self._compact:
            self.tree.setColumnHidden(COL_PERMISSIONS, True)

        layout.addWidget(self.tree, 1)

        self.setWidget(container)


    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            # 保存原始 QSS（只保存一次）
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget {
                background-color: #252526;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #007acc;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
                border: 1px solid #3c3c3c;
            }
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 4px;
                border-radius: 2px;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: white;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #888;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                padding: 4px;
                font-size: 11px;
            }
        """)

    # ========================================================
    # 信号连接
    # ========================================================
    def _connect_manager_signals(self):
        """连接 PluginManager 的信号"""
        if not self.plugin_manager:
            return

        try:
            pm = self.plugin_manager
            if hasattr(pm, 'plugins_changed'):
                pm.plugins_changed.connect(self.refresh)
            if hasattr(pm, 'plugin_loaded'):
                pm.plugin_loaded.connect(
                    lambda name: self.refresh()
                )
            if hasattr(pm, 'plugin_unloaded'):
                pm.plugin_unloaded.connect(
                    lambda name: self.refresh()
                )
            if hasattr(pm, 'plugin_error'):
                pm.plugin_error.connect(self._on_plugin_error)
        except Exception as e:
            print(f"[PluginsPanel] 信号连接失败: {e}")

    def _on_plugin_error(self, name: str, error: str):
        """插件错误回调"""
        self._show_status(f"插件 {name} 错误: {error}", "error")

    # ========================================================
    # 数据加载
    # ========================================================
    def refresh(self):
        """刷新插件列表"""
        self._all_infos = []

        if self.plugin_manager is not None:
            try:
                self._all_infos = self.plugin_manager.list_plugins()
            except Exception as e:
                print(f"[PluginsPanel] 获取插件列表失败: {e}")

        self._apply_filters()

    def _apply_filters(self):
        """应用过滤和分类"""
        infos = list(self._all_infos)

        # 分类过滤
        cat = self._current_category
        if cat != 'all':
            infos = [i for i in infos if i.category == cat]

        # 搜索过滤
        if self._search_text:
            keyword = self._search_text.lower()
            infos = [
                i for i in infos
                if (keyword in i.name.lower()
                    or keyword in (i.display_name or '').lower()
                    or keyword in (i.description or '').lower())
            ]

        self._filtered_infos = infos
        self._render()

    def _render(self):
        """渲染插件列表"""
        self.tree.setUpdatesEnabled(False)
        try:
            self.tree.clear()

            for info in self._filtered_infos:
                self._add_plugin_item(info)

            # 更新统计（紧凑模式下标签已隐藏，但保留更新以防模式切换）
            stats = self._compute_stats()
            self.stats_label.setText(
                f"{stats['active']}/{stats['total']} 激活 · "
                f"{stats['error']} 错误 · "
                f"{stats['disabled']} 禁用"
            )
        finally:
            self.tree.setUpdatesEnabled(True)

    def _add_plugin_item(self, info):
        """添加插件树项"""
        item = QTreeWidgetItem(self.tree)

        # 状态图标
        icon, color, display = STATE_DISPLAY.get(
            info.state, STATE_DISPLAY['UNKNOWN']
        )
        item.setText(COL_ICON, icon)
        item.setForeground(COL_ICON, QBrush(QColor(color)))

        # 名称
        item.setText(COL_NAME, info.display_name or info.name)
        item.setToolTip(COL_NAME, info.description or info.name)

        # 版本
        item.setText(COL_VERSION, info.version or "?")

        # 状态
        item.setText(COL_STATE, display)
        item.setForeground(COL_STATE, QBrush(QColor(color)))

        # 权限（P3-7：由 PluginsWidget 合并而来）
        perms_text = _format_permissions(info.permissions)
        item.setText(COL_PERMISSIONS, perms_text)
        if info.permissions:
            # 完整权限作为 tooltip
            item.setToolTip(
                COL_PERMISSIONS,
                "\n".join(f"• {p}" for p in info.permissions)
            )

        # 数据
        item.setData(0, Qt.UserRole, info)

        # 字体：激活的加粗
        if info.state == 'ACTIVATED':
            font = item.font(COL_NAME)
            font.setBold(True)
            item.setFont(COL_NAME, font)

        # 错误标记
        if info.state == 'ERROR' and info.error:
            item.setToolTip(COL_STATE, info.error)

    def _compute_stats(self) -> Dict[str, int]:
        """计算统计数据"""
        total = len(self._all_infos)
        active = sum(1 for i in self._all_infos
                     if i.state == 'ACTIVATED')
        error = sum(1 for i in self._all_infos
                    if i.state == 'ERROR')
        disabled = sum(1 for i in self._all_infos
                       if not i.is_enabled)
        return {
            'total': total,
            'active': active,
            'error': error,
            'disabled': disabled,
        }

    # ========================================================
    # 过滤交互
    # ========================================================
    def _on_search_changed(self, text: str):
        self._search_text = text.strip()
        self._apply_filters()

    def _on_category_changed(self, index: int):
        self._current_category = self.category_combo.currentData()
        self._apply_filters()

    # ========================================================
    # 插件操作
    # ========================================================
    def _get_current_info(self):
        """获取当前选中的插件信息"""
        item = self.tree.currentItem()
        if item:
            return item.data(0, Qt.UserRole)
        return None

    def get_selected_info(self):
        """
        公开接口：获取当前选中的插件信息。

        等价于 _get_current_info，供外部调用（合并自 PluginsWidget）。
        """
        return self._get_current_info()

    def _toggle_plugin(self, info):
        """切换插件启用状态"""
        if not self.plugin_manager:
            self._show_status("插件管理器不可用", "error")
            return

        try:
            if info.is_enabled:
                self.plugin_manager.disable_plugin(info.name, ask=True)
                self._show_status(f"已禁用: {info.name}", "info")
                self.plugin_toggled.emit(info.name, False)
            else:
                ok = self.plugin_manager.enable_plugin(info.name, ask=True)
                if ok:
                    self._show_status(f"已启用: {info.name}", "success")
                    self.plugin_toggled.emit(info.name, True)
                else:
                    self._show_status(f"启用失败: {info.name}", "error")

            QTimer.singleShot(200, self.refresh)
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))

    def _reload_plugin(self, info):
        """重载插件"""
        if not self.plugin_manager:
            return

        try:
            ok = self.plugin_manager.reload_plugin(info.name)
            if ok:
                self._show_status(f"已重载: {info.name}", "success")
                self.plugin_reloaded.emit(info.name)
            else:
                self._show_status(f"重载失败: {info.name}", "error")
            QTimer.singleShot(200, self.refresh)
        except Exception as e:
            QMessageBox.critical(self, "重载失败", str(e))

    def _unload_plugin(self, info):
        """卸载插件"""
        if not self.plugin_manager:
            return

        reply = QMessageBox.question(
            self, "卸载插件",
            f"确定要卸载插件 {info.name} 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        try:
            ok = self.plugin_manager.unload_plugin(info.name)
            if ok:
                self._show_status(f"已卸载: {info.name}", "success")
                QTimer.singleShot(200, self.refresh)
            else:
                self._show_status(f"卸载失败: {info.name}", "error")
        except Exception as e:
            QMessageBox.critical(self, "卸载失败", str(e))

    def _enable_all(self):
        """全部启用"""
        if not self.plugin_manager:
            return

        reply = QMessageBox.question(
            self, "全部启用",
            f"确定要启用所有 {len(self._all_infos)} 个插件吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.plugin_manager.enable_all()
            QTimer.singleShot(300, self.refresh)
            self._show_status("已全部启用", "success")
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))

    def _disable_all(self):
        """全部禁用"""
        if not self.plugin_manager:
            return

        reply = QMessageBox.question(
            self, "全部禁用",
            f"确定要禁用所有 {len(self._all_infos)} 个插件吗？\n\n"
            f"部分功能可能立即失效。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.plugin_manager.disable_all()
            QTimer.singleShot(300, self.refresh)
            self._show_status("已全部禁用", "info")
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))

    # ========================================================
    # 交互事件
    # ========================================================
    def _on_item_double_clicked(self, item, column):
        """双击项 —— 切换启用状态"""
        info = item.data(0, Qt.UserRole)
        if info:
            self._toggle_plugin(info)

    def _show_context_menu(self, pos):
        """右键菜单"""
        item = self.tree.itemAt(pos)
        if not item:
            # 空白区域
            menu = QMenu(self)
            menu.addAction("🔄 刷新", self.refresh)
            menu.addSeparator()
            menu.addAction("📁 打开插件目录", self._open_plugin_dir)
            menu.exec_(self.tree.viewport().mapToGlobal(pos))
            return

        info = item.data(0, Qt.UserRole)
        if not info:
            return

        menu = QMenu(self)

        # 启用/禁用
        if info.is_enabled:
            menu.addAction("⊘ 禁用", lambda: self._toggle_plugin(info))
        else:
            menu.addAction("✓ 启用", lambda: self._toggle_plugin(info))

        # 重载
        menu.addAction("🔄 重载", lambda: self._reload_plugin(info))

        menu.addSeparator()

        # 详情
        menu.addAction("ℹ 查看详情", lambda: self._show_detail(info))

        # 复制名称
        menu.addAction(
            "📋 复制插件名",
            lambda: QApplication.clipboard().setText(info.name)
        )

        menu.addSeparator()

        # 打开目录
        if info.directory and os.path.isdir(info.directory):
            menu.addAction(
                "📁 打开插件目录",
                lambda: self._open_dir(info.directory)
            )

        menu.addSeparator()

        # 卸载
        menu.addAction("🗑 卸载", lambda: self._unload_plugin(info))

        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _show_detail(self, info):
        """显示插件详情"""
        dlg = PluginDetailDialog(info, self)
        dlg.exec_()

    def _open_plugin_dir(self):
        """打开插件目录"""
        plugin_dir = None
        if self.plugin_manager:
            plugin_dir = getattr(self.plugin_manager, 'plugin_dir', None)
        if not plugin_dir:
            # 兜底：绝对解析，避免相对路径随工作目录变化
            from infrastructure.plugin_loader import resolve_plugin_dir
            plugin_dir = resolve_plugin_dir('plugins')

        if os.path.isdir(plugin_dir):
            self._open_dir(plugin_dir)
        else:
            self._show_status(f"插件目录不存在: {plugin_dir}", "warning")

    def _open_dir(self, path: str):
        """在文件管理器中打开目录"""
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            self._show_status(f"打开失败: {e}", "error")

    # ========================================================
    # 辅助
    # ========================================================
    def _show_status(self, message: str, level: str = "info"):
        """显示状态消息"""
        try:
            if bus:
                bus.emit_status(message, 3000, level)
        except Exception:
            pass

    def count(self) -> int:
        """
        公开接口：返回当前已知插件总数。

        合并自 PluginsWidget.count()。
        """
        return len(self._all_infos)

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        lines = ["PluginsPanel", "=" * 60]
        lines.append(f"插件总数: {len(self._all_infos)}")
        lines.append(f"筛选后: {len(self._filtered_infos)}")
        lines.append(f"当前分类: {self._current_category}")
        lines.append(f"搜索: {self._search_text!r}")
        lines.append(f"紧凑模式: {self._compact}")

        stats = self._compute_stats()
        for k, v in stats.items():
            lines.append(f"  {k}: {v}")

        return "\n".join(lines)

    def __repr__(self):
        return (f"<PluginsPanel total={len(self._all_infos)} "
                f"filtered={len(self._filtered_infos)} "
                f"compact={self._compact}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    win = QMainWindow()
    win.setWindowTitle("PluginsPanel 测试（合并版）")
    win.resize(700, 600)

    # 尝试创建 PluginManager
    pm = None
    try:
        from app.plugin_manager import PluginManager
        pm = PluginManager(main_window=win)
    except Exception as e:
        print(f"PluginManager 不可用: {e}")

    # 测试 1：停靠模式
    panel = PluginsPanel(main_window=win, plugin_manager=pm)
    win.addDockWidget(Qt.RightDockWidgetArea, panel)
    win.show()

    panel.refresh()

    print("=== 停靠模式 ===")
    print(panel.dump())
    print()

    # 测试 2：紧凑模式（作为普通 widget 嵌入）
    from PyQt5.QtWidgets import QDialog, QVBoxLayout

    dlg = QDialog(win)
    dlg.setWindowTitle("紧凑模式嵌入演示")
    dlg.resize(600, 500)

    layout = QVBoxLayout(dlg)
    compact_panel = PluginsPanel(
        main_window=win,
        plugin_manager=pm,
        compact=True,
    )
    layout.addWidget(compact_panel)
    dlg.show()

    print("=== 紧凑模式 ===")
    print(compact_panel.dump())
    print()

    QTimer.singleShot(3000, app.quit)
    sys.exit(app.exec_())