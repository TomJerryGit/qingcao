#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P0 修复脚本
============================================================
自动修复以下三个问题：

  1. core/editor.py     —— 给 EditorProxy 加 prov 属性别名
  2. core/document.py   —— 给 Document 加 enc 属性别名
  3. ui/main_window.py  —— 使用 OutlinePanel(enhanced=True)

特性：
  - 幂等：已修复的项自动跳过
  - 备份：原文件备份为 *.bak.p0
  - 验证：修改后 compile() 检查语法
  - 回滚：语法检查失败自动还原

用法：
    python fix_p0.py
    python fix_p0.py --dry-run     # 仅检测，不修改
    python fix_p0.py --no-backup   # 不生成备份
============================================================
"""

import os
import sys
import shutil
import argparse
import py_compile
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
    """备份文件为 *.bak.p0"""
    backup = path + ".bak.p0"
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
              dry_run=False, no_backup=False):
    """
    应用单块替换修复。

    参数：
        path:        目标文件
        old_block:   要替换的原始内容
        new_block:   替换后的内容
        description: 描述（用于日志）
        dry_run:     仅检测，不修改
        no_backup:   不生成备份

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

    # 检查是否已经修复（新块已存在）
    if new_block in content:
        print_skip(f"已修复，跳过: {description}")
        return False

    # 检查锚点是否存在
    if old_block not in content:
        print_fail(f"未找到锚点: {description}")
        print(f"         期望内容片段（前 200 字符）：")
        preview = old_block[:200].replace('\n', '\\n')
        print(f"         {preview}")
        return False

    # dry-run 模式
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

    # 验证语法
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
# 修复 1: core/editor.py —— 加 prov 属性
# ============================================================
def fix_editor_proxy(dry_run=False, no_backup=False):
    """给 EditorProxy 加 prov 属性别名"""
    path = os.path.join(ROOT, "core", "editor.py")

    # 锚点：title 属性定义之前
    old_block = '''    @property
    def title(self) -> str:
        """标题"""
        return self.document.title'''

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

    @property
    def title(self) -> str:
        """标题"""
        return self.document.title'''

    return apply_fix(
        path, old_block, new_block,
        "core/editor.py: EditorProxy.prov",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复 2: core/document.py —— 加 enc 属性
# ============================================================
def fix_document_enc(dry_run=False, no_backup=False):
    """给 Document 加 enc 属性别名"""
    path = os.path.join(ROOT, "core", "document.py")

    # 锚点：encoding setter 之后
    old_block = '''    @encoding.setter
    def encoding(self, value: str):
        if self.meta.encoding != value:
            old = self.meta.encoding
            self.meta.encoding = value
            if self.provider:
                self.provider.encoding = value
            self.encoding_changed.emit(old, value)'''

    new_block = '''    @encoding.setter
    def encoding(self, value: str):
        if self.meta.encoding != value:
            old = self.meta.encoding
            self.meta.encoding = value
            if self.provider:
                self.provider.encoding = value
            self.encoding_changed.emit(old, value)

    @property
    def enc(self) -> str:
        """
        [已弃用] 兼容旧 API：编码别名。

        早期代码通过 `document.enc` 访问编码，
        新代码应使用 `document.encoding`。
        """
        return self.meta.encoding

    @enc.setter
    def enc(self, value: str):
        """[已弃用] 兼容旧 API：编码别名 setter。"""
        self.encoding = value'''

    return apply_fix(
        path, old_block, new_block,
        "core/document.py: Document.enc",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复 3: ui/main_window.py —— 增强大纲
# ============================================================
def fix_main_window_outline(dry_run=False, no_backup=False):
    """main_window.py 改用 OutlinePanel(enhanced=True)"""
    path = os.path.join(ROOT, "ui", "main_window.py")

    # 锚点：完整的 try-except 块
    old_block = '''        # ============ 增强版大纲面板 ============
        try:
            from ui.outline_panel_enhanced import OutlinePanelEnhanced
            self.outline_enhanced = OutlinePanelEnhanced(self)
            self.outline_enhanced.symbol_clicked.connect(
                self._on_symbol_clicked
            )
            self.addDockWidget(
                Qt.LeftDockWidgetArea, self.outline_enhanced
            )
            # 默认隐藏（避免与基础版重叠）
            self.outline_enhanced.hide()
        except Exception as e:
            print(f"[MainWindow] OutlinePanelEnhanced 加载失败: {e}")
            self.outline_enhanced = None'''

    new_block = '''        # ============ 增强版大纲面板 ============
        # P3-8 重构后 outline_panel_enhanced.py 已合并到 outline_panel.py，
        # 通过 OutlinePanel(enhanced=True) 启用增强功能
        # （面包屑、类型筛选、排序切换、跟随光标高亮、3 列树）
        try:
            from ui.outline_panel import OutlinePanel
            self.outline_enhanced = OutlinePanel(self, enhanced=True)
            self.outline_enhanced.symbol_clicked.connect(
                self._on_symbol_clicked
            )
            self.addDockWidget(
                Qt.LeftDockWidgetArea, self.outline_enhanced
            )
            # 默认隐藏（避免与基础版重叠）
            self.outline_enhanced.hide()
        except Exception as e:
            print(f"[MainWindow] 增强大纲加载失败: {e}")
            import traceback
            traceback.print_exc()
            self.outline_enhanced = None'''

    return apply_fix(
        path, old_block, new_block,
        "ui/main_window.py: OutlinePanel(enhanced=True)",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复后自检
# ============================================================
def self_check():
    """修复后自检：验证属性/导入是否可用"""
    print_header("自检")

    # 检查 prov 属性
    try:
        with open(os.path.join(ROOT, "core", "editor.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "def prov(self):" in content:
            print_ok("core/editor.py: prov 属性已添加")
        else:
            print_fail("core/editor.py: prov 属性未找到")
    except Exception as e:
        print_fail(f"core/editor.py 检查失败: {e}")

    # 检查 enc 属性
    try:
        with open(os.path.join(ROOT, "core", "document.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "def enc(self)" in content:
            print_ok("core/document.py: enc 属性已添加")
        else:
            print_fail("core/document.py: enc 属性未找到")
    except Exception as e:
        print_fail(f"core/document.py 检查失败: {e}")

    # 检查 main_window
    try:
        with open(os.path.join(ROOT, "ui", "main_window.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "OutlinePanel(self, enhanced=True)" in content:
            print_ok("ui/main_window.py: OutlinePanel(enhanced=True) 已应用")
        elif "outline_panel_enhanced" in content:
            print_fail("ui/main_window.py: 仍在使用旧模块 outline_panel_enhanced")
        else:
            print_warn("ui/main_window.py: 未找到增强大纲相关代码")
    except Exception as e:
        print_fail(f"ui/main_window.py 检查失败: {e}")

    # 编译检查
    print()
    print("编译检查：")
    for rel in ["core/editor.py", "core/document.py", "ui/main_window.py"]:
        path = os.path.join(ROOT, rel)
        ok, err = validate_syntax(path)
        if ok:
            print_ok(f"{rel}")
        else:
            print_fail(f"{rel}: {err}")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器 P0 修复脚本",
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='仅检测，不修改')
    parser.add_argument('--no-backup', action='store_true',
                        help='不生成备份文件')

    args = parser.parse_args()

    print_header("青草编辑器 P0 修复")
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       {'DRY-RUN（不修改）' if args.dry_run else '实际修复'}")
    print(f"  备份:       {'禁用' if args.no_backup else '启用'}")

    fixed = 0
    skipped = 0
    failed = 0

    # 修复 1
    print_header("修复 1/3: core/editor.py —— EditorProxy.prov")
    try:
        result = fix_editor_proxy(
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

    # 修复 2
    print_header("修复 2/3: core/document.py —— Document.enc")
    try:
        result = fix_document_enc(
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

    # 修复 3
    print_header("修复 3/3: ui/main_window.py —— OutlinePanel(enhanced=True)")
    try:
        result = fix_main_window_outline(
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

    # 汇总
    print_header("汇总")
    print(f"  已修复: {fixed}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    # 自检（仅在非 dry-run 且有修改时执行）
    if not args.dry_run and fixed > 0:
        self_check()

    # 提示
    print()
    if failed > 0:
        print("✗ 存在失败项，请检查上述错误")
        return 1

    if args.dry_run:
        print("✓ DRY-RUN 完成，未实际修改")
        print("  运行 `python fix_p0.py` 执行实际修复")
    elif fixed > 0:
        print("✓ 修复完成，请重新启动编辑器验证：")
        print("    python main.py")
        print()
        print("  验证清单：")
        print("    1. 打开 .py 文件 → 工具 → Python 调试 → 运行当前文件")
        print("    2. 打开任意文件 → 工具 → Git → 查看状态")
        print("    3. 视图 → 面板 → 大纲（增强）")
        print()
        print("  如果之前有备份，可删除：")
        print("    del core\\editor.py.bak.p0")
        print("    del core\\document.py.bak.p0")
        print("    del ui\\main_window.py.bak.p0")
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