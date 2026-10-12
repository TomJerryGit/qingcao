#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 主题跟随修复 v3
============================================================
修复 v2 遗留问题：
    'ThemeLoader' object has no attribute 'notify_widgets'

原因：
    v1 脚本在 main_window.py 里写的是实例方法调用：
        loader.notify_widgets(self, theme)
    但在 theme_loader.py 里定义的是模块级函数：
        def notify_widgets(root, theme): ...
    调用方式错配。

修复：
    在 ThemeLoader 类里加实例方法 notify_widgets，
    内部调用模块级函数。

用法：
    python fix_theme_follow_v3.py --dry-run
    python fix_theme_follow_v3.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "infrastructure" / "theme_loader.py"
BACKUP_SUFFIX = ".bak.themefollow3"


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m): print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 补丁内容
# ============================================================
PATCH_MARKER = "# v3.1: notify_widgets 实例方法"

# 用 __init__ 方法作为锚点（ThemeLoader 的第一个方法）
PATCH_OLD = '''    def __init__(self, parent: Optional[QObject] = None,
                 theme_dir: str = DEFAULT_THEME_DIR):
        """
        参数:
            parent: 父 QObject
            theme_dir: 主题目录
        """
        super().__init__(parent)'''

PATCH_NEW = '''    def notify_widgets(self, root, theme):
        """
        v3.1: notify_widgets 实例方法。

        遍历 root 控件树，通知所有带 refresh_theme 的子控件刷新样式。
        内部调用模块级函数 notify_widgets(root, theme)。
        """
        try:
            # 调用同模块内的模块级函数
            notify_widgets(root, theme)
        except NameError:
            # 兜底：模块级函数不存在时手动实现
            try:
                from PyQt5.QtWidgets import QWidget
                for widget in root.findChildren(QWidget):
                    fn = getattr(widget, 'refresh_theme', None)
                    if callable(fn):
                        try:
                            fn(theme)
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception as e:
            print(f"[ThemeLoader] notify_widgets 失败: {e}")

    def __init__(self, parent: Optional[QObject] = None,
                 theme_dir: str = DEFAULT_THEME_DIR):
        """
        参数:
            parent: 父 QObject
            theme_dir: 主题目录
        """
        super().__init__(parent)'''


def validate_python(content, filepath):
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("主题跟随修复 v3")
    print(f"  目标文件: {TARGET.relative_to(ROOT)}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    if not TARGET.exists():
        print_fail(f"文件不存在: {TARGET}")
        return 1

    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    # 幂等检测
    if PATCH_MARKER in content:
        print_skip("补丁已应用")
        return 0

    # 锚点检测
    if PATCH_OLD not in content:
        print_fail("锚点未找到")
        print()
        print("  期望锚点（ThemeLoader.__init__ 的开头 4 行）：")
        for line in PATCH_OLD.split('\n')[:4]:
            print(f"    | {line}")
        print()
        print("  请手动打开 infrastructure/theme_loader.py，")
        print("  在 ThemeLoader.__init__ 方法前插入 notify_widgets 方法。")
        return 1

    if content.count(PATCH_OLD) > 1:
        print_fail("锚点重复出现")
        return 1

    if args.dry_run:
        print_info("[DRY-RUN] 锚点存在，会在 ThemeLoader.__init__ 前插入 notify_widgets 方法")
        return 0

    # 应用
    new_content = content.replace(PATCH_OLD, PATCH_NEW, 1)

    ok, err = validate_python(new_content, str(TARGET))
    if not ok:
        print_fail(f"语法错误: {err}")
        return 1
    print_ok("语法验证通过")

    # 备份
    if not args.no_backup:
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(TARGET, backup)
                print_info(f"已备份: {backup.name}")
            except Exception as e:
                print_fail(f"备份失败: {e}")
                return 1

    # 写回
    try:
        TARGET.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok("已写回")
    except Exception as e:
        print_fail(f"写回失败: {e}")
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if backup.exists():
            try:
                shutil.copy2(backup, TARGET)
                print_info("已从备份还原")
            except Exception:
                pass
        return 1

    print()
    print("=" * 60)
    print("✓ 修复完成")
    print("=" * 60)
    print()
    print("下一步:")
    print("  python main.py")
    print("  切换主题，观察控制台是否还有 notify_widgets 报错")

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