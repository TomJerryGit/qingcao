#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P0 修复脚本（第二轮）
============================================================
在 fix_p0.py 基础上，处理剩余的 prov/enc 兼容问题：

  1. core/editor.py     —— 给 prov 属性加 setter
                            （fix_p0.py 只加了 getter，
                              tabs.py 中 `proxy.prov = x` 会失败）

  2. app/tabs.py        —— 简化 _reload_file 中的 provider 更新逻辑
                            （移除死代码 elif 分支）

  3. app/plugins.py     —— get_current_filepath 迁移到新 API
                            （不再直接访问 editor.prov）

前置条件：
    fix_p0.py 已成功运行（core/editor.py 中已存在 prov 属性）

特性：
    - 幂等：已修复的项自动跳过
    - 备份：原文件备份为 *.bak.p0_2
    - 验证：修改后 compile() 检查语法
    - 回滚：语法检查失败自动还原

用法：
    python fix_p0_2.py
    python fix_p0_2.py --dry-run     # 仅检测，不修改
    python fix_p0_2.py --no-backup   # 不生成备份
============================================================
"""

import os
import sys
import shutil
import argparse
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# 通用工具
# ============================================================
def print_header(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_ok(msg):
    print("  [OK]   " + msg)


def print_skip(msg):
    print("  [SKIP] " + msg)


def print_warn(msg):
    print("  [WARN] " + msg)


def print_fail(msg):
    print("  [FAIL] " + msg)


def backup_file(path):
    """备份文件为 *.bak.p0_2"""
    backup = path + ".bak.p0_2"
    try:
        shutil.copy2(path, backup)
        return backup
    except Exception as e:
        print_warn(f"备份失败: {e}")
        return None


def restore_backup(path, backup):
    """从备份还原"""
    if backup and os.path.exists(backup):
        try:
            shutil.copy2(backup, path)
            return True
        except Exception:
            return False
    return False


def validate_syntax(path):
    """验证 Python 文件语法"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        compile(source, path, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_fix(path, old_block, new_block, description,
              applied_marker=None,
              dry_run=False, no_backup=False):
    """
    应用单块替换修复。

    参数：
        path:           目标文件
        old_block:      要替换的原始内容
        new_block:      替换后的内容
        description:    描述
        applied_marker: 幂等标记（若存在于文件，则认为已修复）
        dry_run:        仅检测，不修改
        no_backup:      不生成备份

    返回：
        True 表示已修改（或 dry_run 下会修改）
        False 表示跳过
    """
    if not os.path.exists(path):
        print_fail(f"文件不存在: {path}")
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return False

    # 幂等检测
    marker = applied_marker if applied_marker else new_block
    if marker in content:
        print_skip(f"已修复，跳过: {description}")
        return False

    # 锚点检测
    if old_block not in content:
        print_fail(f"未找到锚点: {description}")
        print(f"         期望片段（前 300 字符）：")
        preview = old_block[:300]
        for line in preview.split('\n')[:10]:
            print(f"         | {line}")
        return False

    # dry-run
    if dry_run:
        print_ok(f"[DRY-RUN] 会修改: {description}")
        return True

    # 备份
    backup = None
    if not no_backup:
        backup = backup_file(path)
        if backup:
            print_ok(f"已备份: {os.path.basename(backup)}")

    # 替换
    new_content = content.replace(old_block, new_block, 1)

    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)
    except Exception as e:
        print_fail(f"写入失败: {e}")
        if backup:
            restore_backup(path, backup)
        return False

    # 语法验证
    ok, err = validate_syntax(path)
    if not ok:
        print_fail(f"语法检查失败: {err}")
        if backup:
            restore_backup(path, backup)
            print_warn("已从备份还原")
        return False

    print_ok(f"已修改: {description}")
    return True


# ============================================================
# 修复 1: core/editor.py —— 给 prov 加 setter
# ============================================================
def fix_prov_setter(dry_run=False, no_backup=False):
    """给 EditorProxy.prov 加 setter"""
    path = os.path.join(ROOT, "core", "editor.py")

    # 检查 prov 属性是否已存在（fix_p0.py 是否已运行）
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return False

    if "@property\n    def prov(self):" not in content:
        print_fail("未找到 prov 属性。请先运行 fix_p0.py")
        return False

    # 锚点：fix_p0.py 生成的 prov getter
    old_block = '''    @property
    def prov(self):
        """
        [已弃用] 兼容旧 API：内容提供者。

        早期代码通过 `proxy.prov` 访问 ContentProvider，
        新代码应使用 `proxy.document.provider`。

        保留此别名以便：
        - 兼容 app/plugins.py 等尚未迁移的调用方
        - 兼容第三方插件

        返回：
            ContentProvider 实例或 None
        """
        if self.document:
            return self.document.provider
        return None'''

    new_block = '''    @property
    def prov(self):
        """
        [已弃用] 兼容旧 API：内容提供者。

        早期代码通过 `proxy.prov` 访问 ContentProvider，
        新代码应使用 `proxy.document.provider`。

        保留此别名以便：
        - 兼容 app/plugins.py 等尚未迁移的调用方
        - 兼容第三方插件

        返回：
            ContentProvider 实例或 None
        """
        if self.document:
            return self.document.provider
        return None

    @prov.setter
    def prov(self, value):
        """
        [已弃用] 兼容旧 API：设置内容提供者。

        早期代码通过 `proxy.prov = provider` 更新，
        新代码应使用 `proxy.document.provider = provider`。
        """
        if self.document:
            self.document.provider = value'''

    return apply_fix(
        path, old_block, new_block,
        "core/editor.py: prov setter",
        applied_marker="@prov.setter",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复 2: app/tabs.py —— 简化 provider 更新逻辑
# ============================================================
def fix_tabs_provider(dry_run=False, no_backup=False):
    """简化 _reload_file 中的 provider 更新"""
    path = os.path.join(ROOT, "app", "tabs.py")

    old_block = '''            # 更新 proxy 的 provider
            try:
                if hasattr(editor, 'proxy'):
                    if hasattr(editor.proxy, 'document') and \\
                            editor.proxy.document:
                        editor.proxy.document.provider = provider
                    elif hasattr(editor.proxy, 'prov'):
                        editor.proxy.prov = provider
            except Exception:
                pass'''

    new_block = '''            # 更新 proxy 的 provider（使用新 API）
            try:
                if hasattr(editor, 'proxy') and editor.proxy.document:
                    editor.proxy.document.provider = provider
            except Exception:
                pass'''

    return apply_fix(
        path, old_block, new_block,
        "app/tabs.py: 简化 provider 更新",
        applied_marker="# 更新 proxy 的 provider（使用新 API）",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复 3: app/plugins.py —— get_current_filepath 迁移
# ============================================================
def fix_plugins_filepath(dry_run=False, no_backup=False):
    """get_current_filepath 迁移到新 API"""
    path = os.path.join(ROOT, "app", "plugins.py")

    old_block = '''    def get_current_filepath(self) -> Optional[str]:
        """获取当前编辑器的文件路径"""
        editor = self.current_editor()
        if editor and editor.prov:
            return editor.prov.filepath
        return None'''

    new_block = '''    def get_current_filepath(self) -> Optional[str]:
        """获取当前编辑器的文件路径（使用新 API）"""
        editor = self.current_editor()
        if not editor:
            return None

        # 优先使用新 API
        if hasattr(editor, 'document') and editor.document:
            return editor.document.filepath or None

        # 兜底：走 EditorProxy 的属性别名
        return editor.filepath or None'''

    return apply_fix(
        path, old_block, new_block,
        "app/plugins.py: get_current_filepath",
        applied_marker="def get_current_filepath(self) -> Optional[str]:\n        \"\"\"获取当前编辑器的文件路径（使用新 API）\"\"\"",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 自检
# ============================================================
def self_check():
    """静态检查修复是否到位"""
    print_header("自检")

    # ---- 检查 1: prov setter ----
    try:
        with open(os.path.join(ROOT, "core", "editor.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "@prov.setter" in content:
            print_ok("core/editor.py: prov setter 已添加")
        else:
            print_fail("core/editor.py: prov setter 未找到")
    except Exception as e:
        print_fail(f"core/editor.py 检查失败: {e}")

    # ---- 检查 2: tabs provider 更新 ----
    try:
        with open(os.path.join(ROOT, "app", "tabs.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "# 更新 proxy 的 provider（使用新 API）" in content:
            print_ok("app/tabs.py: provider 更新已简化")
        elif "editor.proxy.prov = provider" in content:
            print_fail("app/tabs.py: 仍存在旧逻辑 `editor.proxy.prov = provider`")
        else:
            print_warn("app/tabs.py: 未找到相关代码")
    except Exception as e:
        print_fail(f"app/tabs.py 检查失败: {e}")

    # ---- 检查 3: plugins get_current_filepath ----
    try:
        with open(os.path.join(ROOT, "app", "plugins.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "def get_current_filepath(self) -> Optional[str]:\n        \"\"\"获取当前编辑器的文件路径（使用新 API）\"\"\"" in content:
            print_ok("app/plugins.py: get_current_filepath 已迁移")
        elif "return editor.prov.filepath" in content:
            print_fail("app/plugins.py: 仍存在 `return editor.prov.filepath`")
        else:
            print_warn("app/plugins.py: 未找到 get_current_filepath")
    except Exception as e:
        print_fail(f"app/plugins.py 检查失败: {e}")

    # ---- 编译检查 ----
    print()
    print("编译检查：")
    for rel in ["core/editor.py", "app/tabs.py", "app/plugins.py"]:
        path = os.path.join(ROOT, rel)
        ok, err = validate_syntax(path)
        if ok:
            print_ok(rel)
        else:
            print_fail(f"{rel}: {err}")

    # ---- 残留检查 ----
    print()
    print("残留检查（.prov 访问）：")
    found_legacy = False
    for rel in ["core/editor.py", "app/tabs.py", "app/plugins.py",
                "app/menus.py", "app/session.py"]:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for lineno, line in enumerate(f, 1):
                    stripped = line.strip()
                    # 跳过注释行
                    if stripped.startswith('#'):
                        continue
                    # 检测 editor.prov / proxy.prov（赋值除外，因为已加 setter）
                    if "editor.prov." in line or "proxy.prov." in line:
                        print_warn(f"{rel}:{lineno}: {line.rstrip()}")
                        found_legacy = True
        except Exception:
            pass

    if not found_legacy:
        print_ok("未发现残留的 .prov 属性访问")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器 P0 修复（第二轮）",
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='仅检测，不修改')
    parser.add_argument('--no-backup', action='store_true',
                        help='不生成备份文件')

    args = parser.parse_args()

    print_header("青草编辑器 P0 修复（第二轮）")
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       {'DRY-RUN（不修改）' if args.dry_run else '实际修复'}")
    print(f"  备份:       {'禁用' if args.no_backup else '启用'}")

    fixed = 0
    skipped = 0
    failed = 0

    # ---- 修复 1 ----
    print_header("修复 1/3: core/editor.py —— prov setter")
    try:
        result = fix_prov_setter(
            dry_run=args.dry_run, no_backup=args.no_backup
        )
        if result:
            fixed += 1
        else:
            skipped += 1
    except Exception as e:
        print_fail(f"异常: {e}")
        traceback.print_exc()
        failed += 1

    # ---- 修复 2 ----
    print_header("修复 2/3: app/tabs.py —— 简化 provider 更新")
    try:
        result = fix_tabs_provider(
            dry_run=args.dry_run, no_backup=args.no_backup
        )
        if result:
            fixed += 1
        else:
            skipped += 1
    except Exception as e:
        print_fail(f"异常: {e}")
        traceback.print_exc()
        failed += 1

    # ---- 修复 3 ----
    print_header("修复 3/3: app/plugins.py —— get_current_filepath")
    try:
        result = fix_plugins_filepath(
            dry_run=args.dry_run, no_backup=args.no_backup
        )
        if result:
            fixed += 1
        else:
            skipped += 1
    except Exception as e:
        print_fail(f"异常: {e}")
        traceback.print_exc()
        failed += 1

    # ---- 汇总 ----
    print_header("汇总")
    print(f"  已修复: {fixed}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    # ---- 自检 ----
    if not args.dry_run and fixed > 0:
        self_check()

    # ---- 提示 ----
    print()
    if failed > 0:
        print("✗ 存在失败项，请检查上述错误")
        return 1

    if args.dry_run:
        print("✓ DRY-RUN 完成，未实际修改")
        print("  运行 `python fix_p0_2.py` 执行实际修复")
    elif fixed > 0:
        print("✓ 修复完成，请重新启动编辑器验证：")
        print("    python main.py")
        print()
        print("  验证清单：")
        print("    1. 打开 .py 文件 → 工具 → Python 调试 → 运行当前文件")
        print("    2. 打开任意文件 → 工具 → Git → 查看状态")
        print("    3. 打开任意文件 → 编辑保存后，用外部程序修改该文件")
        print("       → 应提示重新加载，且不报错")
        print()
        print("  如果之前有备份，可删除：")
        print("    del core\\editor.py.bak.p0_2")
        print("    del app\\tabs.py.bak.p0_2")
        print("    del app\\plugins.py.bak.p0_2")
    else:
        print("✓ 所有修复项均已完成，无需改动")

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