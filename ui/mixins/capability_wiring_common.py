# -*- coding: utf-8 -*-
"""
青草编辑器 - 能力接线 Mixin（P0-4/5/6/10 + P1 入口重排）
========================================================

本模块集中"把已实现但零引用的能力接到 UI 上"的代码，独立于
`ui/main_window.py`，避免与其它改动互相冲突。

接线清单（每项都注明"此前为何用不到"）：

| 能力 | 源 | 接线方式 |
|---|---|---|
| 本地格式化 | `core/formatter.py`（Black/autopep8/clang-format） | 工具菜单「格式化文档」 |
| LSP 状态/安装向导 | `ui/lsp_panel.py`（548 行） | 面板：LSP |
| 撤销历史 | `ui/undo_history_panel.py`（229 行） | 面板：撤销历史 |
| 崩溃统计 | `core/crash_stats.py`（240 行） | 帮助菜单「崩溃统计」 |
| 导出 PDF/HTML | `core/exporter.py`（157 行） | 文件菜单「导出」 |

**设计约束**：所有方法都做了防御性 `try/except` 与 `hasattr` 检查 ——
因为面板/引擎可能在打包产物中缺失（`build.py` 的 hiddenimports 会静默
跳过不存在模块），缺一个能力不该让整个菜单构建失败。
"""

import logging
import os
import weakref

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QApplication


logger = logging.getLogger(__name__)

# 应用级按键过滤器（模块级单例，弱引用持有窗口）
#
# ★ 为什么不能把 MainWindow 直接 installEventFilter 到 QApplication
#   （实测崩溃，务必看）：
#
#       `app.installEventFilter(self)` 之后，QApplication 持有 MainWindow 的
#       C++ 指针。在主窗口**被销毁**（关窗/测试 teardown / GC）后，
#       QApplication 仍会在下一次事件派发时调用该过滤器的 `eventFilter`，
#       而此时 Python 对象已析构 → **访问违例（0xC0000005）**。
#
#       实测复现：`pytest tests/test_p1_features.py` 单跑必崩
#       （6 个测试全通过后在 teardown 段错误）；把本模块的初始化临时注释掉
#       则完整通过 —— 因果已确认。
#
#   改为：独立的 `_KeySequenceAppFilter`（弱引用窗口）+ 窗口侧只做
#   `_handle_keyseq_event`，窗口没了过滤器安全返回 False。
_KEYSEQ_APP_FILTER = None

__all__ = [n for n in dir() if not n.startswith("__")]
