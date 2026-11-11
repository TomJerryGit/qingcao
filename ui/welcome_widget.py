# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""欢迎页（v2.25 拆分：common/cards/recent/stats/主组件）。"""

from ui.welcome_cards import *  # noqa: F401,F403
from ui.welcome_recent import *  # noqa: F401,F403
from ui.welcome_stats import *  # noqa: F401,F403
from ui.welcome_widget_common import *  # noqa: F401,F403


class WelcomeWidget(QWidget):
    """
    欢迎页主控件。

    在没有打开任何标签时显示，包含:
    - 头部（Logo + 名称）
    - 快速操作
    - 最近文件
    - 每日技巧
    - 使用统计
    - 底部信息

    信号:
        new_file_requested(): 请求新建文件
        open_file_requested(): 请求打开文件
        open_folder_requested(str): 请求打开文件夹
        open_recent_file(str): 请求打开最近文件
        open_recent_project(str): 请求打开最近项目
        open_plugin_store(): 请求打开插件市场
        open_command_palette(): 请求打开命令面板
        close_requested(): 请求关闭欢迎页
    """

    new_file_requested = pyqtSignal()
    open_file_requested = pyqtSignal()
    open_folder_requested = pyqtSignal(str)
    open_recent_file = pyqtSignal(str)
    open_recent_project = pyqtSignal(str)
    open_plugin_store = pyqtSignal()
    open_command_palette = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, main_window=None, parent=None):
        """
        参数:
            main_window: 主窗口（用于加载统计等）
            parent: 父控件
        """
        super().__init__(parent)

        self.main_window = main_window

        # 设置背景
        #
        # 注意：这里与 content/scroll 都必须用**主题色**。
        # 此前是硬编码 #1e1e1e，导致浅色主题（如护眼）下出现
        # "深色欢迎页 + 浅色工具栏"的割裂观感。
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # 主动绑定"当前主题色"：
        #   `load_theme()` 在启动时只调用 apply_qss 应用全局样式表，**不会**
        #   遍历控件调用 refresh_theme；而本控件的样式全部是**内联**的，
        #   构造时若不绑定当前主题，就会用 C 的默认值（暗夜）渲染 ——
        #   这正是"护眼主题下欢迎页仍是深色"的直接原因。
        #
        # 注意：这里**不要**用宽 except 吞掉异常。之前写成
        # `except Exception: pass` 掩盖了 ORG_NAME 未定义导致的 NameError，
        # 结果"修复"看起来生效、实际完全没执行。
        self._bind_current_theme()

        # 构建 UI
        self._build_ui()

        # 构建完成后再应用样式：scroll/content 是在 _build_ui 里创建的
        self._apply_own_style()

        # 连接信号
        self._connect_signals()

        # 淡入动画
        self._setup_animation()

    def _bind_current_theme(self):
        """把当前生效主题的颜色绑定到模块级代理 C

        为什么构造时就要做：本控件的样式全是**内联**的
        （setStyleSheet 只在构建时求值一次），而启动路径
        `main.load_theme()` 只调用 `apply_qss` 应用全局样式表，
        **不会**遍历控件调用 `refresh_theme`。因此若构造时不绑定，
        就会用 C 的默认值（暗夜）渲染 —— 表现为"护眼主题下欢迎页
        仍是深色"。
        """
        from PyQt5.QtCore import QSettings

        from infrastructure.theme_loader import ThemeLoader

        theme = None
        # 1) 已加载过主题的实例（ThemeLoader 内部会缓存 current_theme）
        try:
            theme = getattr(ThemeLoader(), "current_theme", None)
        except Exception as e:  # pragma: no cover
            print(f"[Welcome] 读取当前主题失败: {e}")

        # 2) 回退：从设置里按名称加载
        if theme is None:
            try:
                name = QSettings(ORG_NAME, "Editor").value("theme_name", "", type=str)
                if name:
                    theme = ThemeLoader().load_by_name(name)
            except Exception as e:  # pragma: no cover
                print(f"[Welcome] 按名称加载主题失败: {e}")

        if theme is not None and getattr(theme, "colors", None) is not None:
            C.bind(theme.colors)

    def _apply_own_style(self):
        """把主题色应用到本控件及其直接子容器（供 refresh_theme 复用）"""
        self.setStyleSheet(f"""
            WelcomeWidget {{
                background-color: {C.window_bg};
            }}
        """)
        content = getattr(self, "_content_widget", None)
        if content is not None:
            content.setStyleSheet(f"background-color: {C.window_bg};")
        scroll = getattr(self, "_scroll_area", None)
        if scroll is not None:
            scroll.setStyleSheet(f"""
                QScrollArea {{
                    background-color: transparent;
                    border: none;
                }}
                QScrollBar:vertical {{
                    background-color: {C.scrollbar_bg};
                    width: 10px;
                    border-radius: 5px;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {C.scrollbar_fg};
                    border-radius: 5px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {C.scrollbar_hover};
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical {{
                    height: 0;
                }}
            """)

    def refresh_theme(self, theme=None):
        """主题切换回调（由 ThemeLoader.notify_widgets 调用）

        为什么需要：本控件大量使用**内联样式表**。内联样式不会随全局
        QSS 变化自动更新，`unpolish/polish` 也无法重算 —— 必须重新
        `setStyleSheet`。因此这里重新绑定主题色，再让各面板重放样式。

        修复背景：此前这些样式全部硬编码为暗色（#1e1e1e 等），
        导致浅色主题（如护眼）下出现"深色欢迎页 + 浅色工具栏"的割裂观感。
        """
        try:
            colors = getattr(theme, "colors", None) if theme else None
            if colors is not None:
                C.bind(colors)
            for panel in (
                getattr(self, "header", None),
                getattr(self, "quick_actions", None),
                getattr(self, "recent_files", None),
                getattr(self, "tips_panel", None),
                getattr(self, "stats_panel", None),
                getattr(self, "footer", None),
            ):
                fn = getattr(panel, "refresh_theme", None)
                if callable(fn):
                    try:
                        fn(theme)
                    except Exception:
                        pass
            self._apply_own_style()
        except Exception:
            pass

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        # 主布局：居中滚动
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # 滚动区域
        scroll = QScrollArea()
        self._scroll_area = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 样式由 _apply_own_style() 统一处理（主题相关）

        # 内容容器
        content = QWidget()
        self._content_widget = content
        # 样式由 _apply_own_style() 统一处理

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignTop)

        # 1. 头部
        self.header = WelcomeHeader()
        content_layout.addWidget(self.header)

        # 中央容器（限制最大宽度，居中显示）
        center_container = QWidget()
        center_container.setMaximumWidth(900)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(16)

        # 2. 快速操作
        self.quick_actions = QuickActionsPanel()
        center_layout.addWidget(self.quick_actions)

        # 3. 分栏：左侧最近文件 + 右侧技巧和统计
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # 左侧：最近文件
        left_column = QVBoxLayout()
        self.recent_files = RecentFilesList()
        left_column.addWidget(self.recent_files, 1)
        columns.addLayout(left_column, 3)

        # 右侧：技巧 + 统计
        right_column = QVBoxLayout()
        right_column.setSpacing(16)

        self.tips_panel = TipsPanel()
        right_column.addWidget(self.tips_panel)

        self.stats_panel = StatsPanel()
        right_column.addWidget(self.stats_panel)

        right_column.addStretch()

        columns.addLayout(right_column, 2)

        center_layout.addLayout(columns)

        # 将中央容器包装并居中
        center_wrapper = QHBoxLayout()
        center_wrapper.addStretch()
        center_wrapper.addWidget(center_container)
        center_wrapper.addStretch()

        content_layout.addLayout(center_wrapper)

        content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        # 4. 底部
        self.footer = WelcomeFooter()
        outer_layout.addWidget(self.footer)

    # --------------------------------------------------------
    # 信号连接
    # --------------------------------------------------------
    def _connect_signals(self):
        """连接信号"""
        # 快速操作
        self.quick_actions.action_triggered.connect(self._on_quick_action)

        # 最近文件
        self.recent_files.file_clicked.connect(self._on_recent_file_clicked)
        self.recent_files.project_clicked.connect(self._on_recent_project_clicked)

        # 底部链接
        self.footer.link_clicked.connect(self._on_link_clicked)

    # --------------------------------------------------------
    # 动画
    # --------------------------------------------------------
    def _setup_animation(self):
        """设置淡入动画"""
        try:
            effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(effect)

            self._animation = QPropertyAnimation(effect, b"opacity")
            self._animation.setDuration(400)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.setEasingCurve(QEasingCurve.OutCubic)
        except Exception:
            self._animation = None

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)

        # 播放动画
        if self._animation:
            self._animation.start()

        # 刷新数据
        self.refresh()

    # --------------------------------------------------------
    # 事件处理
    # --------------------------------------------------------
    def _on_quick_action(self, action_key: str):
        """快捷操作触发"""
        if action_key == "new_file":
            self.new_file_requested.emit()
        elif action_key == "open_file":
            self.open_file_requested.emit()
        elif action_key == "open_folder":
            from PyQt5.QtWidgets import QFileDialog

            folder = QFileDialog.getExistingDirectory(self, "打开文件夹")
            if folder:
                self.open_folder_requested.emit(folder)
        elif action_key == "recent":
            # 滚动到最近文件
            self.recent_files.setFocus()
        elif action_key == "plugin_store":
            self.open_plugin_store.emit()
        elif action_key == "command_palette":
            self.open_command_palette.emit()

    def _on_recent_file_clicked(self, filepath: str):
        """最近文件点击"""
        self.open_recent_file.emit(filepath)

    def _on_recent_project_clicked(self, project_path: str):
        """最近项目点击"""
        self.open_recent_project.emit(project_path)

    def _on_link_clicked(self, url: str):
        """链接点击"""
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception:
            pass

    # --------------------------------------------------------
    # 数据刷新
    # --------------------------------------------------------
    def refresh(self):
        """刷新欢迎页数据"""
        try:
            self.recent_files.refresh()
            self.stats_panel.refresh()
        except Exception as e:
            print(f"[WelcomeWidget] 刷新失败: {e}")

    def update_stats(self):
        """更新统计"""
        self.stats_panel.refresh()

    def next_tip(self):
        """显示下一条技巧"""
        self.tips_panel._load_tip()

    # --------------------------------------------------------
    # 键盘导航
    # --------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        """键盘事件"""
        key = event.key()

        # 数字键 1-6 触发快捷操作
        if Qt.Key_1 <= key <= Qt.Key_6:
            index = key - Qt.Key_1
            if 0 <= index < len(QUICK_ACTIONS):
                _, _, _, action_key = QUICK_ACTIONS[index]
                self._on_quick_action(action_key)
                event.accept()
                return

        # Ctrl+N / Ctrl+O
        if event.modifiers() & Qt.ControlModifier:
            if key == Qt.Key_N:
                self.new_file_requested.emit()
                event.accept()
                return
            elif key == Qt.Key_O:
                self.open_file_requested.emit()
                event.accept()
                return

        super().keyPressEvent(event)

    # --------------------------------------------------------
    # 焦点
    # --------------------------------------------------------
    def setFocus(self):
        """设置焦点"""
        super().setFocus()
        # 聚焦到最近文件列表
        try:
            self.recent_files.list_widget.setFocus()
        except Exception:
            pass

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出欢迎页信息"""
        lines = ["WelcomeWidget", "=" * 60]
        lines.append(f"应用: {APP_NAME} v{APP_VERSION}")
        lines.append(f"标语: {APP_SLOGAN}")
        lines.append(f"作者: {AUTHOR}")
        lines.append(f"邮箱: {EMAIL}")
        lines.append(f"最近文件数: {self.recent_files.list_widget.count()}")
        lines.append(f"当前技巧: {self.tips_panel._current_tip[:50]}...")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<WelcomeWidget {APP_NAME} v{APP_VERSION}>"


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("WelcomeWidget 测试")
    win.resize(1100, 750)
    win.show()

    # 创建欢迎页
    welcome = WelcomeWidget()
    win.setCentralWidget(welcome)

    # 连接信号
    welcome.new_file_requested.connect(lambda: print("[信号] 新建文件"))
    welcome.open_file_requested.connect(lambda: print("[信号] 打开文件"))
    welcome.open_folder_requested.connect(lambda p: print(f"[信号] 打开文件夹: {p}"))
    welcome.open_recent_file.connect(lambda p: print(f"[信号] 打开最近文件: {p}"))
    welcome.open_recent_project.connect(lambda p: print(f"[信号] 打开最近项目: {p}"))
    welcome.open_plugin_store.connect(lambda: print("[信号] 打开插件市场"))
    welcome.open_command_palette.connect(lambda: print("[信号] 打开命令面板"))

    # 添加一些测试最近文件
    from PyQt5.QtCore import QSettings

    settings = QSettings("QingCao", "Editor")

    # 创建临时测试文件
    import tempfile

    tmp_dir = tempfile.mkdtemp(prefix="qingcao_welcome_test_")
    test_files = [
        os.path.join(tmp_dir, "main.py"),
        os.path.join(tmp_dir, "README.md"),
        os.path.join(tmp_dir, "config.json"),
    ]

    for f in test_files:
        with open(f, "w") as file:
            file.write("# test\n")

    settings.setValue("recent_files", test_files)
    welcome.refresh()

    print("=== WelcomeWidget 测试 ===")
    print(welcome.dump())
    print()

    # 测试快捷操作
    def test_actions():
        print("测试下一条技巧...")
        welcome.next_tip()

        print("测试刷新统计...")
        welcome.update_stats()

    QTimer.singleShot(2000, test_actions)

    # 清理并退出
    def cleanup_and_quit():
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)
        app.quit()

    QTimer.singleShot(5000, cleanup_and_quit)

    sys.exit(app.exec_())
