#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - plugin_store.py 本地注册表兜底
============================================================
修复：qingcao-editor/plugins-registry 仓库不存在，
      导致插件市场总是空列表。

方案：
    远程全部失败时，读取 resources/registry_fallback.json。

特性：
    - 幂等
    - 备份为 *.bak.localreg
    - 修改后 compile() 验证
    - 原子性：所有锚点先检查，全部通过才写回

用法：
    python fix_registry_fallback.py --dry-run
    python fix_registry_fallback.py
    python fix_registry_fallback.py --no-backup
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "ui" / "plugin_store.py"
FALLBACK_FILE = ROOT / "resources" / "registry_fallback.json"
BACKUP_SUFFIX = ".bak.localreg"


# ============================================================
# 输出辅助
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
# 补丁 1：cache_first 模式读本地兜底
# ============================================================
PATCH_1_MARKER = "# v3.0: cache_first 模式下，退回本地兜底文件"

PATCH_1_OLD = '''        # v2.9: cache_first 模式，只读磁盘缓存（不管 TTL），立即返回
        if cache_first:
            cached = self._load_cache_no_ttl()
            if cached:
                self._registry_cache = cached
                self._registry_cache_time = time.time()
                return cached
            return None'''

PATCH_1_NEW = '''        # v2.9: cache_first 模式，只读磁盘缓存（不管 TTL），立即返回
        if cache_first:
            cached = self._load_cache_no_ttl()
            if cached:
                self._registry_cache = cached
                self._registry_cache_time = time.time()
                return cached
            # v3.0: cache_first 模式下，退回本地兜底文件
            fallback = self._load_fallback_registry()
            if fallback:
                self._registry_cache = fallback
                self._registry_cache_time = time.time()
                return fallback
            return None'''


# ============================================================
# 补丁 2：新增 _load_fallback_registry 方法
# ============================================================
PATCH_2_MARKER = "def _load_fallback_registry(self)"

PATCH_2_OLD = '''    def _load_cache_no_ttl(self) -> Optional[Dict[str, Any]]:
        """
        从磁盘缓存加载，忽略 TTL。'''

PATCH_2_NEW = '''    def _load_fallback_registry(self) -> Optional[Dict[str, Any]]:
        """
        从本地兜底文件加载注册表（v3.0）。

        说明：
            远程注册表仓库可能不存在（qingcao-editor/plugins-registry），
            导致插件市场永远空列表。本方法从本地
            resources/registry_fallback.json 读取内置的插件推荐列表，
            作为离线兜底。
        """
        try:
            # 定位 resources/registry_fallback.json
            # 当前文件在 ui/ 下，根目录是上一级
            root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            fallback_path = os.path.join(
                root, "resources", "registry_fallback.json"
            )

            if not os.path.exists(fallback_path):
                return None

            with open(fallback_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return None

            # 打标记，便于 UI 区分
            data['_from_fallback'] = True
            return data

        except Exception as e:
            print(f"[PluginStore] 读取本地兜底注册表失败: {e}")
            return None

    def _load_cache_no_ttl(self) -> Optional[Dict[str, Any]]:
        """
        从磁盘缓存加载，忽略 TTL。'''


# ============================================================
# 补丁 3：远程全部失败时读本地兜底
# ============================================================
PATCH_3_MARKER = "# v3.0: 远程全部失败，先读磁盘缓存"

PATCH_3_OLD = '''        # 尝试从磁盘缓存加载
        cached = self._load_cache()
        if cached:
            return cached

        return None'''

PATCH_3_NEW = '''        # v3.0: 远程全部失败，先读磁盘缓存
        cached = self._load_cache()
        if cached:
            return cached

        # v3.0: 磁盘缓存也没有，读本地兜底文件
        fallback = self._load_fallback_registry()
        if fallback:
            print("[PluginStore] 使用本地兜底注册表")
            return fallback

        return None'''


# 补丁列表（顺序执行）
PATCHES = [
    ("1", "cache_first 模式读本地兜底",
     PATCH_1_MARKER, PATCH_1_OLD, PATCH_1_NEW),
    ("2", "新增 _load_fallback_registry 方法",
     PATCH_2_MARKER, PATCH_2_OLD, PATCH_2_NEW),
    ("3", "远程全部失败时读本地兜底",
     PATCH_3_MARKER, PATCH_3_OLD, PATCH_3_NEW),
]


# ============================================================
# 语法验证
# ============================================================
def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="plugin_store.py 本地注册表兜底"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='预演，不修改文件')
    parser.add_argument('--no-backup', action='store_true',
                        help='不备份原文件')
    args = parser.parse_args()

    print_header("plugin_store.py 本地注册表兜底")
    print(f"  项目目录: {ROOT}")
    print(f"  目标文件: "
          f"{TARGET.relative_to(ROOT) if TARGET.exists() else TARGET}")
    print(f"  兜底文件: "
          f"{FALLBACK_FILE.relative_to(ROOT) if FALLBACK_FILE.exists() else FALLBACK_FILE}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    # ---- 前置检查 1: 目标文件 ----
    if not TARGET.exists():
        print()
        print_fail(f"目标文件不存在: {TARGET}")
        return 1

    # ---- 前置检查 2: 兜底文件 ----
    if not FALLBACK_FILE.exists():
        print()
        print_fail(f"兜底文件不存在: {FALLBACK_FILE.relative_to(ROOT)}")
        print()
        print_info("请先创建 resources/registry_fallback.json")
        print_info("内容参考项目 README 或下方提示：")
        print()
        print("  {")
        print('    "version": "1.0",')
        print('    "plugins": [ ... ],')
        print('    "themes": [ ... ]')
        print("  }")
        return 1

    print()
    print_ok(f"找到兜底文件")

    # ---- 读取目标文件 ----
    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    # ---- 检查补丁状态 ----
    print()
    print("=" * 60)
    print("检查补丁状态")
    print("=" * 60)

    need_apply: List[Tuple[str, str, str, str]] = []
    for pid, name, marker, old, new in PATCHES:
        applied = marker in content
        print(f"  补丁 {pid}（{name}）: "
              f"{'已应用' if applied else '未应用'}")
        if not applied:
            cnt = content.count(old)
            if cnt == 0:
                print(f"    [FAIL] 锚点未找到")
                print(f"    期望锚点：")
                for line in old.split('\n')[:6]:
                    print(f"      | {line}")
                return 1
            if cnt > 1:
                print(f"    [FAIL] 锚点重复出现 {cnt} 次")
                return 1
            need_apply.append((pid, name, old, new))

    if not need_apply:
        print()
        print_skip("所有补丁均已应用，无需修改")
        return 0

    # ---- DRY-RUN ----
    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 会应用 {len(need_apply)} 处修改：")
        for pid, name, _, _ in need_apply:
            print_info(f"  {pid}. {name}")
        return 0

    # ---- 应用（原子性）----
    print()
    print("=" * 60)
    print("应用补丁")
    print("=" * 60)

    new_content = content
    for pid, name, old, new in need_apply:
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

    # ---- 备份 ----
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
            print_info(f"备份已存在: {backup.name}（保留旧备份）")

    # ---- 写回 ----
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

    # ---- 完成 ----
    print()
    print("=" * 60)
    print("✓ 修复完成")
    print("=" * 60)
    print()
    print("行为变化：")
    print("  远程全失败 → 读磁盘缓存 → 读本地兜底 → UI 显示内置列表")
    print()
    print("下一步:")
    print("  python -c \"import ast; ast.parse("
          "open('ui/plugin_store.py', encoding='utf-8').read()); "
          "print('OK')\"")
    print("  python main.py    # 打开插件市场")

    return 0


# ============================================================
# 入口
# ============================================================
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