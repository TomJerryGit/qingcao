#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 全量补丁一键执行
============================================================
应用所有 15 个补丁（P0/P1/P2）。

用法:
    python apply_all_patches.py --dry-run          # 预演
    python apply_all_patches.py                    # 应用
    python apply_all_patches.py --no-backup        # 不备份
    python apply_all_patches.py --only 1,3,5       # 只应用指定补丁
    python apply_all_patches.py --skip 8,14        # 跳过指定补丁

特性:
    - 幂等: 已修复的自动跳过
    - 备份: 首次修改前备份为 *.bak.allpatch
    - 验证: Python 文件修改后 compile 检查
    - 回滚: 语法失败自动还原
    - 报告: 每个补丁的状态
"""

import os
import re
import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Callable, Tuple, Optional

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.allpatch"


# ============================================================
# 输出辅助
# ============================================================
def print_header(title: str):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_ok(msg: str):
    print(f"  [OK]   {msg}")


def print_skip(msg: str):
    print(f"  [SKIP] {msg}")


def print_fail(msg: str):
    print(f"  [FAIL] {msg}")


def print_info(msg: str):
    print(f"  [INFO] {msg}")


# ============================================================
# Patch 类
# ============================================================
class Patch:
    """一个补丁：对单个文件的内容变换"""

    def __init__(self, pid: str, name: str, filepath: str,
                 apply_func: Callable[[str], Tuple[str, bool]],
                 marker: Optional[str] = None,
                 is_python: Optional[bool] = None):
        self.pid = pid
        self.name = name
        self.filepath = filepath
        self.apply_func = apply_func
        self.marker = marker
        # 自动判断是否为 Python 文件
        if is_python is None:
            is_python = filepath.endswith('.py')
        self.is_python = is_python

    def is_applied(self, content: str) -> bool:
        """幂等检测"""
        return bool(self.marker) and self.marker in content

    def apply(self, content: str) -> Tuple[str, bool]:
        return self.apply_func(content)


def replace_edit(pid: str, name: str, filepath: str,
                 old: str, new: str, marker: Optional[str] = None,
                 is_python: Optional[bool] = None) -> Patch:
    """构造一个简单替换补丁"""
    if marker is None:
        # 用 new 的前 60 字符作为幂等标记
        marker = new.strip().split('\n')[0][:60]

    def apply_func(content: str) -> Tuple[str, bool]:
        if old not in content:
            raise ValueError(f"锚点未找到（补丁 {pid}: {name}）")
        if content.count(old) > 1:
            raise ValueError(f"锚点重复出现 >1 次（补丁 {pid}: {name}）")
        return content.replace(old, new, 1), True

    return Patch(pid, name, filepath, apply_func, marker, is_python)


def func_edit(pid: str, name: str, filepath: str,
              apply_func: Callable[[str], Tuple[str, bool]],
              marker: Optional[str] = None,
              is_python: Optional[bool] = None) -> Patch:
    """构造一个函数式补丁"""
    return Patch(pid, name, filepath, apply_func, marker, is_python)


# ============================================================
# 补丁定义
# ============================================================
def build_patches() -> List[Patch]:
    patches: List[Patch] = []

    # --------------------------------------------------------
    # 补丁 1: command_palette 主题访问
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="1",
        name="CommandPalette 主题访问修复",
        filepath="ui/command_palette.py",
        old="""                    if 'qss' in theme:
                        win.setStyleSheet(theme['qss'])""",
        new="""                    qss = getattr(theme, 'qss', '')
                    if qss:
                        win.setStyleSheet(qss)""",
    ))

    # --------------------------------------------------------
    # 补丁 2: README.md 尾部污染清理 + 代码块闭合
    # --------------------------------------------------------
    def fix_readme(content: str) -> Tuple[str, bool]:
        changed = False
        # 定位 "变更摘要" 起始行，截断
        for marker in ("\n变更摘要", "\n## 变更摘要",
                       "\n检查清单", "\n## 检查清单"):
            idx = content.find(marker)
            if idx >= 0:
                content = content[:idx].rstrip() + "\n"
                changed = True
                break

        # 检查 ``` 配对（行首）
        fence_count = len(re.findall(r'^```', content, re.MULTILINE))
        if fence_count % 2 == 1:
            # 追加未闭合的 ````
            content += "\n```\n"
            changed = True

        return content, changed

    patches.append(func_edit(
        pid="2",
        name="README.md 清理",
        filepath="README.md",
        apply_func=fix_readme,
        marker="青草枯荣，野火重生",
        is_python=False,
    ))

    # --------------------------------------------------------
    # 补丁 3: build.py 移除 core.search_worker
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="3",
        name="build.py 移除 core.search_worker",
        filepath="build.py",
        old="""        'core.project', 'core.search', 'core.search_worker',""",
        new="""        'core.project', 'core.search',""",
    ))

    # --------------------------------------------------------
    # 补丁 4a: directory_tree.py 添加缓存字段
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="4a",
        name="DirectoryTree 添加 Git 缓存字段",
        filepath="ui/directory_tree.py",
        old="""        # 文件系统监听
        self._watcher: Optional[QFileSystemWatcher] = None

        # 图标提供者
        self._icon_provider = QFileIconProvider()""",
        new="""        # 文件系统监听
        self._watcher: Optional[QFileSystemWatcher] = None

        # Git 状态缓存（P1-1 性能优化）
        self._git_root: Optional[str] = None
        self._git_status_cache: Dict[str, str] = {}
        self._git_cache_time: float = 0.0
        self._git_cache_ttl: float = 5.0

        # 图标提供者
        self._icon_provider = QFileIconProvider()""",
    ))

    # --------------------------------------------------------
    # 补丁 4b: directory_tree.py 替换 _get_git_status
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="4b",
        name="DirectoryTree._get_git_status 性能优化",
        filepath="ui/directory_tree.py",
        old="""    def _get_git_status(self, filepath: str) -> str:
        \"\"\"
        获取文件的 Git 状态。

        返回:
            单字符状态标识或空字符串
        \"\"\"
        try:
            # 查找 .git 目录
            dirpath = os.path.dirname(filepath) if os.path.isfile(filepath) else filepath
            git_root = None
            check_path = dirpath

            while check_path != os.path.dirname(check_path):
                if os.path.isdir(os.path.join(check_path, '.git')):
                    git_root = check_path
                    break
                check_path = os.path.dirname(check_path)

            if not git_root:
                return ''

            # 执行 git status
            result = subprocess.run(
                ['git', '-C', git_root, 'status', '--porcelain', '--', filepath],
                capture_output=True, text=True, timeout=2,
                encoding='utf-8', errors='replace'
            )

            if result.returncode == 0 and result.stdout.strip():
                # 取第一个字符作为状态
                status = result.stdout.strip()[:2]
                # 优先返回第二个字符（工作区状态），其次是第一个（暂存区状态）
                if len(status) >= 2:
                    if status[1] != ' ':
                        return status[1]
                    elif status[0] != ' ':
                        return status[0]
                return status[0]

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            pass

        return ''""",
        new="""    def _get_git_status(self, filepath: str) -> str:
        \"\"\"
        获取文件的 Git 状态（带缓存）。

        修复说明（P1-1）:
            原实现对每个文件独立调用 `git status`，
            一个包含 N 个文件的目录会启动 N 个 git 子进程。
            现改为一次性获取整个仓库状态并缓存 5 秒。
        \"\"\"
        try:
            git_root = self._find_git_root(filepath)
            if not git_root:
                return ''

            now = time.time()
            if (self._git_root == git_root and
                    now - self._git_cache_time < self._git_cache_ttl):
                return self._lookup_git_status(filepath, git_root)

            self._git_root = git_root
            self._git_status_cache = self._fetch_git_status(git_root)
            self._git_cache_time = now

            return self._lookup_git_status(filepath, git_root)
        except Exception:
            return ''

    def _find_git_root(self, filepath: str) -> Optional[str]:
        \"\"\"查找文件的 git 根目录\"\"\"
        try:
            dirpath = (os.path.dirname(filepath)
                       if os.path.isfile(filepath) else filepath)
            check_path = os.path.abspath(dirpath)
            while check_path != os.path.dirname(check_path):
                if os.path.isdir(os.path.join(check_path, '.git')):
                    return check_path
                check_path = os.path.dirname(check_path)
        except Exception:
            pass
        return None

    def _fetch_git_status(self, git_root: str) -> Dict[str, str]:
        \"\"\"一次性获取整个 git 仓库的状态\"\"\"
        try:
            result = subprocess.run(
                ['git', '-C', git_root, 'status', '--porcelain'],
                capture_output=True, text=True, timeout=5,
                encoding='utf-8', errors='replace'
            )
            if result.returncode != 0:
                return {}

            status_map: Dict[str, str] = {}
            for line in result.stdout.splitlines():
                if len(line) < 4:
                    continue
                status = line[:2]
                path = line[3:].strip()
                if ' -> ' in path:
                    path = path.split(' -> ')[-1]
                abs_path = os.path.normpath(
                    os.path.join(git_root, path)
                ).replace('\\\\', '/')
                if len(status) >= 2:
                    if status[1] != ' ':
                        status_map[abs_path] = status[1]
                    elif status[0] != ' ':
                        status_map[abs_path] = status[0]
            return status_map
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {}
        except Exception:
            return {}

    def _lookup_git_status(self, filepath: str, git_root: str) -> str:
        \"\"\"从缓存查询指定文件的 Git 状态\"\"\"
        try:
            abs_path = os.path.normpath(filepath).replace('\\\\', '/')
            return self._git_status_cache.get(abs_path, '')
        except Exception:
            return ''""",
    ))

    # --------------------------------------------------------
    # 补丁 5: editor_view.py SnippetManager 集成
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="5",
        name="EditorWidget._handle_tab 集成 SnippetManager",
        filepath="ui/editor_view.py",
        old="""        # 无选区，检查代码片段触发
        line, col = self.getCursorPosition()
        line_text = self.text(line)

        # 获取光标前的单词
        before = line_text[:col]
        # 提取最后一个单词
        word = ""
        for i in range(len(before) - 1, -1, -1):
            ch = before[i]
            if ch.isalnum() or ch == '_':
                word = ch + word
            else:
                break

        if word and word in self.proxy.SNIPPETS:
            try:
                self.proxy.expand_snippet(word)
                return True
            except Exception:
                pass

        return False""",
        new="""        # 无选区，检查代码片段触发
        line, col = self.getCursorPosition()
        line_text = self.text(line)

        # 获取光标前的单词
        before = line_text[:col]
        word = ""
        for i in range(len(before) - 1, -1, -1):
            ch = before[i]
            if ch.isalnum() or ch == '_':
                word = ch + word
            else:
                break

        if not word:
            return False

        # 修复说明（P1-4）: 优先查询用户片段 SnippetManager
        try:
            from core.snippets import get_snippet_manager
            mgr = get_snippet_manager()
            snippet = mgr.get(word)
            if snippet:
                body = snippet.body
                if isinstance(body, list):
                    body = '\\n'.join(body)
                if body:
                    word_len_bytes = len(word.encode('utf-8'))
                    cur = self.SendScintilla(
                        QsciScintilla.SCI_GETCURRENTPOS
                    )
                    self.SendScintilla(
                        QsciScintilla.SCI_SETSELECTIONSTART,
                        cur - word_len_bytes
                    )
                    self.SendScintilla(
                        QsciScintilla.SCI_SETSELECTIONEND, cur
                    )
                    self.SendScintilla(
                        QsciScintilla.SCI_REPLACESEL,
                        body.encode('utf-8')
                    )
                    return True
        except Exception as e:
            print(f"[EditorWidget] SnippetManager 触发失败: {e}")

        # 回退到内置片段
        if word in self.proxy.SNIPPETS:
            try:
                self.proxy.expand_snippet(word)
                return True
            except Exception:
                pass

        return False""",
    ))

    # --------------------------------------------------------
    # 补丁 6: main.py print → logger（多处，逐个替换）
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="6a",
        name="main.py deferred_init 起始 print",
        filepath="main.py",
        old="""    def deferred_init():
        \"\"\"延迟初始化非关键组件\"\"\"
        print(">>> [MAIN] deferred_init 开始", flush=True)""",
        new="""    def deferred_init():
        \"\"\"延迟初始化非关键组件\"\"\"
        logger.info("deferred_init 开始")""",
    ))

    patches.append(replace_edit(
        pid="6b",
        name="main.py restore_session print",
        filepath="main.py",
        old="""            if hasattr(window, 'restore_session'):
                print(">>> [MAIN] 调用 restore_session...", flush=True)
                try:
                    window.restore_session()
                    print(">>> [MAIN] restore_session 完成", flush=True)
                except Exception as e:
                    logger.error(f"会话恢复失败: {e}")""",
        new="""            if hasattr(window, 'restore_session'):
                logger.debug("调用 restore_session...")
                try:
                    window.restore_session()
                    logger.debug("restore_session 完成")
                except Exception as e:
                    logger.error(f"会话恢复失败: {e}")""",
    ))

    patches.append(replace_edit(
        pid="6c",
        name="main.py 更新检查 print",
        filepath="main.py",
        old="""                    checker.check_async()
                    print(">>> [MAIN] 已启动更新检查", flush=True)""",
        new="""                    checker.check_async()
                    logger.debug("已启动更新检查")""",
    ))

    patches.append(replace_edit(
        pid="6d",
        name="main.py 遥测 print",
        filepath="main.py",
        old="""                telemetry.record_app_start()
                print(">>> [MAIN] 遥测记录完成", flush=True)""",
        new="""                telemetry.record_app_start()
                logger.debug("遥测记录完成")""",
    ))

    patches.append(replace_edit(
        pid="6e",
        name="main.py deferred_init 结束 print",
        filepath="main.py",
        old="""            logger.info("延迟初始化完成")
            print(">>> [MAIN] deferred_init 全部完成", flush=True)""",
        new="""            logger.info("延迟初始化完成")""",
    ))

    patches.append(replace_edit(
        pid="6f",
        name="main.py 事件循环 print",
        filepath="main.py",
        old="""    print(">>> [MAIN] 即将进入 app.exec_()", flush=True)
    exit_code = app.exec_()
    print(f">>> [MAIN] app.exec_() 返回, exit_code={exit_code}", flush=True)""",
        new="""    logger.info("即将进入事件循环")
    exit_code = app.exec_()
    logger.info(f"事件循环结束，exit_code={exit_code}")""",
    ))

    # --------------------------------------------------------
    # 补丁 7: requirements.txt 移除 PyQt5-Qt5
    # --------------------------------------------------------
    def fix_requirements(content: str) -> Tuple[str, bool]:
        lines = content.splitlines()
        new_lines = []
        changed = False
        for line in lines:
            if line.strip().startswith("PyQt5-Qt5"):
                changed = True
                continue
            new_lines.append(line)
        if changed:
            return "\n".join(new_lines) + "\n", True
        return content, False

    patches.append(func_edit(
        pid="7",
        name="requirements.txt 移除 PyQt5-Qt5 锁",
        filepath="requirements.txt",
        apply_func=fix_requirements,
        marker="# 只锁 PyQt5 主包",
        is_python=False,
    ))

    # --------------------------------------------------------
    # 补丁 8: .gitignore 追加 crash.log
    # --------------------------------------------------------
    def fix_gitignore(content: str) -> Tuple[str, bool]:
        additions = [
            "",
            "# ---- 运行时产物 ----",
            "crash.log",
            "*.crash.log",
        ]
        missing = [a for a in additions if a and a not in content]
        if not missing:
            return content, False
        if not content.endswith("\n"):
            content += "\n"
        content += "\n".join(additions) + "\n"
        return content, True

    patches.append(func_edit(
        pid="8",
        name=".gitignore 追加 crash.log",
        filepath=".gitignore",
        apply_func=fix_gitignore,
        marker="# ---- 运行时产物 ----",
        is_python=False,
    ))

    # --------------------------------------------------------
    # 补丁 9: app/menus.py DEPRECATED 标记
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="9",
        name="app/menus.py 标记 DEPRECATED",
        filepath="app/menus.py",
        old="""#!/usr/bin/env python
# -*- coding: utf-8 -*-
\"\"\"
青草编辑器 (QingCao Editor)""",
        new="""#!/usr/bin/env python
# -*- coding: utf-8 -*-
\"\"\"
[DEPRECATED] 本模块已被 ui/main_window.py 的 _build_menus 取代。

青草编辑器 (QingCao Editor)""",
    ))

    # --------------------------------------------------------
    # 补丁 10: main_window.py closeEvent 重入保护
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="10a",
        name="main_window.py 添加 _closing 标志",
        filepath="ui/main_window.py",
        old="""        self.plugin_loader = None
        self.plugin_manager = None

        # 偏好设置""",
        new="""        self.plugin_loader = None
        self.plugin_manager = None

        # 关闭标志（避免 closeEvent 重入）
        self._closing = False

        # 偏好设置""",
    ))

    patches.append(replace_edit(
        pid="10b",
        name="main_window.py closeEvent 重入保护",
        filepath="ui/main_window.py",
        old="""    def closeEvent(self, event):
        \"\"\"
        关闭事件。

        修复说明（P0）:
            - 原实现仅调用 event.accept()，依赖 main.py 中的
              setQuitOnLastWindowClosed(True) 退出事件循环。
            - 这里额外显式调用 QApplication.quit()（双保险），
              以覆盖"关闭主窗口时仍有其他 QDialog/子窗口存活"的
              边缘场景，确保事件循环一定能退出。
        \"\"\"
        try:
            # 检查未保存文件
            modified = []""",
        new="""    def closeEvent(self, event):
        \"\"\"
        关闭事件。

        修复说明:
            - 增加 _closing 标志，避免 closeEvent 重入
              （quit() 触发其他顶层窗口关闭时可能再次调用）。
            - 保留双保险：event.accept() + app.quit()。
        \"\"\"
        if getattr(self, '_closing', False):
            event.accept()
            return

        self._closing = True

        try:
            # 检查未保存文件
            modified = []""",
    ))

    # --------------------------------------------------------
    # 补丁 11: lsp_panel.py 一次性信号连接
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="11",
        name="LspPanel 一次性信号连接",
        filepath="ui/lsp_panel.py",
        old="""        # 避免重复连接
        try:
            self.installer.install_finished.disconnect()
        except Exception:
            pass

        self.installer.install_started.connect(on_started)
        self.installer.install_progress.connect(on_progress)
        self.installer.install_finished.connect(on_finished)

        self.installer.install_async(language)""",
        new="""        # 修复说明（P2-4）: 原实现 disconnect() 不带参数会断开
        # 所有订阅者。现改为一次性连接，成功/失败后自动清理。
        def _one_shot_finished(lang, success, msg):
            for signal, slot in (
                (self.installer.install_started, on_started),
                (self.installer.install_progress, on_progress),
                (self.installer.install_finished, _one_shot_finished),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            on_finished(lang, success, msg)

        self.installer.install_started.connect(on_started)
        self.installer.install_progress.connect(on_progress)
        self.installer.install_finished.connect(_one_shot_finished)

        self.installer.install_async(language)""",
    ))

    # --------------------------------------------------------
    # 补丁 12: main_window.py _goto_line_dialog SCI API
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="12",
        name="main_window.py _goto_line_dialog 统一 SCI API",
        filepath="ui/main_window.py",
        old="""            total = proxy.sc.lines()
            line, ok = QInputDialog.getInt(
                self, "跳转到行", "行号:",
                1, 1, total
            )""",
        new="""            total = proxy.sc.SendScintilla(
                proxy.sc.SCI_GETLINECOUNT
            )
            if total <= 0:
                total = 1
            line, ok = QInputDialog.getInt(
                self, "跳转到行", "行号:",
                1, 1, total
            )""",
    ))

    # --------------------------------------------------------
    # 补丁 13: welcome_widget.py 事件订阅
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="13",
        name="RecentFilesList 事件订阅",
        filepath="ui/welcome_widget.py",
        old="""    def __init__(self, parent=None):
        super().__init__(parent)

        self._settings = QSettings("QingCao", "Editor")

        self._build_ui()
        self._load_recent()""",
        new="""    def __init__(self, parent=None):
        super().__init__(parent)

        self._settings = QSettings("QingCao", "Editor")

        self._build_ui()
        self._load_recent()

        # 修复说明（P2-2）: 订阅文件事件自动刷新最近列表
        try:
            from app.event_bus import bus
            bus.file_opened.connect(self._on_file_event)
            bus.file_saved.connect(self._on_file_event)
        except Exception as e:
            print(f"[RecentFilesList] 事件订阅失败: {e}")

    def _on_file_event(self, event):
        \"\"\"文件事件回调 —— 刷新最近列表\"\"\"
        try:
            QTimer.singleShot(100, self._load_recent)
        except Exception:
            pass""",
    ))

    # --------------------------------------------------------
    # 补丁 14: docker-compose.yml 平台说明
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="14",
        name="docker-compose.yml 平台说明",
        filepath="docker-compose.yml",
        old="""version: '3.8'

services:
  app:""",
        new="""# ============================================================
# 青草编辑器 - 开发用 docker-compose
#
# 平台限制：
#   本配置使用 X11 socket 转发（/tmp/.X11-unix）显示 GUI，
#   仅适用于 Linux 主机。Windows / macOS 用户请直接运行
#   `python main.py`，或使用 WSL2（Windows）。
# ============================================================

version: '3.8'

services:
  app:""",
    ))

    # --------------------------------------------------------
    # 补丁 15: build.py clean_spec 参数
    # --------------------------------------------------------
    patches.append(replace_edit(
        pid="15a",
        name="build.py clean_build 保留 spec",
        filepath="build.py",
        old="""def clean_build(quiet: bool = False):
    \"\"\"清理旧的构建\"\"\"
    if not quiet:
        print_step("清理旧构建...")

    # 删除 dist / build
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            if not quiet:
                print(f"  移除: {d}")
            shutil.rmtree(d, ignore_errors=True)

    # 删除 spec
    if os.path.exists(SPEC_FILE):
        try:
            os.remove(SPEC_FILE)
        except Exception:
            pass""",
        new="""def clean_build(quiet: bool = False, clean_spec: bool = False):
    \"\"\"
    清理旧的构建。

    修复说明（P2-新-3）: 默认保留 .spec 文件，避免用户手动
    定制的内容被误删；只有 --clean-spec 时才删除。
    \"\"\"
    if not quiet:
        print_step("清理旧构建...")

    # 删除 dist / build
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            if not quiet:
                print(f"  移除: {d}")
            shutil.rmtree(d, ignore_errors=True)

    # 删除 spec（仅在显式指定时）
    if clean_spec and os.path.exists(SPEC_FILE):
        try:
            os.remove(SPEC_FILE)
            if not quiet:
                print(f"  移除: {SPEC_FILE}")
        except Exception:
            pass""",
    ))

    patches.append(replace_edit(
        pid="15b",
        name="build.py CLI --clean-spec",
        filepath="build.py",
        old="""    parser.add_argument('--clean', action='store_true',
                        help='打包前清理旧构建')
    parser.add_argument('--no-clean', action='store_true',
                        help='不清理旧构建')""",
        new="""    parser.add_argument('--clean', action='store_true',
                        help='打包前清理旧构建（保留 .spec）')
    parser.add_argument('--clean-spec', action='store_true',
                        help='同时删除生成的 .spec 文件')
    parser.add_argument('--no-clean', action='store_true',
                        help='不清理旧构建')""",
    ))

    patches.append(replace_edit(
        pid="15c",
        name="build.py 调用 clean_build 传参",
        filepath="build.py",
        old="""    if args.clean or not args.no_clean:
        print_header("清理")
        clean_build(quiet=args.quiet)
        print_ok("已清理")""",
        new="""    if args.clean or not args.no_clean:
        print_header("清理")
        clean_build(quiet=args.quiet, clean_spec=args.clean_spec)
        print_ok("已清理")""",
    ))

    return patches


# ============================================================
# 应用逻辑
# ============================================================
def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    """验证 Python 文件语法"""
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def apply_patches(patches: List[Patch],
                  dry_run: bool = False,
                  no_backup: bool = False) -> bool:
    """应用补丁列表（按文件分组）"""
    # 按文件分组
    by_file: dict = {}
    for p in patches:
        by_file.setdefault(p.filepath, []).append(p)

    total_applied = 0
    total_skipped = 0
    total_failed = 0

    for filepath, file_patches in by_file.items():
        print()
        print(f"【{filepath}】")

        path = ROOT / filepath
        if not path.exists():
            print_fail(f"文件不存在，跳过 {len(file_patches)} 个补丁")
            total_failed += len(file_patches)
            continue

        try:
            original_content = path.read_text(encoding='utf-8')
        except Exception as e:
            print_fail(f"读取失败: {e}")
            total_failed += len(file_patches)
            continue

        content = original_content
        file_changed = False

        for patch in file_patches:
            # 幂等检测
            if patch.is_applied(content):
                print_skip(f"补丁 {patch.pid}: {patch.name}（已应用）")
                total_skipped += 1
                continue

            if dry_run:
                print_info(f"[DRY-RUN] 补丁 {patch.pid}: {patch.name}")
                total_applied += 1
                continue

            try:
                new_content, changed = patch.apply(content)
                if not changed:
                    print_skip(f"补丁 {patch.pid}: {patch.name}（无需修改）")
                    total_skipped += 1
                    continue

                # Python 文件语法验证
                if patch.is_python:
                    ok, err = validate_python(new_content, filepath)
                    if not ok:
                        print_fail(
                            f"补丁 {patch.pid} 语法验证失败: {err}"
                        )
                        total_failed += 1
                        continue

                content = new_content
                file_changed = True
                print_ok(f"补丁 {patch.pid}: {patch.name}")
                total_applied += 1

            except ValueError as e:
                print_fail(f"补丁 {patch.pid}: {e}")
                total_failed += 1
            except Exception as e:
                print_fail(f"补丁 {patch.pid} 异常: {e}")
                traceback.print_exc()
                total_failed += 1

        # 写回
        if file_changed and not dry_run:
            # 备份
            if not no_backup:
                backup_path = Path(str(path) + BACKUP_SUFFIX)
                if not backup_path.exists():
                    try:
                        shutil.copy2(path, backup_path)
                        print_info(f"已备份: {backup_path.name}")
                    except Exception as e:
                        print_fail(f"备份失败: {e}")

            try:
                path.write_text(content, encoding='utf-8',
                                newline='\n')
            except Exception as e:
                print_fail(f"写回失败: {e}")
                # 尝试从备份恢复
                backup_path = Path(str(path) + BACKUP_SUFFIX)
                if backup_path.exists():
                    try:
                        shutil.copy2(backup_path, path)
                        print_info("已从备份还原")
                    except Exception:
                        pass

    # 汇总
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {total_applied}")
    print(f"  已跳过: {total_skipped}")
    print(f"  失败:   {total_failed}")

    if dry_run:
        print()
        print("⚠ DRY-RUN 模式：未实际修改文件")
        print("  运行 `python apply_all_patches.py` 应用")

    return total_failed == 0


# ============================================================
# 参数解析
# ============================================================
def parse_args():
    parser = argparse.ArgumentParser(
        description="青草编辑器 全量补丁一键执行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python apply_all_patches.py --dry-run     # 预演
  python apply_all_patches.py               # 应用所有
  python apply_all_patches.py --only 1,3,5  # 只应用 1,3,5
  python apply_all_patches.py --skip 8,14   # 跳过 8,14
        """,
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='预演，不修改文件')
    parser.add_argument('--no-backup', action='store_true',
                        help='不备份原文件')
    parser.add_argument('--only', type=str, default='',
                        help='只应用指定补丁（逗号分隔 id）')
    parser.add_argument('--skip', type=str, default='',
                        help='跳过指定补丁（逗号分隔 id）')
    return parser.parse_args()


def main():
    args = parse_args()

    print()
    print("=" * 60)
    print("青草编辑器 全量补丁执行")
    print("=" * 60)
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    patches = build_patches()

    # 过滤
    only_ids = set()
    if args.only:
        only_ids = {x.strip() for x in args.only.split(',') if x.strip()}
    skip_ids = set()
    if args.skip:
        skip_ids = {x.strip() for x in args.skip.split(',') if x.strip()}

    if only_ids:
        patches = [p for p in patches if p.pid in only_ids]
    if skip_ids:
        patches = [p for p in patches if p.pid not in skip_ids]

    print(f"  补丁数:   {len(patches)}")
    print()

    if not patches:
        print("无待应用补丁")
        return 0

    # 打印补丁列表
    for p in patches:
        print(f"  [{p.pid}] {p.filepath:35s} {p.name}")

    # 应用
    success = apply_patches(patches,
                            dry_run=args.dry_run,
                            no_backup=args.no_backup)

    if success and not args.dry_run:
        print()
        print("=" * 60)
        print("✓ 全部完成")
        print("=" * 60)
        print()
        print("下一步:")
        print("  1. 运行验证: python tools/verify_patches.py")
        print("  2. 测试启动: python main.py")
        print("  3. 清理备份: del /s *.bak.allpatch  (Windows)")
        print("               find . -name '*.bak.allpatch' -delete  (Linux/macOS)")

    return 0 if success else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        traceback.print_exc()
        sys.exit(1)