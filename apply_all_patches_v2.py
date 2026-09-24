#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 全量补丁一键执行 (v2)
============================================================
修复 v1 的问题：
    - marker 改为"new 中独有的特征字符串"，避免误判
    - 移除 app/menus.py 补丁（文件可能不存在）
    - 增加详细的已应用/未应用诊断

用法:
    python apply_all_patches_v2.py --dry-run
    python apply_all_patches_v2.py
    python apply_all_patches_v2.py --force   # 忽略幂等检测，强制应用
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
    def __init__(self, pid, name, filepath, apply_func,
                 marker, is_python=None):
        self.pid = pid
        self.name = name
        self.filepath = filepath
        self.apply_func = apply_func
        self.marker = marker
        if is_python is None:
            is_python = filepath.endswith('.py')
        self.is_python = is_python

    def is_applied(self, content: str) -> bool:
        return bool(self.marker) and self.marker in content

    def apply(self, content: str) -> Tuple[str, bool]:
        return self.apply_func(content)


def replace_edit(pid, name, filepath, old, new,
                 marker=None, is_python=None) -> Patch:
    """
    构造替换补丁。

    marker 必须显式指定，且必须是 new 中独有的字符串。
    """
    if not marker:
        raise ValueError(f"补丁 {pid} 必须显式提供 marker")

    def apply_func(content):
        if old not in content:
            raise ValueError(f"锚点未找到（补丁 {pid}）")
        if content.count(old) > 1:
            raise ValueError(f"锚点重复（补丁 {pid}）")
        return content.replace(old, new, 1), True

    return Patch(pid, name, filepath, apply_func, marker, is_python)


def func_edit(pid, name, filepath, apply_func,
              marker, is_python=None) -> Patch:
    return Patch(pid, name, filepath, apply_func, marker, is_python)


# ============================================================
# 补丁定义 (v2)
# ============================================================
def build_patches() -> List[Patch]:
    patches = []

    # ---- 1: command_palette 主题访问 ----
    patches.append(replace_edit(
        pid="1",
        name="CommandPalette 主题访问修复",
        filepath="ui/command_palette.py",
        old="""                    if 'qss' in theme:
                        win.setStyleSheet(theme['qss'])""",
        new="""                    qss = getattr(theme, 'qss', '')
                    if qss:
                        win.setStyleSheet(qss)""",
        marker="qss = getattr(theme, 'qss', '')",
    ))

    # ---- 2: README 清理 ----
    def fix_readme(content):
        changed = False
        for marker in ("\n变更摘要", "\n## 变更摘要",
                       "\n检查清单", "\n## 检查清单"):
            idx = content.find(marker)
            if idx >= 0:
                content = content[:idx].rstrip() + "\n"
                changed = True
                break
        fence_count = len(re.findall(r'^```', content, re.MULTILINE))
        if fence_count % 2 == 1:
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

    # ---- 3: build.py 移除 core.search_worker ----
    patches.append(replace_edit(
        pid="3",
        name="build.py 移除 core.search_worker",
        filepath="build.py",
        old="""        'core.project', 'core.search', 'core.search_worker',""",
        new="""        'core.project', 'core.search',""",
        marker="""        'core.project', 'core.search',\n""",
    ))

    # ---- 4a: directory_tree 添加缓存字段 ----
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
        marker="_git_status_cache: Dict[str, str] = {}",
    ))

    # ---- 4b: directory_tree 替换 _get_git_status ----
    def apply_4b(content):
        """用正则替换整个 _get_git_status 方法"""
        # 找到方法范围
        pattern = re.compile(
            r'^(    def _get_git_status\(self, filepath: str\) -> str:.*?)'
            r'(?=^    def |^class |\Z)',
            re.MULTILINE | re.DOTALL,
        )
        m = pattern.search(content)
        if not m:
            raise ValueError("未找到 _get_git_status 方法")

        new_method = '''    def _get_git_status(self, filepath: str) -> str:
        """
        获取文件的 Git 状态（带缓存）。

        修复说明（P1-1）:
            原实现对每个文件独立调用 `git status`，
            一个包含 N 个文件的目录会启动 N 个 git 子进程。
            现改为一次性获取整个仓库状态并缓存 5 秒。
        """
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
        """查找文件的 git 根目录"""
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
        """一次性获取整个 git 仓库的状态"""
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
        """从缓存查询指定文件的 Git 状态"""
        try:
            abs_path = os.path.normpath(filepath).replace('\\\\', '/')
            return self._git_status_cache.get(abs_path, '')
        except Exception:
            return ''

'''
        return content[:m.start()] + new_method + content[m.end():], True

    patches.append(func_edit(
        pid="4b",
        name="DirectoryTree._get_git_status 性能优化",
        filepath="ui/directory_tree.py",
        apply_func=apply_4b,
        marker="def _fetch_git_status",
    ))

    # ---- 5: editor_view SnippetManager ----
    def apply_5(content):
        """替换 _handle_tab 方法体中的片段触发逻辑"""
        old_block = """        # 无选区，检查代码片段触发
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

        return False"""

        new_block = """        # 无选区，检查代码片段触发
        line, col = self.getCursorPosition()
        line_text = self.text(line)

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

        return False"""

        if old_block not in content:
            raise ValueError("未找到 _handle_tab 中的片段触发逻辑")
        return content.replace(old_block, new_block, 1), True

    patches.append(func_edit(
        pid="5",
        name="EditorWidget._handle_tab 集成 SnippetManager",
        filepath="ui/editor_view.py",
        apply_func=apply_5,
        marker="from core.snippets import get_snippet_manager",
    ))

    # ---- 6a-6f: main.py print → logger ----
    main_patches = [
        ("6a",
         """    def deferred_init():
        \"\"\"延迟初始化非关键组件\"\"\"
        print(">>> [MAIN] deferred_init 开始", flush=True)""",
         """    def deferred_init():
        \"\"\"延迟初始化非关键组件\"\"\"
        logger.info("deferred_init 开始")""",
         'logger.info("deferred_init 开始")'),
        ("6b",
         """            if hasattr(window, 'restore_session'):
                print(">>> [MAIN] 调用 restore_session...", flush=True)
                try:
                    window.restore_session()
                    print(">>> [MAIN] restore_session 完成", flush=True)
                except Exception as e:
                    logger.error(f"会话恢复失败: {e}")""",
         """            if hasattr(window, 'restore_session'):
                logger.debug("调用 restore_session...")
                try:
                    window.restore_session()
                    logger.debug("restore_session 完成")
                except Exception as e:
                    logger.error(f"会话恢复失败: {e}")""",
         'logger.debug("调用 restore_session...")'),
        ("6c",
         """                    checker.check_async()
                    print(">>> [MAIN] 已启动更新检查", flush=True)""",
         """                    checker.check_async()
                    logger.debug("已启动更新检查")""",
         'logger.debug("已启动更新检查")'),
        ("6d",
         """                telemetry.record_app_start()
                print(">>> [MAIN] 遥测记录完成", flush=True)""",
         """                telemetry.record_app_start()
                logger.debug("遥测记录完成")""",
         'logger.debug("遥测记录完成")'),
        ("6e",
         """            logger.info("延迟初始化完成")
            print(">>> [MAIN] deferred_init 全部完成", flush=True)""",
         """            logger.info("延迟初始化完成")""",
         'logger.info("延迟初始化完成")'),
        ("6f",
         """    print(">>> [MAIN] 即将进入 app.exec_()", flush=True)
    exit_code = app.exec_()
    print(f">>> [MAIN] app.exec_() 返回, exit_code={exit_code}", flush=True)""",
         """    logger.info("即将进入事件循环")
    exit_code = app.exec_()
    logger.info(f"事件循环结束，exit_code={exit_code}")""",
         'logger.info("即将进入事件循环")'),
    ]
    for pid, old, new, marker in main_patches:
        patches.append(replace_edit(
            pid=pid, name=f"main.py {pid}",
            filepath="main.py",
            old=old, new=new, marker=marker,
        ))

    # ---- 7: requirements.txt ----
    def fix_requirements(content):
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
        name="requirements.txt 移除 PyQt5-Qt5",
        filepath="requirements.txt",
        apply_func=fix_requirements,
        marker="PyQt5>=5.15.4,<5.16.0",
        is_python=False,
    ))

    # ---- 8: .gitignore ----
    def fix_gitignore(content):
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

    # ---- 10a: main_window 添加 _closing ----
    patches.append(replace_edit(
        pid="10a",
        name="main_window 添加 _closing",
        filepath="ui/main_window.py",
        old="""        self.plugin_loader = None
        self.plugin_manager = None

        # 偏好设置""",
        new="""        self.plugin_loader = None
        self.plugin_manager = None

        # 关闭标志（避免 closeEvent 重入）
        self._closing = False

        # 偏好设置""",
        marker="self._closing = False",
    ))

    # ---- 10b: main_window closeEvent ----
    patches.append(replace_edit(
        pid="10b",
        name="main_window closeEvent 重入保护",
        filepath="ui/main_window.py",
        old="""        try:
            # 检查未保存文件
            modified = []""",
        new="""        if getattr(self, '_closing', False):
            event.accept()
            return

        self._closing = True

        try:
            # 检查未保存文件
            modified = []""",
        marker="if getattr(self, '_closing', False):",
    ))

    # ---- 11: lsp_panel 一次性连接 ----
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
        marker="_one_shot_finished",
    ))

    # ---- 12: main_window _goto_line_dialog ----
    patches.append(replace_edit(
        pid="12",
        name="main_window _goto_line_dialog SCI API",
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
        marker="proxy.sc.SendScintilla(\n                proxy.sc.SCI_GETLINECOUNT",
    ))

    # ---- 13: welcome_widget 事件订阅 ----
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
        marker="bus.file_opened.connect(self._on_file_event)",
    ))

    # ---- 14: docker-compose ----
    patches.append(replace_edit(
        pid="14",
        name="docker-compose 平台说明",
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
        marker="平台限制：",
        is_python=False,
    ))

    # ---- 15a: build.py clean_build ----
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

    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            if not quiet:
                print(f"  移除: {d}")
            shutil.rmtree(d, ignore_errors=True)

    if clean_spec and os.path.exists(SPEC_FILE):
        try:
            os.remove(SPEC_FILE)
            if not quiet:
                print(f"  移除: {SPEC_FILE}")
        except Exception:
            pass""",
        marker="clean_spec: bool = False",
    ))

    # ---- 15b: build.py CLI 参数 ----
    patches.append(replace_edit(
        pid="15b",
        name="build.py CLI --clean-spec",
        filepath="build.py",
        old="""    parser.add_argument('--clean', action='store_true',
                        help='打包前清理旧构建')""",
        new="""    parser.add_argument('--clean', action='store_true',
                        help='打包前清理旧构建（保留 .spec）')
    parser.add_argument('--clean-spec', action='store_true',
                        help='同时删除生成的 .spec 文件')""",
        marker="'--clean-spec'",
    ))

    # ---- 15c: build.py 调用 ----
    patches.append(replace_edit(
        pid="15c",
        name="build.py 调用 clean_build",
        filepath="build.py",
        old="""    if args.clean or not args.no_clean:
        print_header("清理")
        clean_build(quiet=args.quiet)
        print_ok("已清理")""",
        new="""    if args.clean or not args.no_clean:
        print_header("清理")
        clean_build(quiet=args.quiet, clean_spec=args.clean_spec)
        print_ok("已清理")""",
        marker="clean_build(quiet=args.quiet, clean_spec=args.clean_spec)",
    ))

    return patches


# ============================================================
# 应用
# ============================================================
def validate_python(content, filepath):
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def apply_patches(patches, dry_run=False, no_backup=False, force=False):
    by_file = {}
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
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            print_fail(f"读取失败: {e}")
            total_failed += len(file_patches)
            continue

        original_content = content
        file_changed = False

        for patch in file_patches:
            if not force and patch.is_applied(content):
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

                if patch.is_python:
                    ok, err = validate_python(new_content, filepath)
                    if not ok:
                        print_fail(f"补丁 {patch.pid} 语法失败: {err}")
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

        if file_changed and not dry_run:
            if not no_backup:
                backup_path = Path(str(path) + BACKUP_SUFFIX)
                if not backup_path.exists():
                    try:
                        shutil.copy2(path, backup_path)
                        print_info(f"已备份: {backup_path.name}")
                    except Exception as e:
                        print_fail(f"备份失败: {e}")

            try:
                path.write_text(content, encoding='utf-8', newline='\n')
            except Exception as e:
                print_fail(f"写回失败: {e}")

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {total_applied}")
    print(f"  已跳过: {total_skipped}")
    print(f"  失败:   {total_failed}")

    return total_failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器 全量补丁执行 v2")
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--force', action='store_true',
                        help='忽略幂等检测，强制应用')
    parser.add_argument('--only', type=str, default='')
    parser.add_argument('--skip', type=str, default='')
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("青草编辑器 全量补丁 v2")
    print("=" * 60)
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")
    print(f"  强制:     {'是' if args.force else '否'}")

    patches = build_patches()

    if args.only:
        only_ids = {x.strip() for x in args.only.split(',') if x.strip()}
        patches = [p for p in patches if p.pid in only_ids]
    if args.skip:
        skip_ids = {x.strip() for x in args.skip.split(',') if x.strip()}
        patches = [p for p in patches if p.pid not in skip_ids]

    print(f"  补丁数:   {len(patches)}")

    success = apply_patches(patches,
                            dry_run=args.dry_run,
                            no_backup=args.no_backup,
                            force=args.force)

    if success and not args.dry_run:
        print()
        print("=" * 60)
        print("✓ 完成")
        print("=" * 60)

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