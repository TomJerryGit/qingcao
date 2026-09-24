#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P3 修复脚本
============================================================
包含 3 项：

  1. P3-3: 集成 status_bar_widgets 到主窗口状态栏
           （编码/行尾符可点击切换，Git 分支可点击）

  2. P3-2a: 删除 ui/ai_actions.py（无引用）

  3. P3-2b: 删除 core/search_worker.py，并同步清理
            build.py 的 hidden_imports 列表

前置检查：
    - ui/status_bar_widgets.py 必须存在

用法：
    python fix_p3_3.py --dry-run
    python fix_p3_3.py
============================================================
"""

import os
import sys
import shutil
import argparse
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_skip(m):
    print("  [SKIP] " + m)


def print_warn(m):
    print("  [WARN] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def print_info(m):
    print("  [INFO] " + m)


def backup_file(path, suffix=".bak.p3"):
    backup = path + suffix
    try:
        shutil.copy2(path, backup)
        return backup
    except Exception as e:
        print_warn(f"备份失败: {e}")
        return None


def restore(path, backup):
    if backup and os.path.exists(backup):
        try:
            shutil.copy2(backup, path)
            return True
        except Exception:
            return False
    return False


def validate_syntax(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            src = f.read()
        compile(src, path, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_fix(path, old, new, desc, marker=None,
              dry_run=False, no_backup=False):
    if not os.path.exists(path):
        print_fail(f"文件不存在: {path}")
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return False

    check = marker if marker else new
    if check in content:
        print_skip(f"已修复: {desc}")
        return False

    if old not in content:
        print_fail(f"未找到锚点: {desc}")
        print("         期望片段：")
        for line in old.split('\n')[:8]:
            print(f"         | {line}")
        return False

    if dry_run:
        print_ok(f"[DRY-RUN] 会修改: {desc}")
        return True

    backup = None
    if not no_backup:
        backup = backup_file(path)
        if backup:
            print_ok(f"已备份: {os.path.basename(backup)}")

    new_content = content.replace(old, new, 1)

    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)
    except Exception as e:
        print_fail(f"写入失败: {e}")
        if backup:
            restore(path, backup)
        return False

    ok, err = validate_syntax(path)
    if not ok:
        print_fail(f"语法检查失败: {err}")
        if backup:
            restore(path, backup)
            print_warn("已从备份还原")
        return False

    print_ok(f"已修改: {desc}")
    return True


# ============================================================
# 前置检查
# ============================================================
def preflight():
    """前置检查"""
    sbw = os.path.join(ROOT, "ui", "status_bar_widgets.py")
    if not os.path.exists(sbw):
        print_fail(f"缺少前置文件: ui/status_bar_widgets.py")
        print_info("请先确认该文件存在于 ui/ 目录下")
        return False

    print_ok(f"前置文件存在: ui/status_bar_widgets.py")
    return True


# ============================================================
# 修复 1: P3-3 —— 状态栏集成
# ============================================================
def fix_status_bar_labels(dry_run=False, no_backup=False):
    """状态栏编码/行尾符替换为可点击组件"""
    path = os.path.join(ROOT, "ui", "main_window.py")

    old = """        # 编码
        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setMinimumWidth(80)
        self.status_bar.addWidget(self.encoding_label)

        # 行尾符
        self.eol_label = QLabel("LF")
        self.eol_label.setMinimumWidth(40)
        self.status_bar.addWidget(self.eol_label)"""

    new = """        # 编码（可点击切换）
        try:
            from ui.status_bar_widgets import EncodingLabel
            self.encoding_label = EncodingLabel(self)
            self.encoding_label.setMinimumWidth(80)
            self.encoding_label.encoding_changed.connect(
                self._on_encoding_changed
            )
        except ImportError:
            self.encoding_label = QLabel("UTF-8")
            self.encoding_label.setMinimumWidth(80)
        self.status_bar.addWidget(self.encoding_label)

        # 行尾符（可点击切换）
        try:
            from ui.status_bar_widgets import EolLabel
            self.eol_label = EolLabel(self)
            self.eol_label.setMinimumWidth(40)
            self.eol_label.eol_changed.connect(self._on_eol_changed)
        except ImportError:
            self.eol_label = QLabel("LF")
            self.eol_label.setMinimumWidth(40)
        self.status_bar.addWidget(self.eol_label)"""

    return apply_fix(
        path, old, new,
        "状态栏编码/行尾符换为可点击组件",
        marker="self.encoding_label = EncodingLabel(self)",
        dry_run=dry_run, no_backup=no_backup,
    )


def fix_status_bar_git(dry_run=False, no_backup=False):
    """Git 分支标签换为可点击组件"""
    path = os.path.join(ROOT, "ui", "main_window.py")

    old = """        # Git 分支
        self.git_branch_label = QLabel("")
        self.git_branch_label.setMinimumWidth(100)
        self.status_bar.addPermanentWidget(self.git_branch_label)"""

    new = """        # Git 分支（可点击）
        try:
            from ui.status_bar_widgets import GitBranchLabel
            self.git_branch_label = GitBranchLabel(self)
            self.git_branch_label.setMinimumWidth(100)
            self.git_branch_label.git_clicked.connect(
                self._on_git_branch_clicked
            )
        except ImportError:
            self.git_branch_label = QLabel("")
            self.git_branch_label.setMinimumWidth(100)
        self.status_bar.addPermanentWidget(self.git_branch_label)"""

    return apply_fix(
        path, old, new,
        "状态栏 Git 分支换为可点击组件",
        marker="self.git_branch_label = GitBranchLabel(self)",
        dry_run=dry_run, no_backup=no_backup,
    )


def add_status_bar_slots(dry_run=False, no_backup=False):
    """新增 _on_encoding_changed / _on_eol_changed / _on_git_branch_clicked"""
    path = os.path.join(ROOT, "ui", "main_window.py")

    old = '''    def _refresh_status(self):
        """定时刷新状态栏"""
        self._update_memory()'''

    new = '''    def _on_encoding_changed(self, encoding: str):
        """状态栏切换编码"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.document:
                proxy.document.change_encoding(encoding)
                self._update_status_for_editor()
                self.status_bar.showMessage(
                    f"编码已切换: {encoding}", 2000
                )
        except Exception as e:
            print(f"[MainWindow] 切换编码失败: {e}")

    def _on_eol_changed(self, eol: str):
        """状态栏切换行尾符"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.document:
                if hasattr(proxy.document, 'set_eol'):
                    proxy.document.set_eol(eol)
                    self._update_status_for_editor()
                    display = {"\\n": "LF", "\\r\\n": "CRLF",
                                "\\r": "CR"}.get(eol, "LF")
                    self.status_bar.showMessage(
                        f"行尾符已切换: {display}", 2000
                    )
        except Exception as e:
            print(f"[MainWindow] 切换行尾符失败: {e}")

    def _on_git_branch_clicked(self):
        """状态栏点击 Git 分支"""
        try:
            # 优先尝试调用已加载的 git_deep 插件
            for plugin in getattr(self, 'plugins', []):
                if getattr(plugin, 'NAME', '') == 'git_deep':
                    if hasattr(plugin, 'show_status'):
                        plugin.show_status()
                        return
            # 回退：显示简单提示
            from PyQt5.QtWidgets import QMessageBox
            text = self.git_branch_label.text() or "(无)"
            QMessageBox.information(self, "Git 分支", text)
        except Exception as e:
            print(f"[MainWindow] Git 分支点击失败: {e}")

    def _refresh_status(self):
        """定时刷新状态栏"""
        self._update_memory()'''

    return apply_fix(
        path, old, new,
        "新增状态栏槽函数",
        marker="def _on_encoding_changed(self, encoding: str):",
        dry_run=dry_run, no_backup=no_backup,
    )


def fix_update_status_for_editor(dry_run=False, no_backup=False):
    """_update_status_for_editor 调用新组件的 setter"""
    path = os.path.join(ROOT, "ui", "main_window.py")

    old = """            # 编码
            try:
                enc = "utf-8"
                if proxy.document:
                    enc = proxy.document.encoding or "utf-8"
                self.encoding_label.setText(enc.upper())
            except Exception:
                pass

            # 行尾符
            try:
                if proxy.document and hasattr(proxy.document, 'meta'):
                    eol = getattr(proxy.document.meta, 'eol', "\\n")
                    eol_display = {'\\n': 'LF', '\\r\\n': 'CRLF',
                                    '\\r': 'CR'}.get(eol, 'LF')
                    self.eol_label.setText(eol_display)
            except Exception:
                pass"""

    new = """            # 编码（优先调用新组件的 set_encoding）
            try:
                enc = "utf-8"
                if proxy.document:
                    enc = proxy.document.encoding or "utf-8"
                if hasattr(self.encoding_label, 'set_encoding'):
                    self.encoding_label.set_encoding(enc)
                else:
                    self.encoding_label.setText(enc.upper())
            except Exception:
                pass

            # 行尾符（优先调用新组件的 set_eol）
            try:
                if proxy.document and hasattr(proxy.document, 'meta'):
                    eol = getattr(proxy.document.meta, 'eol', "\\n")
                    if hasattr(self.eol_label, 'set_eol'):
                        self.eol_label.set_eol(eol)
                    else:
                        eol_display = {'\\n': 'LF', '\\r\\n': 'CRLF',
                                        '\\r': 'CR'}.get(eol, 'LF')
                        self.eol_label.setText(eol_display)
            except Exception:
                pass"""

    return apply_fix(
        path, old, new,
        "_update_status_for_editor 调用新组件 setter",
        marker="if hasattr(self.encoding_label, 'set_encoding'):",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复 2: P3-2a —— 删除 ui/ai_actions.py
# ============================================================
def remove_ai_actions(dry_run=False, no_backup=False):
    """删除未被引用的 ui/ai_actions.py"""
    path = os.path.join(ROOT, "ui", "ai_actions.py")

    if not os.path.exists(path):
        print_skip("文件不存在，跳过")
        return False

    if dry_run:
        print_ok(f"[DRY-RUN] 会删除: ui/ai_actions.py")
        return True

    # 备份
    if not no_backup:
        backup = path + ".bak.p3"
        try:
            shutil.move(path, backup)
            print_ok(f"已移入备份: {os.path.basename(backup)}")
            return True
        except Exception as e:
            print_fail(f"删除失败: {e}")
            return False
    else:
        try:
            os.remove(path)
            print_ok("已删除: ui/ai_actions.py")
            return True
        except Exception as e:
            print_fail(f"删除失败: {e}")
            return False


# ============================================================
# 修复 3: P3-2b —— 删除 core/search_worker.py + 清理 build.py
# ============================================================
def remove_search_worker(dry_run=False, no_backup=False):
    """删除 core/search_worker.py 并同步 build.py"""
    target = os.path.join(ROOT, "core", "search_worker.py")

    if not os.path.exists(target):
        print_skip("core/search_worker.py 不存在，跳过")
    elif dry_run:
        print_ok("[DRY-RUN] 会删除: core/search_worker.py")
    else:
        if not no_backup:
            backup = target + ".bak.p3"
            try:
                shutil.move(target, backup)
                print_ok(f"已移入备份: {os.path.basename(backup)}")
            except Exception as e:
                print_fail(f"删除失败: {e}")
                return False
        else:
            try:
                os.remove(target)
                print_ok("已删除: core/search_worker.py")
            except Exception as e:
                print_fail(f"删除失败: {e}")
                return False

    # 同步清理 build.py 中的 hidden_imports
    build_py = os.path.join(ROOT, "build.py")
    if not os.path.exists(build_py):
        print_warn("build.py 不存在，跳过清理")
        return True

    old = "        'core.search_worker',\n"
    if old not in open(build_py, 'r', encoding='utf-8').read():
        # 也可能缩进不同，尝试其他形式
        print_info("build.py 中未找到 'core.search_worker' 引用")
        return True

    if dry_run:
        print_ok("[DRY-RUN] 会从 build.py 移除 core.search_worker")
        return True

    return apply_fix(
        build_py,
        old,
        "",  # 直接删除这一行
        "build.py 移除 core.search_worker",
        marker="'core.search_worker'",
        dry_run=False, no_backup=no_backup,
    )


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器 P3 修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--skip-status-bar', action='store_true',
                        help='跳过状态栏集成')
    parser.add_argument('--skip-cleanup', action='store_true',
                        help='跳过冗余文件清理')
    args = parser.parse_args()

    print_header("青草编辑器 P3 修复")
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       {'DRY-RUN' if args.dry_run else '实际修复'}")

    # 前置检查
    print_header("前置检查")
    if not args.skip_status_bar:
        if not preflight():
            print()
            print("请提供 ui/status_bar_widgets.py 后再运行")
            return 1
    else:
        print_info("已跳过状态栏集成的前置检查")

    fixed = 0

    # ---- 修复 1: 状态栏 ----
    if not args.skip_status_bar:
        print_header("修复 1/3: P3-3 —— 状态栏集成")

        for fn, name in [
            (fix_status_bar_labels, "编码/行尾符"),
            (fix_status_bar_git, "Git 分支"),
            (add_status_bar_slots, "槽函数"),
            (fix_update_status_for_editor, "_update_status_for_editor"),
        ]:
            try:
                if fn(dry_run=args.dry_run, no_backup=args.no_backup):
                    fixed += 1
            except Exception as e:
                print_fail(f"{name} 异常: {e}")
                traceback.print_exc()

    # ---- 修复 2: 删除 ai_actions.py ----
    if not args.skip_cleanup:
        print_header("修复 2/3: P3-2a —— 删除 ui/ai_actions.py")
        try:
            if remove_ai_actions(dry_run=args.dry_run,
                                  no_backup=args.no_backup):
                fixed += 1
        except Exception as e:
            print_fail(f"异常: {e}")

    # ---- 修复 3: 删除 search_worker.py ----
    if not args.skip_cleanup:
        print_header("修复 3/3: P3-2b —— 删除 core/search_worker.py")
        try:
            if remove_search_worker(dry_run=args.dry_run,
                                     no_backup=args.no_backup):
                fixed += 1
        except Exception as e:
            print_fail(f"异常: {e}")

    # ---- 汇总 ----
    print_header("汇总")
    print(f"  已处理: {fixed}")
    print()
    if args.dry_run:
        print("✓ DRY-RUN 完成，运行 `python fix_p3_3.py` 执行")
    else:
        print("✓ 修复完成，建议执行：")
        print("    python main.py")
        print()
        print("  验证清单：")
        print("    1. 状态栏编码（UTF-8）→ 点击应弹出菜单")
        print("    2. 状态栏行尾符（LF）→ 点击应弹出菜单")
        print("    3. Git 分支（若有）→ 点击应打开 Git 状态")
        print()
        print("  回滚命令（如需）：")
        print("    copy ui\\main_window.py.bak.p3 ui\\main_window.py")
        print("    copy ui\\ai_actions.py.bak.p3 ui\\ai_actions.py")
        print("    copy core\\search_worker.py.bak.p3 core\\search_worker.py")

    return 0


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