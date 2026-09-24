#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动补全两个被截断的文件
============================================================
避免手动复制粘贴（含三引号嵌套容易出错）。

用「行列表 + join」构建内容，不产生语法冲突。

用法：
    python tools\fix_truncated.py --dry-run
    python tools\fix_truncated.py
============================================================
"""

import sys
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_skip(m):
    print("  [SKIP] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


# ============================================================
# 补全内容 1: core/code_templates.py
# ============================================================
CODE_TEMPLATES_TAIL = "\n".join([
    "",
    "",
    "## 使用",
    "",
    "```bash",
    "python main.py",
    "```",
    "",
    "## 目录结构",
    "",
    "```",
    "project/",
    "├── main.py",
    "├── requirements.txt",
    "└── README.md",
    "```",
    "",
    "## 许可证",
    "",
    "MIT License",
    "''',",
    '        "placeholders": ["project_name", "description"],',
    "    },",
    "}",
    "",
    "",
    "# ============================================================",
    "# 辅助函数",
    "# ============================================================",
    "def get_template(name: str) -> dict:",
    '    """获取指定模板"""',
    "    return TEMPLATES.get(name, {})",
    "",
    "",
    "def list_templates() -> List[str]:",
    '    """列出所有模板名"""',
    "    return list(TEMPLATES.keys())",
    "",
    "",
    "def format_template(name: str, **kwargs) -> str:",
    '    """格式化模板"""',
    "    template = TEMPLATES.get(name)",
    "    if not template:",
    '        return ""',
    '    code = template.get("code", "")',
    "    try:",
    "        return code.format(**kwargs)",
    "    except (KeyError, IndexError, ValueError):",
    "        return code",
    "",
])


# ============================================================
# 补全内容 2: ui/help_browser.py
# ============================================================
HELP_BROWSER_TAIL = "\n".join([
    "",
    "plugins/",
    "└── my_plugin/",
    "    ├── plugin.json      # 插件清单（必需）",
    "    ├── __init__.py      # 插件入口（必需）",
    "    └── README.md        # 插件说明（可选）",
    "```",
    "",
    "## 最小插件示例",
    "",
    "```python",
    "from app.plugins import PluginBase",
    "",
    "",
    "class Plugin(PluginBase):",
    '    NAME = "my_plugin"',
    '    VERSION = "1.0.0"',
    '    DESCRIPTION = "我的第一个插件"',
    "",
    "    def on_activate(self):",
    '        self.api.log("插件已激活")',
    '        self.api.add_menu("工具/我的插件/执行", self.run)',
    "",
    "    def on_deactivate(self):",
    '        self.api.log("插件已卸载")',
    "",
    "    def run(self):",
    '        self.api.show_status("Hello from my plugin!")',
    "```",
    "",
    "## 权限声明",
    "",
    "在 `plugin.json` 的 `permissions` 字段声明所需权限：",
    "",
    "| 权限 | 说明 |",
    "|------|------|",
    "| filesystem | 读写本地文件 |",
    "| network | 访问网络 |",
    "| process | 执行系统命令 |",
    "| clipboard | 读写剪贴板 |",
    "| dialog | 显示对话框 |",
    "| editor_read | 读取编辑器内容 |",
    "| editor_write | 修改编辑器内容 |",
    "| terminal | 使用集成终端 |",
    "",
    "## 生命周期",
    "",
    "- `on_activate()`: 插件激活时调用",
    "- `on_deactivate()`: 插件卸载时调用",
    "",
    "## 调试",
    "",
    "修改插件代码后，重启编辑器即可加载新版本。",
    '""",',
    "}",
    "",
    "",
    "# ============================================================",
    "# 帮助浏览器对话框",
    "# ============================================================",
    "class HelpBrowser(QDialog):",
    '    """帮助浏览器对话框"""',
    "",
    "    def __init__(self, parent=None):",
    "        super().__init__(parent)",
    '        self.setWindowTitle("帮助")',
    "        self.resize(800, 600)",
    "        self._build_ui()",
    "        self._apply_style()",
    "",
    "    def _build_ui(self):",
    '        """构建 UI"""',
    "        layout = QVBoxLayout(self)",
    "",
    "        splitter = QSplitter(Qt.Horizontal)",
    "",
    "        # 左侧：主题列表",
    "        left = QWidget()",
    "        left_layout = QVBoxLayout(left)",
    "        left_layout.setContentsMargins(0, 0, 0, 0)",
    '        left_layout.addWidget(QLabel("主题"))',
    "        self.topic_list = QListWidget()",
    "        for topic in HELP_TOPICS.keys():",
    "            self.topic_list.addItem(QListWidgetItem(topic))",
    "        self.topic_list.currentItemChanged.connect(",
    "            self._on_topic_changed",
    "        )",
    "        left_layout.addWidget(self.topic_list)",
    "        splitter.addWidget(left)",
    "",
    "        # 右侧：内容",
    "        right = QWidget()",
    "        right_layout = QVBoxLayout(right)",
    "        right_layout.setContentsMargins(0, 0, 0, 0)",
    "        self.content_browser = QTextBrowser()",
    "        self.content_browser.setOpenExternalLinks(True)",
    "        right_layout.addWidget(self.content_browser)",
    "        splitter.addWidget(right)",
    "",
    "        splitter.setSizes([200, 600])",
    "        layout.addWidget(splitter)",
    "",
    "        # 底部：关闭按钮",
    "        btn_layout = QHBoxLayout()",
    "        btn_layout.addStretch()",
    '        close_btn = QPushButton("关闭")',
    "        close_btn.clicked.connect(self.accept)",
    "        btn_layout.addWidget(close_btn)",
    "        layout.addLayout(btn_layout)",
    "",
    "        # 默认选中第一项",
    "        if self.topic_list.count() > 0:",
    "            self.topic_list.setCurrentRow(0)",
    "",
    "    def _apply_style(self):",
    '        """应用样式"""',
    '        self.setStyleSheet("""',
    "            QDialog { background-color: #1e1e1e; color: #d4d4d4; }",
    "            QLabel { color: #d4d4d4; font-size: 12px; }",
    "            QListWidget {",
    "                background-color: #252526;",
    "                color: #d4d4d4;",
    "                border: 1px solid #3c3c3c;",
    "                font-size: 12px;",
    "                outline: none;",
    "            }",
    "            QListWidget::item { padding: 6px 8px; }",
    "            QListWidget::item:selected { background-color: #094771; }",
    "            QListWidget::item:hover { background-color: #2a2d2e; }",
    "            QTextBrowser {",
    "                background-color: #1e1e1e;",
    "                color: #d4d4d4;",
    "                border: 1px solid #3c3c3c;",
    "                padding: 12px;",
    "                font-size: 12px;",
    "            }",
    "            QPushButton {",
    "                background-color: #0e639c;",
    "                color: white;",
    "                border: none;",
    "                border-radius: 3px;",
    "                padding: 6px 14px;",
    "            }",
    "            QPushButton:hover { background-color: #1177bb; }",
    "            QSplitter::handle { background-color: #3c3c3c; }",
    '        """)',
    "",
    "    def _on_topic_changed(self, current, previous):",
    '        """主题切换"""',
    "        if not current:",
    "            return",
    "        topic = current.text()",
    '        content = HELP_TOPICS.get(topic, "")',
    "        try:",
    "            self.content_browser.setMarkdown(content)",
    "        except Exception:",
    "            self.content_browser.setPlainText(content)",
    "",
    "    def show_topic(self, topic: str):",
    '        """显示指定主题"""',
    "        for i in range(self.topic_list.count()):",
    "            item = self.topic_list.item(i)",
    "            if item.text() == topic:",
    "                self.topic_list.setCurrentRow(i)",
    "                break",
    "",
    "",
    'def show_help(parent=None, topic: str = ""):',
    '    """便捷函数：显示帮助"""',
    "    dlg = HelpBrowser(parent)",
    "    if topic:",
    "        dlg.show_topic(topic)",
    "    return dlg.exec_()",
    "",
])


# ============================================================
# 工具函数
# ============================================================
def validate_syntax(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            src = f.read()
        compile(src, str(path), 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def append_tail(path, tail, marker, description,
                dry_run=False, no_backup=False):
    """追加内容到文件末尾"""
    if not path.exists():
        print_fail(f"文件不存在: {path}")
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            current = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return False

    # 幂等：已补全则跳过
    if marker in current:
        print_skip(f"已补全，跳过: {description}")
        return False

    if dry_run:
        print_ok(f"[DRY-RUN] 会补全: {description}")
        print(f"           将追加 {len(tail)} 字符")
        return True

    # 备份
    if not no_backup:
        backup = path.with_suffix(path.suffix + ".bak.trunc")
        try:
            shutil.copy2(path, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_fail(f"备份失败: {e}")
            return False

    # 追加（统一 LF 换行）
    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(current)
            f.write(tail)
    except Exception as e:
        print_fail(f"写入失败: {e}")
        return False

    # 语法验证
    ok, err = validate_syntax(path)
    if not ok:
        print_fail(f"语法检查失败: {err}")
        if not no_backup:
            backup = path.with_suffix(path.suffix + ".bak.trunc")
            if backup.exists():
                shutil.copy2(backup, path)
                print_fail("已从备份还原")
        return False

    print_ok(f"已追加 {len(tail)} 字符，语法验证通过")
    return True


# ============================================================
# 主流程
# ============================================================
def main():
    dry_run = '--dry-run' in sys.argv
    no_backup = '--no-backup' in sys.argv

    print_header("补全被截断的文件")
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       {'DRY-RUN' if dry_run else '实际修复'}")

    fixed = 0

    # 补全 1
    print_header("补全 1/2: core/code_templates.py")
    if append_tail(
        ROOT / "core" / "code_templates.py",
        CODE_TEMPLATES_TAIL,
        marker="def format_template(name: str, **kwargs) -> str:",
        description="readme 模板 + 辅助函数",
        dry_run=dry_run, no_backup=no_backup,
    ):
        fixed += 1

    # 补全 2
    print_header("补全 2/2: ui/help_browser.py")
    if append_tail(
        ROOT / "ui" / "help_browser.py",
        HELP_BROWSER_TAIL,
        marker="class HelpBrowser(QDialog):",
        description="插件开发文档 + HelpBrowser 类",
        dry_run=dry_run, no_backup=no_backup,
    ):
        fixed += 1

    # 汇总
    print_header("汇总")
    print(f"  已补全: {fixed}")

    if dry_run:
        print()
        print("✓ DRY-RUN 完成")
        print("  运行 `python tools\\fix_truncated.py` 执行")
    elif fixed > 0:
        print()
        print("✓ 修复完成")
        print()
        print("  验证:")
        print("    python -c \"import py_compile; "
              "py_compile.compile('core/code_templates.py')\"")
        print("    python -c \"import py_compile; "
              "py_compile.compile('ui/help_browser.py')\"")
    else:
        print()
        print("✓ 无需修复")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)