#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - plugin_store.py 注册表 URL 镜像优先
============================================================
修复：raw.githubusercontent.com 在国内经常超时，
      导致插件市场加载失败。

方案：
    1. DEFAULT_REGISTRY_URL 改为 jsDelivr CDN（国内可访问）
    2. FALLBACK_REGISTRY_URLS 增加多路兜底

特性：
    - 幂等
    - 备份为 *.bak.registry
    - 修改后 compile() 验证
    - 原子性：全部锚点先检查再应用

用法：
    python fix_registry_urls.py --dry-run
    python fix_registry_urls.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "ui" / "plugin_store.py"
BACKUP_SUFFIX = ".bak.registry"


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
# 补丁定义
# ============================================================
PATCH_1_MARKER = "cdn.jsdelivr.net/gh/"

PATCH_1_OLD = '''# 插件市场注册表地址
DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/"
    "qingcao-editor/plugins-registry/main/registry.json"
)'''

PATCH_1_NEW = '''# 插件市场注册表地址（镜像优先，国内可访问）
# 优先级：jsDelivr CDN > 用户自定义 > FALLBACK 列表
# 用户可在"插件市场"的"注册表 URL"输入框中覆盖此默认值
DEFAULT_REGISTRY_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "qingcao-editor/plugins-registry@main/registry.json"
)'''


PATCH_2_MARKER = "# Statically CDN（第三兜底）"

PATCH_2_OLD = '''# 备用注册表地址
FALLBACK_REGISTRY_URLS = [
    "https://gitee.com/qingcao-editor/plugins-registry/raw/main/registry.json",
]'''

PATCH_2_NEW = '''# 备用注册表地址（多路兜底）
FALLBACK_REGISTRY_URLS = [
    # GitHub 原始地址（国外/代理环境）
    "https://raw.githubusercontent.com/"
    "qingcao-editor/plugins-registry/main/registry.json",
    # Gitee 镜像（国内）
    "https://gitee.com/qingcao-editor/plugins-registry/raw/main/registry.json",
    # Statically CDN（第三兜底）
    "https://cdn.statically.io/gh/"
    "qingcao-editor/plugins-registry/main/registry.json",
]'''


PATCHES = [
    ("1", "DEFAULT_REGISTRY_URL 改为 jsDelivr CDN",
     PATCH_1_MARKER, PATCH_1_OLD, PATCH_1_NEW),
    ("2", "FALLBACK_REGISTRY_URLS 增加多路兜底",
     PATCH_2_MARKER, PATCH_2_OLD, PATCH_2_NEW),
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

    print_header("plugin_store.py 注册表 URL 镜像优先")
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

    # 语法验证
    ok, err = validate_python(new_content, str(TARGET))
    if not ok:
        print_fail(f"语法错误: {err}")
        return 1
    print_ok("语法验证通过")

    # 备份 + 写回
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
    print("新的 URL 优先级：")
    print("  1. jsDelivr CDN       (https://cdn.jsdelivr.net/...)")
    print("  2. GitHub raw         (https://raw.githubusercontent.com/...)")
    print("  3. Gitee              (https://gitee.com/...)")
    print("  4. Statically CDN     (https://cdn.statically.io/...)")
    print()
    print("下一步:")
    print("  python main.py  # 重新打开插件市场")

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