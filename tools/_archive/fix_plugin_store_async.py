#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - plugin_store.py 异步加载修复
============================================================
修复：打开插件市场时窗口"(未响应)"30~60 秒。

现象：
    PluginStoreDialog 打开后，主窗口标题栏显示"(未响应)"，
    直到网络请求超时并 fallback 到本地扫描才恢复。

原因：
    ui/plugin_store.py 中所有网络请求都在主线程同步执行：
      1. QTimer.singleShot(100, self._load_plugins) 在事件循环里触发
      2. _load_plugins → get_all_plugins → fetch_registry
      3. fetch_registry 顺序请求主 URL + fallback URL
      4. 每次 requests.get(timeout=30)
      5. 30~60 秒内 Qt 事件循环被完全阻塞

修复：
    1. 缩短 DOWNLOAD_TIMEOUT: 30 → 5 秒
    2. 新增 RegistryFetchWorker（QThread）异步拉远程
    3. _load_plugins 改为：先立即显示本地，再后台拉远程
    4. 后台完成后通过信号刷新列表

特性：
    - 幂等
    - 备份为 *.bak.async
    - 修改后 compile() 验证
    - 失败自动回滚
    - 原子性：所有锚点先检查，全通过才写回

用法：
    python fix_plugin_store_async.py --dry-run
    python fix_plugin_store_async.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "ui" / "plugin_store.py"
BACKUP_SUFFIX = ".bak.async"


# ============================================================
# 输出
# ============================================================
def print_header(t: str):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m: str):
    print(f"  [OK]   {m}")


def print_skip(m: str):
    print(f"  [SKIP] {m}")


def print_fail(m: str):
    print(f"  [FAIL] {m}")


def print_info(m: str):
    print(f"  [INFO] {m}")


# ============================================================
# 补丁定义
# ============================================================
# 补丁 1：缩短超时
PATCH_1_MARKER = "DOWNLOAD_TIMEOUT = 5"
PATCH_1_OLD = "DOWNLOAD_TIMEOUT = 30"
PATCH_1_NEW = "DOWNLOAD_TIMEOUT = 5"


# 补丁 2：_load_plugins 改为异步
PATCH_2_MARKER = "def _load_plugins(self, force=False):\n        \"\"\"加载插件列表（异步）"

PATCH_2_OLD = """    def _load_plugins(self, force: bool = False):
        \"\"\"加载插件列表\"\"\"
        self.status_label.setText("正在加载插件列表...")
        self.refresh_btn.setEnabled(False)

        try:
            self._all_plugins = self.client.get_all_plugins(force=force)
            self._apply_filters()

            self.status_label.setText(
                f"共 {len(self._all_plugins)} 个插件"
            )

        except Exception as e:
            self.status_label.setText(f"加载失败: {e}")
            QMessageBox.warning(self, "加载失败", str(e))

        finally:
            self.refresh_btn.setEnabled(True)"""

PATCH_2_NEW = '''    def _load_plugins(self, force: bool = False):
        """加载插件列表（异步）。

        修复说明（异步加载）:
            原实现同步调用 get_all_plugins()，内部 fetch_registry()
            会顺序请求主 URL + fallback URL，每次 requests.get()
            超时 30 秒 → 主线程被阻塞 30~60 秒，窗口"未响应"。

            新实现分两步：
              1. 立即同步加载本地插件（毫秒级）并显示
              2. 后台线程拉远程注册表，完成后通过信号回传刷新
        """
        # ---- 第 1 步：立即显示本地插件 ----
        self.status_label.setText("正在扫描本地插件...")
        self.refresh_btn.setEnabled(False)

        try:
            local_plugins = self.client.scan_local_plugins()
            # 用本地插件初始化列表（不含远程元数据）
            self._all_plugins = list(local_plugins.values())
            for p in self._all_plugins:
                if p.state.value if hasattr(p.state, 'value') else True:
                    p.state = PluginState.INSTALLED
            self._apply_filters()

            self.status_label.setText(
                f"已加载 {len(self._all_plugins)} 个本地插件，"
                f"正在拉取远程列表..."
            )
        except Exception as e:
            print(f"[PluginStore] 加载本地插件失败: {e}")
            self._all_plugins = []
            self._apply_filters()

        # ---- 第 2 步：后台拉远程 ----
        # 用 QThread 避免阻塞主线程。
        self._registry_worker = RegistryFetchWorker(
            self.client, force=force, parent=self
        )
        self._registry_worker.finished.connect(
            self._on_registry_loaded
        )
        self._registry_worker.failed.connect(
            self._on_registry_failed
        )
        self._registry_worker.start()

    def _on_registry_loaded(self, registry: dict):
        """后台拉取远程注册表成功"""
        try:
            # 重新合并远程 + 本地
            self._all_plugins = self.client.get_all_plugins(force=False)
            self._apply_filters()
            self.status_label.setText(
                f"共 {len(self._all_plugins)} 个插件"
            )
        except Exception as e:
            print(f"[PluginStore] 合并远程插件失败: {e}")
        finally:
            self.refresh_btn.setEnabled(True)

    def _on_registry_failed(self, error: str):
        """后台拉取远程注册表失败（已 fallback 到本地）"""
        print(f"[PluginStore] 远程注册表不可用: {error}")
        self.status_label.setText(
            f"共 {len(self._all_plugins)} 个插件（离线模式）"
        )
        self.refresh_btn.setEnabled(True)'''


# 补丁 3：新增 RegistryFetchWorker 类
PATCH_3_MARKER = "class RegistryFetchWorker(QThread):"

# 插入到 PluginDetailDialog 类定义之前（v2.4 版本里这个类存在）
PATCH_3_ANCHOR = """# ============================================================
# 插件详情对话框
# ============================================================
class PluginDetailDialog(QDialog):"""

PATCH_3_NEW = '''# ============================================================
# 远程注册表异步拉取 Worker
# ============================================================
class RegistryFetchWorker(QThread):
    """
    后台拉取远程注册表。

    修复说明（异步加载）:
        避免在 QTimer.singleShot 回调中同步执行网络请求，
        导致 Qt 事件循环阻塞、窗口"未响应"。

    信号：
        finished(dict): 成功拉取到注册表
        failed(str):    拉取失败（已 fallback 到磁盘缓存）
    """

    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client, force: bool = False, parent=None):
        super().__init__(parent)
        self.client = client
        self.force = force

    def run(self):
        try:
            registry = self.client.fetch_registry(force=self.force)
            if registry:
                self.finished.emit(registry)
            else:
                self.failed.emit("无法获取注册表（网络与缓存均失败）")
        except Exception as e:
            self.failed.emit(str(e))


# ============================================================
# 插件详情对话框
# ============================================================
class PluginDetailDialog(QDialog):'''


PATCHES = [
    ("1", "缩短 DOWNLOAD_TIMEOUT 到 5 秒",
     PATCH_1_MARKER, PATCH_1_OLD, PATCH_1_NEW),

    ("2", "_load_plugins 改为异步（本地优先 + 后台拉远程）",
     PATCH_2_MARKER, PATCH_2_OLD, PATCH_2_NEW),

    ("3", "新增 RegistryFetchWorker 类",
     PATCH_3_MARKER, PATCH_3_ANCHOR, PATCH_3_NEW),
]


# ============================================================
# 校验与应用
# ============================================================
def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="plugin_store.py 异步加载修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("plugin_store.py 异步加载修复")
    print(f"  项目目录: {ROOT}")
    print(f"  目标文件: {TARGET.relative_to(ROOT) if TARGET.exists() else TARGET}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    if not TARGET.exists():
        print_fail(f"目标文件不存在: {TARGET}")
        print()
        print("  可能路径：")
        for guess in [
            ROOT / "ui" / "plugin_store.py",
            ROOT / "ui" / "plugin_market.py",
            ROOT / "app" / "plugin_store.py",
        ]:
            marker = "✓" if guess.exists() else " "
            print(f"    [{marker}] {guess.relative_to(ROOT)}")
        return 1

    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    # ---- 检查所有补丁状态 ----
    print()
    print("=" * 60)
    print("检查补丁状态")
    print("=" * 60)

    need_apply: List[Tuple[str, str, str, str, str]] = []
    all_applied = True

    for pid, name, marker, old, new in PATCHES:
        applied = marker in content
        status = "已应用" if applied else "未应用"
        print(f"  补丁 {pid}（{name}）: {status}")
        if not applied:
            all_applied = False
            # 检查锚点
            cnt = content.count(old)
            if cnt == 0:
                print(f"    [FAIL] 锚点未找到")
                print(f"    期望：")
                for line in old.split('\n')[:6]:
                    print(f"      | {line}")
                return 1
            if cnt > 1:
                print(f"    [FAIL] 锚点重复 {cnt} 次")
                return 1
            need_apply.append((pid, name, marker, old, new))

    if all_applied:
        print()
        print_skip("所有补丁均已应用，无需修改")
        return 0

    # ---- DRY-RUN ----
    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 会应用 {len(need_apply)} 处修改：")
        for pid, name, _, _, _ in need_apply:
            print_info(f"  {pid}. {name}")
        return 0

    # ---- 应用（原子性：全部成功才写回）----
    print()
    print("=" * 60)
    print("应用补丁")
    print("=" * 60)

    new_content = content
    for pid, name, marker, old, new in need_apply:
        try:
            new_content = new_content.replace(old, new, 1)
            print_ok(f"{pid}. {name}")
        except Exception as e:
            print_fail(f"{pid}. {name}: {e}")
            return 1

    # ---- 语法验证 ----
    print()
    print("=" * 60)
    print("语法验证")
    print("=" * 60)

    ok, err = validate_python(new_content, str(TARGET))
    if not ok:
        print_fail(f"语法错误: {err}")
        print_info("文件未修改")
        return 1
    print_ok("语法验证通过")

    # ---- 检查 pyqtSignal / QThread 是否已导入 ----
    print()
    print("=" * 60)
    print("依赖检查")
    print("=" * 60)

    if "QThread" not in new_content.split("class RegistryFetchWorker")[0]:
        # 检查 import 语句
        if "from PyQt5.QtCore import" in new_content:
            import re
            m = re.search(
                r'from PyQt5\.QtCore import ([^\n]+)',
                new_content
            )
            if m and "QThread" not in m.group(1):
                print_info("QThread 未导入，正在补齐...")
                new_content = re.sub(
                    r'from PyQt5\.QtCore import ([^\n]+)',
                    lambda mo: f"from PyQt5.QtCore import {mo.group(1)}, QThread",
                    new_content, count=1
                )
                # 重新验证
                ok, err = validate_python(new_content, str(TARGET))
                if not ok:
                    print_fail(f"补 QThread 导入后语法错误: {err}")
                    return 1
                print_ok("已补齐 QThread 导入")
            else:
                print_ok("QThread 已导入")
        else:
            print_info("未找到 PyQt5.QtCore 导入，请手动添加 QThread")
    else:
        print_ok("QThread 已导入")

    if "pyqtSignal" not in new_content.split("class RegistryFetchWorker")[0]:
        if "from PyQt5.QtCore import" in new_content:
            import re
            m = re.search(
                r'from PyQt5\.QtCore import ([^\n]+)',
                new_content
            )
            if m and "pyqtSignal" not in m.group(1):
                print_info("pyqtSignal 未导入，正在补齐...")
                new_content = re.sub(
                    r'from PyQt5\.QtCore import ([^\n]+)',
                    lambda mo: f"from PyQt5.QtCore import {mo.group(1)}, pyqtSignal",
                    new_content, count=1
                )
                ok, err = validate_python(new_content, str(TARGET))
                if not ok:
                    print_fail(f"补 pyqtSignal 导入后语法错误: {err}")
                    return 1
                print_ok("已补齐 pyqtSignal 导入")
            else:
                print_ok("pyqtSignal 已导入")
    else:
        print_ok("pyqtSignal 已导入")

    # ---- 备份 + 写回 ----
    print()
    print("=" * 60)
    print("写回文件")
    print("=" * 60)

    if not args.no_backup:
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(TARGET, backup)
                print_info(f"已备份: {backup.name}")
            except Exception as e:
                print_fail(f"备份失败: {e}")
                return 1
        else:
            print_info(f"备份已存在: {backup.name}")

    try:
        TARGET.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok(f"已写回: {TARGET.relative_to(ROOT)}")
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
    print("  python -c \"import ast; ast.parse("
          "open('ui/plugin_store.py', encoding='utf-8').read()); "
          "print('OK')\"")
    print("  python main.py    # 打开插件市场，应不再卡顿")

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