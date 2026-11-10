# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""状态/内联控件（v2.24 拆出）。"""

from ui.panels_common import *


class MessageBar(QFrame):
    """
    消息提示条。

    在编辑器顶部显示临时提示信息。
    """

    # 消息级别
    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setVisible(False)
        self.setFixedHeight(32)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedWidth(20)
        layout.addWidget(self.icon_label)

        # 消息
        self.message_label = QLabel()
        self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.message_label, 1)

        # 关闭按钮
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

    def _on_close(self):
        """关闭"""
        self.hide()
        self.closed.emit()

    def show_message(self, message: str, level: str = "info", auto_hide_ms: int = 3000):
        """
        显示消息。

        参数:
            message: 消息内容
            level: 级别（info/success/warning/error）
            auto_hide_ms: 自动隐藏延迟（0 表示不自动隐藏）
        """
        self.message_label.setText(message)

        # 根据级别设置样式
        if level == self.LEVEL_SUCCESS:
            bg = "#1e5f3f"
            fg = "#ffffff"
            icon = "✓"
        elif level == self.LEVEL_WARNING:
            bg = "#8f5f1e"
            fg = "#ffffff"
            icon = "⚠"
        elif level == self.LEVEL_ERROR:
            bg = "#8f1e1e"
            fg = "#ffffff"
            icon = "✕"
        else:
            bg = "#1e3f5f"
            fg = "#ffffff"
            icon = "ℹ"

        self.setStyleSheet(f"""
            MessageBar {{
                background-color: {bg};
                border: none;
                border-radius: 4px;
            }}
            MessageBar QLabel {{
                color: {fg};
                font-size: 12px;
            }}
            MessageBar QToolButton {{
                background-color: transparent;
                color: {fg};
                border: none;
                font-size: 12px;
            }}
            MessageBar QToolButton:hover {{
                background-color: rgba(255, 255, 255, 40);
                border-radius: 3px;
            }}
        """)

        self.icon_label.setText(icon)
        self.setVisible(True)

        # 自动隐藏
        if auto_hide_ms > 0:
            self._auto_hide_timer.start(auto_hide_ms)


# ============================================================
# 状态指示器
# ============================================================


class StatusIndicator(QLabel):
    """
    状态指示器。

    显示一个彩色圆点表示状态。
    """

    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_SUCCESS = "success"
    STATE_WARNING = "warning"
    STATE_ERROR = "error"

    def __init__(self, parent=None):
        super().__init__("●", parent)

        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignCenter)

        self._state = self.STATE_IDLE
        self._update_style()

    def set_state(self, state: str, tooltip: str = ""):
        """设置状态"""
        self._state = state
        if tooltip:
            self.setToolTip(tooltip)
        self._update_style()

    def _update_style(self):
        """更新样式"""
        colors = {
            self.STATE_IDLE: "#888888",
            self.STATE_RUNNING: "#f0ad4e",
            self.STATE_SUCCESS: "#7ec850",
            self.STATE_WARNING: "#f0ad4e",
            self.STATE_ERROR: "#f14c4c",
        }

        color = colors.get(self._state, "#888888")
        self.setStyleSheet(f"color: {color}; font-size: 14px;")


# ============================================================
# 内嵌搜索面板
# ============================================================


class InlineSearchPanel(QWidget):
    """
    内嵌搜索面板。

    可在编辑器内部显示的浮动搜索框。
    """

    search_requested = pyqtSignal(str, object)
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(36)
        self.setVisible(False)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # 输入框
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("搜索...")
        self.pattern_edit.setClearButtonEnabled(True)
        layout.addWidget(self.pattern_edit, 1)

        # 上一个
        prev_btn = QToolButton()
        prev_btn.setText("↑")
        prev_btn.setFixedSize(24, 24)
        prev_btn.clicked.connect(lambda: self._on_search(False))
        layout.addWidget(prev_btn)

        # 下一个
        next_btn = QToolButton()
        next_btn.setText("↓")
        next_btn.setFixedSize(24, 24)
        next_btn.clicked.connect(lambda: self._on_search(True))
        layout.addWidget(next_btn)

        # 关闭
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

        # 回车
        self.pattern_edit.returnPressed.connect(lambda: self._on_search(True))

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            InlineSearchPanel {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
        """)

    def _on_search(self, forward: bool):
        """执行搜索"""
        pattern = self.pattern_edit.text()
        if pattern:
            options = SearchOptions(pattern=pattern)
            self.search_requested.emit(pattern, options)

    def _on_close(self):
        """关闭"""
        self.setVisible(False)
        self.close_requested.emit()

    def show_and_focus(self):
        """显示并聚焦"""
        self.setVisible(True)
        self.pattern_edit.setFocus()
        self.pattern_edit.selectAll()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Escape:
            self._on_close()
            return
        super().keyPressEvent(event)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("Panels 测试")
    win.resize(900, 700)
    win.show()

    # 测试 SearchBar
    print("=== 测试 SearchBar ===")
    search_bar = SearchBar()
    win.addToolBar(Qt.BottomToolBarArea, search_bar)
    search_bar.show()

    print(search_bar.dump())
    print()

    # 测试状态指示器
    print("=== 测试 StatusIndicator ===")
    indicator = StatusIndicator()
    win.statusBar().addPermanentWidget(indicator)
    indicator.set_state("running", "处理中...")

    # 测试消息提示条
    print("=== 测试 MessageBar ===")
    msg_bar = MessageBar(win)
    win.statusBar().addWidget(msg_bar)

    def show_message():
        msg_bar.show_message("这是一条测试消息", "success", 3000)

    QTimer.singleShot(1000, show_message)

    # 测试对话框
    def test_dialogs():
        print()
        print("=== 测试 GotoLineDialog ===")
        dlg = GotoLineDialog(1000, 100)
        if dlg.exec():
            print(f"选中行: {dlg.get_line()}")

        print()
        print("=== 测试 EncodingDialog ===")
        dlg = EncodingDialog("utf-8")
        if dlg.exec():
            print(f"选中编码: {dlg.get_encoding()}")

        print()
        print("=== 测试 LineEndingDialog ===")
        dlg = LineEndingDialog("\n")
        if dlg.exec():
            print(f"选中行尾: {repr(dlg.get_eol())}")

        print()
        print("=== 测试 InputDialog ===")
        dlg = InputDialog("测试", "请输入内容:", "默认值")
        if dlg.exec():
            print(f"输入: {dlg.get_text()}")

        app.quit()

    # 3 秒后测试对话框
    QTimer.singleShot(3000, test_dialogs)

    sys.exit(app.exec())
