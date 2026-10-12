#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
代理环境变量诊断 + Ollama 连通性测试
============================================================
1. 打印所有 HTTP 代理相关环境变量
2. 用 requests 分别在【走代理】和【禁用代理】下测试 Ollama
3. 给出结论和修复建议

用法：
    python tools/diagnose_proxy.py
============================================================
"""

import os
import sys
import time


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_warn(m):
    print("  [WARN] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def print_info(m):
    print("  [INFO] " + m)


def show_proxy_env():
    """显示所有代理相关环境变量"""
    print_header("1. 代理环境变量")

    proxy_keys = [
        'HTTP_PROXY', 'http_proxy',
        'HTTPS_PROXY', 'https_proxy',
        'ALL_PROXY', 'all_proxy',
        'NO_PROXY', 'no_proxy',
        'FTP_PROXY', 'ftp_proxy',
    ]

    found = False
    for k in proxy_keys:
        v = os.environ.get(k)
        if v:
            print_warn(f"{k} = {v!r}")
            found = True

    if not found:
        print_ok("未发现任何代理环境变量")

    return found


def test_ollama(use_proxy: bool, timeout: int = 15) -> bool:
    """测试 Ollama 连通性"""
    try:
        import requests
    except ImportError:
        print_fail("缺少 requests 库")
        return False

    url = "http://localhost:11434/v1/chat/completions"
    payload = {
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 16,
    }
    headers = {"Content-Type": "application/json"}

    label = "走代理" if use_proxy else "禁用代理"
    print_info(f"测试 ({label}): {url}")

    if use_proxy:
        # 默认行为（读环境变量）
        proxies = None
    else:
        # 显式禁用代理
        proxies = {"http": None, "https": None}

    start = time.time()
    try:
        resp = requests.post(
            url, json=payload, headers=headers,
            timeout=timeout, proxies=proxies,
        )
        elapsed = (time.time() - start) * 1000
        if resp.status_code == 200:
            try:
                content = resp.json()['choices'][0]['message']['content']
            except Exception:
                content = resp.text[:80]
            print_ok(f"HTTP 200 ({elapsed:.0f} ms): {content[:60]}")
            return True
        else:
            print_fail(f"HTTP {resp.status_code} ({elapsed:.0f} ms)")
            print_fail(f"响应: {resp.text[:200]}")
            return False
    except requests.exceptions.Timeout:
        print_fail(f"超时（>{timeout} 秒）")
        return False
    except requests.exceptions.ProxyError as e:
        print_fail(f"代理错误: {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        print_fail(f"连接错误: {e}")
        return False
    except Exception as e:
        print_fail(f"异常: {type(e).__name__}: {e}")
        return False


def test_direct_socket(timeout: int = 5) -> bool:
    """用原生 socket 测试（完全绕过代理）"""
    import socket

    print_info("原生 socket 测试: localhost:11434")
    start = time.time()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(("127.0.0.1", 11434))
        s.close()
        elapsed = (time.time() - start) * 1000
        print_ok(f"TCP 连接成功 ({elapsed:.0f} ms)")
        return True
    except Exception as e:
        print_fail(f"TCP 连接失败: {e}")
        return False


def main():
    print_header("Ollama 代理诊断")

    # ---- 1. 环境变量 ----
    has_proxy_env = show_proxy_env()

    # ---- 2. 原生 socket（无代理） ----
    print_header("2. 原生 socket 测试（不走任何代理）")
    socket_ok = test_direct_socket()

    # ---- 3. 走代理 ----
    print_header("3. requests 走代理")
    proxy_ok = test_ollama(use_proxy=True)

    # ---- 4. 禁用代理 ----
    print_header("4. requests 禁用代理")
    direct_ok = test_ollama(use_proxy=False)

    # ---- 5. 结论 ----
    print_header("5. 结论与建议")

    if proxy_ok and direct_ok:
        print_ok("两种情况都成功 —— 代理不是问题")
        print_info("如果编辑器内仍报 404，请重新配置 base_url：")
        print_info("  工具 → AI 助手 → ⚙ 配置 AI")
        print_info("  Base URL 填: http://localhost:11434/v1")
        return 0

    if not proxy_ok and direct_ok:
        print_fail("走代理失败，禁用代理成功")
        print()
        print_info("★ 关键问题：代理环境变量干扰了 localhost 请求")
        print()
        print_info("修复方式：在项目中为 requests 请求禁用代理")
        print_info("需要修改 core/ai_client.py 的 _make_request 方法：")
        print()
        print("  # 修改前")
        print("  resp = requests.post(url, headers=headers, json=json_data,")
        print("                       timeout=timeout)")
        print()
        print("  # 修改后")
        print("  resp = requests.post(url, headers=headers, json=json_data,")
        print("                       timeout=timeout,")
        print("                       proxies={'http': None, 'https': None})")
        print()
        print_info("或清空环境变量后重启编辑器：")
        if has_proxy_env:
            print("    set HTTP_PROXY=")
            print("    set HTTPS_PROXY=")
            print("    set http_proxy=")
            print("    set https_proxy=")
        return 1

    if not socket_ok:
        print_fail("TCP 连接失败 —— Ollama 服务未运行")
        print_info("启动 Ollama：ollama serve")
        return 1

    print_fail("两种方式都失败")
    print_info("请检查 Ollama 日志：")
    print_info("  Windows: %LOCALAPPDATA%\\Ollama\\server.log")
    return 1


if __name__ == '__main__':
    sys.exit(main())