#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断插件注册表 URL 可达性。

用法:
    python diagnose_registry.py
"""

import time
from typing import Tuple


URLS = [
    ("jsDelivr CDN（当前默认）",
     "https://cdn.jsdelivr.net/gh/"
     "qingcao-editor/plugins-registry@main/registry.json"),
    ("GitHub raw",
     "https://raw.githubusercontent.com/"
     "qingcao-editor/plugins-registry/main/registry.json"),
    ("Gitee 镜像",
     "https://gitee.com/qingcao-editor/"
     "plugins-registry/raw/main/registry.json"),
    ("Statically CDN",
     "https://cdn.statically.io/gh/"
     "qingcao-editor/plugins-registry/main/registry.json"),
]


def test_url(url: str, timeout: int = 5) -> Tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "缺少 requests 库"

    start = time.time()
    try:
        resp = requests.get(url, timeout=timeout)
        elapsed = (time.time() - start) * 1000

        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code} · {elapsed:.0f}ms"

        try:
            data = resp.json()
        except Exception:
            preview = resp.text[:60].replace('\n', ' ')
            return False, f"HTTP 200 但非 JSON: {preview}"

        if not isinstance(data, dict):
            return False, f"HTTP 200 但顶层不是 dict"

        plugins = data.get('plugins', [])
        return True, f"HTTP 200 · {len(plugins)} 个插件 · {elapsed:.0f}ms"

    except requests.exceptions.Timeout:
        return False, f"超时（>{timeout}s）"
    except requests.exceptions.ConnectionError as e:
        return False, f"连接失败: {str(e)[:60]}"
    except Exception as e:
        return False, f"异常: {str(e)[:60]}"


def main():
    print("=" * 70)
    print("注册表 URL 可达性诊断")
    print("=" * 70)
    print()

    success = 0
    results = []

    for name, url in URLS:
        ok, detail = test_url(url)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {name}")
        print(f"      {detail}")
        results.append((ok, name, url))
        if ok:
            success += 1
        print()

    print("=" * 70)
    print(f"结果：{success}/{len(URLS)} 个 URL 可用")
    print("=" * 70)
    print()

    if success == 0:
        print("所有 URL 都不可用。先排除是不是网络问题：")
        print()
        print("  1. 测试基本网络:")
        print("     ping 8.8.8.8")
        print()
        print("  2. 测试能否访问 GitHub:")
        print("     curl https://github.com")
        print()
        print("  3. 如果 GitHub 通但 raw 不通，说明是 CDN 被墙")
        print()
        print("如果网络本身正常，说明注册表仓库不存在：")
        print("      https://github.com/qingcao-editor/plugins-registry")
        print()
        print("这种情况下的建议：")
        print("  A. 接受离线模式（本地插件仍可用）")
        print("  B. 自己建一个 registry.json 仓库")
        print("  C. 打开插件市场，在'注册表 URL'输入框填入可用的地址")
        print()
    else:
        print("可用的 URL：")
        for ok, name, url in results:
            if ok:
                print(f"  ✓ {name}")
                print(f"    {url}")
        print()
        print("打开插件市场 → 在'注册表 URL'输入框填入上述地址 → 应用并刷新")
        print()


if __name__ == "__main__":
    main()