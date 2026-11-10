# main 目录自举：spec_from_file_location 加载时也能导入仓库包
import os as _os
import sys as _sys


_main_root = _os.path.dirname(_os.path.abspath(__file__))
if _main_root not in _sys.path:
    _sys.path.insert(0, _main_root)

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为青草编辑器的启动入口，包含：
- 国际化设置（core.i18n）
- 全局异常处理与崩溃上报（core.crash_reporter）
- 便携模式检测
- 启动画面
- 主窗口延迟加载
- 崩溃恢复检测（旧版 backup/autosave_*）
- 自动备份恢复（backup/autosave 目录）
- 首次启动向导（ui.first_run_wizard）
- 自动更新检查（core.updater）
- 遥测（core.telemetry）
- 主题加载（infrastructure.theme_loader）
- 日志轮转
- 命令行参数解析
- 会话恢复

修复记录:
- setup_locale: 拆分为 _detect_language + 加载逻辑，独立处理
  "PyQt5 缺失"与"core.i18n 导入失败"两类异常（P3-5）。
  之前两类异常混在同一个 try 中，PyQt5 缺失时回退路径会二次
  import PyQt5 而再次失败。
- setQuitOnLastWindowClosed: 从 False 改为 True（P0）。
  原值与 closeEvent 中未显式 quit() 的组合导致应用"关不掉"。
- deferred_init: 新增草稿恢复调用（P0-2）。生产者
  `core/document.py::_save_draft` 每 60 秒写 backup/drafts/*.draft，
  但读取端 `SessionManager.check_and_recover_drafts()` 原先**零调用点**
  —— 只写不读，崩溃后未保存正文 100% 丢失。现已接线（见
  `_render_recovered_drafts` / `_notify_draft_recovery`）。

待接线契约（P0-10：requirements.txt 承诺的"文件 → 导出 → PDF"）
--------------------------------------------------------------
`requirements.txt` 第 69-72 行声明"用于『文件 → 导出 → PDF』
（core.exporter）"，但 `core/exporter.py` 目前**全仓零引用**
（只在 `build.py` 的 hiddenimports 名单里出现），菜单里也没有"导出"项。
`core/exporter.py` 归 task-10，下面是**已确认可用**的调用契约，
接线时按此实现即可（`ui/main_window.py` 的菜单结构不在本次修复范围内）：

    from core.exporter import Exporter

    # 1) 取当前编辑器正文与元信息
    proxy = self.tabs.current_proxy()              # EditorProxy
    text  = proxy.sc.text()                        # 真实字符文本（str）
    doc   = proxy.document                         # core.document.Document
    path  = getattr(doc, 'filepath', '') or ''
    title = os.path.basename(path) or "未命名"
    language = getattr(doc, 'language', '') or "text"

    # 2) HTML（同步，返回 str；由调用方写文件）
    html = Exporter.to_html(text, title=title, language=language)
    #    写: open(out_path, 'w', encoding='utf-8').write(html)

    # 3) Markdown（同步，返回 str）
    md = Exporter.to_markdown(text, title=title, language=language)

    # 4) PDF（同步，返回 (ok: bool, message: str)；缺 reportlab 时
    #    ok=False 且 message 为 "需要安装 reportlab: pip install reportlab"）
    ok, msg = Exporter.to_pdf(text, out_path, title=title)
    if not ok:
        QMessageBox.warning(self, "PDF 导出失败", msg)

    # 5) 整个会话报告（配合 tabs.get_all_tabs_info()；注意其中的
    #    char_count 已在 P0-8 中改为**真实字符数**）
    report = Exporter.session_to_markdown(self.tabs.get_all_tabs_info())

建议的菜单接入点（不改现有菜单结构，新增一个"文件 → 导出"子菜单）:
    文件(&F) → 导出 → HTML... / Markdown... / PDF...
"""

import atexit
import datetime
import os
import shutil
import sys
import time
import traceback

from app.main_common import *  # noqa: E402,F401,F403
from app.main_helpers import *  # noqa: E402,F401,F403
from app.main_helpers import CRASH_LOG  # noqa: E402,F401
from version import __version__  # noqa: E402,F401


def main(argv=None):
    from app.main_run import main as _run

    return _run(argv) if argv is not None else _run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断，退出。")
        sys.exit(130)
    except Exception:
        # 最后的防线
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            with open(CRASH_LOG, "a", encoding="utf-8") as f:
                f.write(f"\n{'=' * 70}\n")
                f.write(f"启动失败: {datetime.datetime.now()}\n")
                f.write(tb)
                f.write(f"{'=' * 70}\n")
        except Exception:
            pass
        sys.exit(1)
