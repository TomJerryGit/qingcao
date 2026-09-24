#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - plugin_store.py 加注册表 URL 配置输入框
============================================================
功能：在 PluginStoreDialog 工具栏加一行"注册表 URL"输入框，
      允许用户手动指定镜像地址（保存到 QSettings）。

UI 布局：
    [搜索框]  [分类▾]  [排序▾]
    [注册表 URL: ____________________] [应用并刷新]

特性：
    - 幂等
    - 备份为 *.bak.ui
    - 修改后 compile() 验证
    - 原子性

用法：
    python fix_registry_ui.py --dry-run
    python fix_registry_ui.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "ui" / "plugin_store.py"
BACKUP_SUFFIX = ".bak.ui"


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print(f"  [OK]   {m}")


def print_skip(m):
    print(f"  [SKIP] {m}")


def print_fail(m):
    print(f"  [FAIL] {m}")


def print_info(m):
    print(f"  [INFO] {m}")


# ============================================================
# 补丁 1：__init__ 加载用户自定义 URL
# ============================================================
PATCH_1_MARKER = "# v2.9: 从 QSettings 加载自定义注册表 URL"

PATCH_1_OLD = '''        # 客户端
        self.client = PluginStoreClient()

        # 插件列表
        self._all_plugins: List[PluginInfo] = []'''

PATCH_1_NEW = '''        # 客户端
        self.client = PluginStoreClient()

        # v2.9: 从 QSettings 加载自定义注册表 URL
        # 允许用户覆盖默认注册表地址（适配网络环境）
        self._settings = QSettings("QingCao", "PluginStore")
        custom_url = self._settings.value(
            "registry_url", "", type=str
        )
        if custom_url:
            self.client.registry_url = custom_url

        # 插件列表
        self._all_plugins: List[PluginInfo] = []'''


# ============================================================
# 补丁 2：_build_toolbar 加 URL 输入行
# ============================================================
PATCH_2_MARKER = "# v2.9: 注册表 URL 配置行"

PATCH_2_OLD = '''    def _build_toolbar(self) -> QWidget:
        """构建工具栏"""
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)'''

PATCH_2_NEW = '''    def _build_toolbar(self) -> QWidget:
        """构建工具栏（v2.9：两行布局）"""
        toolbar = QWidget()
        outer = QVBoxLayout(toolbar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ====================================================
        # v2.9: 注册表 URL 配置行
        # ====================================================
        url_row = QHBoxLayout()
        url_row.setContentsMargins(0, 0, 0, 0)
        url_row.setSpacing(6)

        url_label = QLabel("注册表 URL:")
        url_label.setStyleSheet("color: #888; font-size: 11px;")
        url_row.addWidget(url_label)

        self.registry_url_edit = QLineEdit()
        self.registry_url_edit.setPlaceholderText(
            "留空使用默认（jsDelivr CDN）"
        )
        self.registry_url_edit.setText(
            self._settings.value("registry_url", "", type=str)
        )
        self.registry_url_edit.setClearButtonEnabled(True)
        self.registry_url_edit.returnPressed.connect(
            self._on_registry_url_changed
        )
        url_row.addWidget(self.registry_url_edit, 1)

        self.apply_url_btn = QPushButton("应用并刷新")
        self.apply_url_btn.clicked.connect(
            self._on_registry_url_changed
        )
        url_row.addWidget(self.apply_url_btn)

        reset_url_btn = QPushButton("重置")
        reset_url_btn.setToolTip("恢复默认注册表地址")
        reset_url_btn.clicked.connect(self._on_reset_registry_url)
        url_row.addWidget(reset_url_btn)

        outer.addLayout(url_row)

        # ====================================================
        # 原有的搜索/分类/排序行
        # ====================================================
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)

        # 临时把 layout 指向 filter_row，后面的 addWidget 会加到这一行
        layout = filter_row'''

PATCH_2_TAIL_MARKER = "# v2.9: 注册表 URL 配置行"

PATCH_2_TAIL_OLD = '''        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        layout.addWidget(self.sort_combo)

        return toolbar'''

PATCH_2_TAIL_NEW = '''        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        layout.addWidget(self.sort_combo)

        # 把 filter_row 加到 toolbar 的 outer 布局
        outer.addLayout(filter_row)

        return toolbar

    # ========================================================
    # v2.9: 注册表 URL 处理
    # ========================================================
    def _on_registry_url_changed(self):
        """用户点击"应用并刷新"或按回车"""
        url = self.registry_url_edit.text().strip()

        # 简单校验
        if url and not (url.startswith("http://")
                        or url.startswith("https://")):
            QMessageBox.warning(
                self, "URL 格式错误",
                "注册表 URL 必须以 http:// 或 https:// 开头"
            )
            return

        # 保存到 QSettings
        if url:
            self._settings.setValue("registry_url", url)
        else:
            self._settings.remove("registry_url")

        # 应用到 client
        if url:
            self.client.registry_url = url
        else:
            # 恢复默认
            self.client.registry_url = DEFAULT_REGISTRY_URL

        # 清缓存并刷新
        self.client.clear_cache()
        self._load_plugins(force=True)

        QMessageBox.information(
            self, "已应用",
            f"注册表地址已更新：\\n{url or '(默认)'}\\n\\n"
            f"正在重新拉取插件列表..."
        )

    def _on_reset_registry_url(self):
        """重置为默认 URL"""
        self.registry_url_edit.clear()
        self._settings.remove("registry_url")
        self.client.registry_url = DEFAULT_REGISTRY_URL
        self.client.clear_cache()
        self._load_plugins(force=True)'''


PATCHES = [
    ("1", "__init__ 加载自定义 URL",
     PATCH_1_MARKER, PATCH_1_OLD, PATCH_1_NEW),
    ("2a", "_build_toolbar 加 URL 配置行",
     PATCH_2_MARKER, PATCH_2_OLD, PATCH_2_NEW),
    ("2b", "_build_toolbar 尾部 + URL 处理方法",
     PATCH_2_TAIL_MARKER, PATCH_2_TAIL_OLD, PATCH_2_TAIL_NEW),
]


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

    print_header("plugin_store.py 加注册表 URL 配置")
    print(f"  目标文件: {TARGET.relative_to(ROOT) if TARGET.exists() else TARGET}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

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

    # 检查依赖
    if "QLabel" not in new_content.split("class PluginStoreDialog")[0]:
        print_info("QLabel 未导入，正在补齐...")
        import re
        # 在 QLineEdit 后面补 QLabel
        if "QLineEdit," in new_content:
            new_content = new_content.replace(
                "QLineEdit,", "QLineEdit, QLabel,", 1
            )

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
    print("✓ 修复完成")
    print("=" * 60)
    print()
    print("UI 变化：")
    print("  ┌─────────────────────────────────────────────────┐")
    print("  │ 注册表 URL: [____________________] [应用并刷新]│")
    print("  │ [搜索插件...]  [分类▾]  [排序▾]                │")
    print("  └─────────────────────────────────────────────────┘")
    print()
    print("用户可以在输入框中填自定义镜像地址，例如：")
    print("  https://your-mirror.com/registry.json")
    print()
    print("下一步:")
    print("  python main.py  # 打开插件市场查看新 UI")

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