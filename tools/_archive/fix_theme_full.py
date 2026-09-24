#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 主题功能完整补丁
============================================================
修改 ui/main_window.py：
1. 视图 → 主题 → 增加"编辑/市场/导入/导出/删除"子菜单项
2. 工具 → 增加"首选项..."菜单项
3. 增加对应的槽函数

依赖（应已存在）：
    ui/theme_editor.py
    ui/theme_market.py       （本方案新增）
    ui/preferences_panel.py  （本方案新增）
    core/theme_pack.py
    infrastructure/theme_loader.py

用法：
    python fix_theme_full.py --dry-run
    python fix_theme_full.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "ui" / "main_window.py"
BACKUP_SUFFIX = ".bak.themefull"


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m): print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 补丁 1：视图菜单加主题子菜单
# ============================================================
PATCH_1_MARKER = "# --- 主题子菜单（完整版）---"

PATCH_1_OLD = '''        # ============ 工具菜单 ============
        self.tools_menu = menubar.addMenu("工具(&T)")'''

PATCH_1_NEW = '''        # --- 主题子菜单（完整版）---
        self.theme_menu = self.view_menu.addMenu("🎨 主题")
        self._build_full_theme_menu()

        # ============ 工具菜单 ============
        self.tools_menu = menubar.addMenu("工具(&T)")'''


# ============================================================
# 补丁 2：工具菜单加"首选项"
# ============================================================
PATCH_2_MARKER = "# --- 首选项入口 ---"

PATCH_2_OLD = '''        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📤 导出配置", None,
                          self._export_config)'''

PATCH_2_NEW = '''        # --- 首选项入口 ---
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "⚙ 首选项...", "Ctrl+,",
                          self._show_preferences)

        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📤 导出配置", None,
                          self._export_config)'''


# ============================================================
# 补丁 3：加 _build_full_theme_menu 方法
# ============================================================
PATCH_3_MARKER = "def _build_full_theme_menu(self):"

PATCH_3_OLD = '''    def _add_action(self, menu: QMenu, text: str, shortcut: Optional[str],
                     slot) -> QAction:'''

PATCH_3_NEW = '''    def _build_full_theme_menu(self):
        """构建完整的主题子菜单"""
        # 跟随系统
        self._add_action(
            self.theme_menu, "跟随系统", None,
            lambda: self._apply_theme_by_name("__system__")
        )

        self.theme_menu.addSeparator()

        # 动态扫描 themes/
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith('.json'):
                    name = os.path.splitext(f)[0]
                    self._add_action(
                        self.theme_menu, name, None,
                        lambda checked=False, n=name:
                        self._apply_theme_by_name(n)
                    )

        self.theme_menu.addSeparator()

        # 编辑 / 市场 / 导入 / 导出 / 删除
        self._add_action(
            self.theme_menu, "📝 编辑当前主题...", None,
            self._show_theme_editor
        )
        self._add_action(
            self.theme_menu, "🎨 主题市场...", None,
            self._show_theme_market
        )
        self.theme_menu.addSeparator()
        self._add_action(
            self.theme_menu, "📥 导入主题包...", None,
            self._import_theme_pack
        )
        self._add_action(
            self.theme_menu, "📤 导出当前主题...", None,
            self._export_theme_pack
        )
        self.theme_menu.addSeparator()
        self._add_action(
            self.theme_menu, "📁 打开主题目录", None,
            self._open_theme_dir
        )

    def _apply_theme_by_name(self, name: str):
        """按名称应用主题"""
        try:
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()

            if name == "__system__":
                loader.apply_system_theme(
                    QApplication.instance(),
                    self.tabs.currentWidget()
                )
                self.status_bar.showMessage("已切换到跟随系统", 2000)
                return

            theme = loader.load_by_name(name)
            if not theme:
                self._show_error("主题加载失败", f"未找到主题: {name}")
                return

            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)
            if theme.qss:
                self.setStyleSheet(theme.qss)

            # 持久化
            from PyQt5.QtCore import QSettings
            settings = QSettings("QingCao", "Editor")
            settings.setValue("theme_name", name)

            self.status_bar.showMessage(f"主题已切换: {name}", 2000)
        except Exception as e:
            self._show_error("主题切换失败", str(e))

    def _show_theme_editor(self):
        """打开主题编辑器（含实时预览）"""
        try:
            from ui.theme_editor import ThemeEditor
            dlg = ThemeEditor(self)

            # 保存后立即应用 + 刷新主题菜单
            def on_saved(path):
                try:
                    from infrastructure.theme_loader import ThemeLoader
                    loader = ThemeLoader()
                    theme = loader.load(path)
                    if theme:
                        for i in range(self.tabs.count()):
                            loader.apply(self.tabs.widget(i), theme)
                        if theme.qss:
                            self.setStyleSheet(theme.qss)
                    # 重新构建菜单
                    self.theme_menu.clear()
                    self._build_full_theme_menu()
                except Exception as e:
                    print(f"[ThemeEditor] 保存后应用失败: {e}")

            dlg.theme_saved.connect(on_saved)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开主题编辑器失败", str(e))

    def _show_theme_market(self):
        """打开主题市场"""
        try:
            from ui.theme_market import ThemeMarketDialog
            dlg = ThemeMarketDialog(self, self)

            def on_installed(name):
                # 刷新菜单
                self.theme_menu.clear()
                self._build_full_theme_menu()

            def on_deleted(name):
                self.theme_menu.clear()
                self._build_full_theme_menu()

            dlg.theme_installed.connect(on_installed)
            dlg.theme_deleted.connect(on_deleted)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开主题市场失败", str(e))

    def _import_theme_pack(self):
        """导入主题包（zip）"""
        try:
            from core.theme_pack import ThemePack
            from PyQt5.QtWidgets import QFileDialog

            path, _ = QFileDialog.getOpenFileName(
                self, "导入主题包", "",
                "主题包 (*.zip);;所有文件 (*.*)"
            )
            if not path:
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "themes"
            )
            ok, msg = ThemePack.import_theme(path, themes_dir)
            if ok:
                QMessageBox.information(self, "成功", msg)
                # 刷新菜单
                self.theme_menu.clear()
                self._build_full_theme_menu()
            else:
                QMessageBox.warning(self, "导入失败", msg)
        except Exception as e:
            self._show_error("导入失败", str(e))

    def _export_theme_pack(self):
        """导出当前主题为 zip 包"""
        try:
            from core.theme_pack import ThemePack
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QFileDialog

            settings = QSettings("QingCao", "Editor")
            theme_name = settings.value("theme_name", "", type=str)
            if not theme_name:
                self._show_info("提示", "当前没有选中主题")
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "themes"
            )
            source = os.path.join(themes_dir, f"{theme_name}.json")
            if not os.path.exists(source):
                self._show_error("导出失败", f"主题文件不存在: {source}")
                return

            path, _ = QFileDialog.getSaveFileName(
                self, "导出主题包",
                f"{theme_name}.zip",
                "主题包 (*.zip)"
            )
            if not path:
                return

            ok, msg = ThemePack.export_theme(source, path)
            if ok:
                QMessageBox.information(self, "成功", msg)
            else:
                QMessageBox.warning(self, "导出失败", msg)
        except Exception as e:
            self._show_error("导出失败", str(e))

    def _open_theme_dir(self):
        """打开主题目录"""
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(themes_dir))

    def _show_preferences(self):
        """打开首选项面板"""
        try:
            from ui.preferences_panel import PreferencesDialog
            dlg = PreferencesDialog(self, self)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开首选项失败", str(e))

    def _add_action(self, menu: QMenu, text: str, shortcut: Optional[str],
                     slot) -> QAction:'''


PATCHES = [
    ("1", "视图菜单加主题子菜单",
     PATCH_1_MARKER, PATCH_1_OLD, PATCH_1_NEW),
    ("2", "工具菜单加首选项入口",
     PATCH_2_MARKER, PATCH_2_OLD, PATCH_2_NEW),
    ("3", "加主题相关槽函数",
     PATCH_3_MARKER, PATCH_3_OLD, PATCH_3_NEW),
]


# ============================================================
# 校验
# ============================================================
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

    print_header("主题功能完整补丁")
    print(f"  目标文件: {TARGET.relative_to(ROOT) if TARGET.exists() else TARGET}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    # 前置检查
    missing = []
    for rel in ["ui/theme_editor.py", "ui/theme_market.py",
                "ui/preferences_panel.py", "core/theme_pack.py",
                "resources/theme_fallback.json"]:
        if not (ROOT / rel).exists():
            missing.append(rel)

    if missing:
        print()
        print_fail("缺少以下前置文件：")
        for m in missing:
            print(f"      - {m}")
        print()
        print_info("请先创建这些文件后再运行补丁脚本。")
        return 1

    print_ok("前置文件齐全")

    if not TARGET.exists():
        print_fail(f"目标文件不存在: {TARGET}")
        return 1

    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    print()
    print("=" * 60)
    print("检查补丁状态")
    print("=" * 60)

    need_apply = []
    for pid, name, marker, old, new in PATCHES:
        applied = marker in content
        print(f"  补丁 {pid}（{name}）: {'已应用' if applied else '未应用'}")
        if not applied:
            cnt = content.count(old)
            if cnt == 0:
                print(f"    [FAIL] 锚点未找到")
                for line in old.split('\n')[:4]:
                    print(f"      | {line}")
                return 1
            if cnt > 1:
                print(f"    [FAIL] 锚点重复 {cnt} 次")
                return 1
            need_apply.append((pid, name, old, new))

    if not need_apply:
        print()
        print_skip("所有补丁均已应用")
        return 0

    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 会应用 {len(need_apply)} 处修改：")
        for pid, name, _, _ in need_apply:
            print_info(f"  {pid}. {name}")
        return 0

    print()
    print("=" * 60)
    print("应用补丁")
    print("=" * 60)

    new_content = content
    for pid, name, old, new in need_apply:
        new_content = new_content.replace(old, new, 1)
        print_ok(f"{pid}. {name}")

    ok, err = validate_python(new_content, str(TARGET))
    if not ok:
        print_fail(f"语法错误: {err}")
        return 1
    print_ok("语法验证通过")

    if not args.no_backup:
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(TARGET, backup)
            print_info(f"已备份: {backup.name}")

    try:
        TARGET.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok(f"已写回: {TARGET.relative_to(ROOT)}")
    except Exception as e:
        print_fail(f"写回失败: {e}")
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if backup.exists():
            shutil.copy2(backup, TARGET)
            print_info("已从备份还原")
        return 1

    print()
    print("=" * 60)
    print("✓ 补丁完成")
    print("=" * 60)
    print()
    print("菜单变化：")
    print("  视图 → 🎨 主题 → 跟随系统")
    print("                    ─────")
    print("                    暗夜 / 晨曦 / 护眼 / 高对比度")
    print("                    ─────")
    print("                    📝 编辑当前主题...")
    print("                    🎨 主题市场...")
    print("                    📥 导入主题包...")
    print("                    📤 导出当前主题...")
    print("                    📁 打开主题目录")
    print()
    print("  工具 → ⚙ 首选项...    (Ctrl+,)")
    print()
    print("下一步:")
    print("  python main.py")

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