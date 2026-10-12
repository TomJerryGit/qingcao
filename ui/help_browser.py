# -*- coding: utf-8 -*-
"""帮助浏览器"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


# 内置帮助文档
HELP_TOPICS = {
    "快速入门": """
# 快速入门

## 基本操作
- **新建文件**: Ctrl+N
- **打开文件**: Ctrl+O
- **保存文件**: Ctrl+S
- **关闭标签**: Ctrl+W

## 编辑技巧
- **撤销/重做**: Ctrl+Z / Ctrl+Y
- **查找**: Ctrl+F
- **替换**: Ctrl+H
- **跳转到行**: Ctrl+G

## 高级功能
- **命令面板**: Ctrl+Shift+P
- **全局搜索**: Ctrl+Shift+F
- **Python 控制台**: Ctrl+`
- **文件对比**: 工具菜单
""",

    "快捷键": """
# 完整快捷键列表

## 文件
| 快捷键 | 功能 |
|--------|------|
| Ctrl+N | 新建 |
| Ctrl+O | 打开 |
| Ctrl+S | 保存 |
| Ctrl+Shift+S | 另存为 |
| Ctrl+W | 关闭标签 |
| Ctrl+Q | 退出 |

## 编辑
| 快捷键 | 功能 |
|--------|------|
| Ctrl+Z | 撤销 |
| Ctrl+Y | 重做 |
| Ctrl+X | 剪切 |
| Ctrl+C | 复制 |
| Ctrl+V | 粘贴 |
| Ctrl+A | 全选 |
| Ctrl+D | 选中下一个 |
| Ctrl+/ | 注释切换 |

## 查找
| 快捷键 | 功能 |
|--------|------|
| Ctrl+F | 查找 |
| Ctrl+H | 替换 |
| Ctrl+Shift+F | 全局搜索 |
| Ctrl+G | 跳转到行 |
| Ctrl+R | 符号跳转 |

## 视图
| 快捷键 | 功能 |
|--------|------|
| F11 | 无干扰模式 |
| Shift+F11 | 全屏 |
| Ctrl+= | 放大字体 |
| Ctrl+- | 缩小字体 |
| Ctrl+0 | 重置字体 |
| Alt+C | 列模式 |

## 工具
| 快捷键 | 功能 |
|--------|------|
| Ctrl+Shift+P | 命令面板 |
| Ctrl+P | 文件切换 |
| Ctrl+` | Python 控制台 |
| Ctrl+Shift+R | 录制宏 |
| Ctrl+Shift+M | 回放宏 |
| Ctrl+Shift+A | AI 助手 |
""",

    "插件开发": """
# 插件开发指南

## 目录结构
plugins/
└── my_plugin/
    ├── plugin.json      # 插件清单（必需）
    ├── __init__.py      # 插件入口（必需）
    └── README.md        # 插件说明（可选）
```

## 最小插件示例

```python
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "my_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "我的第一个插件"

    def on_activate(self):
        self.api.log("插件已激活")
        self.api.add_menu("工具/我的插件/执行", self.run)

    def on_deactivate(self):
        self.api.log("插件已卸载")

    def run(self):
        self.api.show_status("Hello from my plugin!")
```

## 权限声明

在 `plugin.json` 的 `permissions` 字段声明所需权限：

| 权限 | 说明 |
|------|------|
| filesystem | 读写本地文件 |
| network | 访问网络 |
| process | 执行系统命令 |
| clipboard | 读写剪贴板 |
| dialog | 显示对话框 |
| editor_read | 读取编辑器内容 |
| editor_write | 修改编辑器内容 |
| terminal | 使用集成终端 |

## 生命周期

- `on_activate()`: 插件激活时调用
- `on_deactivate()`: 插件卸载时调用

## 调试

修改插件代码后，重启编辑器即可加载新版本。
""",
}


# ============================================================
# 帮助浏览器对话框
# ============================================================
class HelpBrowser(QDialog):
    """帮助浏览器对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助")
        self.resize(800, 600)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧：主题列表
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("主题"))
        self.topic_list = QListWidget()
        for topic in HELP_TOPICS.keys():
            self.topic_list.addItem(QListWidgetItem(topic))
        self.topic_list.currentItemChanged.connect(
            self._on_topic_changed
        )
        left_layout.addWidget(self.topic_list)
        splitter.addWidget(left)

        # 右侧：内容
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.content_browser = QTextBrowser()
        self.content_browser.setOpenExternalLinks(True)
        right_layout.addWidget(self.content_browser)
        splitter.addWidget(right)

        splitter.setSizes([200, 600])
        layout.addWidget(splitter)

        # 底部：关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # 默认选中第一项
        if self.topic_list.count() > 0:
            self.topic_list.setCurrentRow(0)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; font-size: 12px; }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:selected { background-color: #094771; }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                padding: 12px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QSplitter::handle { background-color: #3c3c3c; }
        """)

    def _on_topic_changed(self, current, previous):
        """主题切换"""
        if not current:
            return
        topic = current.text()
        content = HELP_TOPICS.get(topic, "")
        try:
            self.content_browser.setMarkdown(content)
        except Exception:
            self.content_browser.setPlainText(content)

    def show_topic(self, topic: str):
        """显示指定主题"""
        for i in range(self.topic_list.count()):
            item = self.topic_list.item(i)
            if item.text() == topic:
                self.topic_list.setCurrentRow(i)
                break


def show_help(parent=None, topic: str = ""):
    """便捷函数：显示帮助"""
    dlg = HelpBrowser(parent)
    if topic:
        dlg.show_topic(topic)
    return dlg.exec_()
