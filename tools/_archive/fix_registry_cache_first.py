#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - plugin_store.py 缓存优先
============================================================
修复：第二次启动时，即使磁盘缓存已存在，仍会先等 5 秒
      网络超时才回退到缓存。

方案：
    1. PluginStoreClient.fetch_registry 增加 cache_first 参数
    2. 新增 _load_cache_no_ttl 方法（忽略 TTL）
    3. PluginStoreDialog._load_plugins 用 cache_first=True
       快速加载本地 + 磁盘缓存，后台 Worker 再用 force=True 刷新

效果：
    - 首次启动：无缓存 → 等 5 秒网络超时 → 显示本地插件
    - 之后启动：有缓存 → 立即显示本地 + 缓存插件 → 后台静默刷新

特性：
    - 幂等
    - 备份为 *.bak.cachefirst
    - 修改后 compile() 验证
    - 原子性

用法：
    python fix_registry_cache_first.py --dry-run
    python fix_registry_cache_first.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "ui" / "plugin_store.py"
BACKUP_SUFFIX = ".bak.cachefirst"


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
# 补丁 1：fetch_registry 增加 cache_first 参数
# ============================================================
PATCH_1_MARKER = "def fetch_registry(self, force: bool = False,\n                      cache_first: bool = False)"

PATCH_1_OLD = '''    def fetch_registry(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        拉取远程注册表。

        参数:
            force: 强制刷新（忽略缓存）

        返回:
            注册表数据或 None
        """
        # 检查缓存
        if not force and self._registry_cache is not None:
            elapsed = time.time() - self._registry_cache_time
            if elapsed < CACHE_TTL:
                return self._registry_cache

        # 从远程拉取
        urls = [self.registry_url] + FALLBACK_REGISTRY_URLS

        for url in urls:
            try:
                data = self._download_json(url)
                if data:
                    self._registry_cache = data
                    self._registry_cache_time = time.time()
                    self._save_cache(data)
                    return data
            except Exception as e:
                print(f"[PluginStore] 拉取注册表失败 ({url}): {e}")
                continue

        # 尝试从磁盘缓存加载
        cached = self._load_cache()
        if cached:
            return cached

        return None'''

PATCH_1_NEW = '''    def fetch_registry(self, force: bool = False,
                       cache_first: bool = False
                       ) -> Optional[Dict[str, Any]]:
        """
        拉取远程注册表。

        参数:
            force: 强制刷新（忽略内存缓存 TTL）
            cache_first:
                True  → 只读内存 + 磁盘缓存，不发起网络请求；
                        网络拉取由调用方在后台线程用 force=True 处理。
                False → 完整流程：内存缓存 → 网络 → 磁盘缓存。

        返回:
            注册表数据或 None
        """
        # 检查内存缓存
        if not force and self._registry_cache is not None:
            elapsed = time.time() - self._registry_cache_time
            if elapsed < CACHE_TTL:
                return self._registry_cache

        # v2.9: cache_first 模式，只读磁盘缓存（不管 TTL），立即返回
        if cache_first:
            cached = self._load_cache_no_ttl()
            if cached:
                self._registry_cache = cached
                self._registry_cache_time = time.time()
                return cached
            return None

        # 从远程拉取
        urls = [self.registry_url] + FALLBACK_REGISTRY_URLS

        for url in urls:
            try:
                data = self._download_json(url)
                if data:
                    self._registry_cache = data
                    self._registry_cache_time = time.time()
                    self._save_cache(data)
                    return data
            except Exception as e:
                print(f"[PluginStore] 拉取注册表失败 ({url}): {e}")
                continue

        # 尝试从磁盘缓存加载
        cached = self._load_cache()
        if cached:
            return cached

        return None'''


# ============================================================
# 补丁 2：新增 _load_cache_no_ttl 方法
# ============================================================
PATCH_2_MARKER = "def _load_cache_no_ttl(self)"

PATCH_2_OLD = '''    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """从磁盘缓存加载"""'''

PATCH_2_NEW = '''    def _load_cache_no_ttl(self) -> Optional[Dict[str, Any]]:
        """
        从磁盘缓存加载，忽略 TTL。

        v2.9 新增：用于 cache_first 模式。
        即使缓存过期很久也返回，让 UI 立即有数据可显示；
        真正的刷新由后台线程负责。
        """
        try:
            cache_file = os.path.join(self.cache_dir, "registry.json")
            if not os.path.exists(cache_file):
                return None

            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)

            data = cached.get('data')
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """从磁盘缓存加载（受 TTL 限制）"""'''


# ============================================================
# 补丁 3：_load_plugins 用 cache_first
# ============================================================
PATCH_3_MARKER = "cache_first=True"

PATCH_3_OLD = '''        try:
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
            self._apply_filters()'''

PATCH_3_NEW = '''        try:
            # v2.9: 先用 cache_first 快速合并（本地 + 磁盘缓存）
            # 不发起网络请求，确保 UI 立即有内容
            try:
                fast_registry = self.client.fetch_registry(
                    force=False, cache_first=True
                )
            except Exception:
                fast_registry = None

            if fast_registry:
                # 有磁盘缓存：一次性合并远程 + 本地
                self._all_plugins = self.client.get_all_plugins(
                    force=False
                )
                self.status_label.setText(
                    f"已从缓存加载 {len(self._all_plugins)} 个插件，"
                    f"后台刷新中..."
                )
            else:
                # 无缓存：只显示本地
                local_plugins = self.client.scan_local_plugins()
                self._all_plugins = list(local_plugins.values())
                for p in self._all_plugins:
                    p.state = PluginState.INSTALLED
                self.status_label.setText(
                    f"已加载 {len(self._all_plugins)} 个本地插件，"
                    f"正在拉取远程列表..."
                )
            self._apply_filters()

        except Exception as e:
            print(f"[PluginStore] 加载插件失败: {e}")
            self._all_plugins = []
            self._apply_filters()'''


PATCHES = [
    ("1", "fetch_registry 增加 cache_first 参数",
     PATCH_1_MARKER, PATCH_1_OLD, PATCH_1_NEW),
    ("2", "新增 _load_cache_no_ttl 方法",
     PATCH_2_MARKER, PATCH_2_OLD, PATCH_2_NEW),
    ("3", "_load_plugins 用 cache_first 快速加载",
     PATCH_3_MARKER, PATCH_3_OLD, PATCH_3_NEW),
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

    print_header("plugin_store.py 缓存优先")
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
    print("行为变化：")
    print("  首次启动  : 无缓存 → 5 秒超时 → 显示本地插件")
    print("  之后启动  : 有缓存 → 立即显示本地+缓存 → 后台刷新")

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