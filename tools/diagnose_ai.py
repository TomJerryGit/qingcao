#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 配置诊断
============================================================
功能：
  1. 读取编辑器 QSettings 中的 AI 配置
  2. 显示 base_url / model / provider
  3. 模拟编辑器的实际请求 URL
  4. 实际调用 Ollama /v1/chat/completions 验证

用法：
    python tools/diagnose_ai.py
============================================================
"""

import json
import os
import sys


# 添加项目根目录到 path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


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


def read_settings_directly():
    """直接从 QSettings 读（不依赖 PyQt5 app 实例）"""
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings("QingCao", "AI")
        return {
            'provider': settings.value("provider", "", type=str),
            'api_key': settings.value("api_key", "", type=str),
            'model': settings.value("model", "", type=str),
            'base_url': settings.value("base_url", "", type=str),
        }
    except Exception as e:
        print_fail(f"读取 QSettings 失败: {e}")
        return None


def test_request(base_url, model, api_key):
    """模拟编辑器的实际请求"""
    import urllib.error
    import urllib.request

    # 模拟 ai_client.py 的 URL 拼接
    # 见 core/ai_client.py:
    #   self.base_url = base_url.rstrip('/') if base_url else ""
    #   url = self.base_url + "/chat/completions"
    normalized_base = base_url.rstrip('/') if base_url else ""
    actual_url = normalized_base + "/chat/completions"

    print_info(f"模拟请求 URL: {actual_url}")

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = "Bearer " + api_key

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.3,
        "max_tokens": 16,
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            actual_url, data=data, headers=headers, method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8')
            print_ok(f"HTTP {resp.status}")
            try:
                parsed = json.loads(body)
                content = parsed.get('choices', [{}])[0].get(
                    'message', {}
                ).get('content', '')
                print_ok(f"响应内容: {content[:80]}")
                return True
            except Exception:
                print_ok(f"响应: {body[:200]}")
                return True
    except urllib.error.HTTPError as e:
        print_fail(f"HTTP {e.code}")
        try:
            body = e.read().decode('utf-8')
            print_fail(f"响应体: {body[:300]}")
        except Exception:
            pass
        return False
    except Exception as e:
        print_fail(f"请求失败: {e}")
        return False


def main():
    print_header("AI 配置诊断")

    # ---- 1. 读取配置 ----
    print_header("1. 当前配置（QSettings: QingCao/AI）")
    cfg = read_settings_directly()
    if not cfg:
        return 1

    for k, v in cfg.items():
        if k == 'api_key':
            display = ('*' * len(v)) if v else '(空)'
        else:
            display = v if v else '(空)'
        print(f"  {k:12s} = {display!r}")

    # ---- 2. 分析配置 ----
    print_header("2. 配置分析")

    provider = cfg.get('provider', '')
    base_url = cfg.get('base_url', '')
    model = cfg.get('model', '')
    api_key = cfg.get('api_key', '')

    if provider != 'ollama':
        print_warn(f"当前 provider 不是 ollama（是 {provider!r}）")
        print_info("如果只是想测 Ollama，可先跳过本节")

    # 检查 base_url
    if not base_url:
        print_warn("base_url 为空 —— 将使用默认值（应该是 http://localhost:11434/v1）")
        default_for_ollama = "http://localhost:11434/v1"
        base_url = default_for_ollama
        print_info(f"Ollama 默认 base_url: {default_for_ollama}")
    else:
        # 关键检查
        if not base_url.endswith('/v1'):
            if base_url.endswith('/v1/'):
                print_fail("base_url 以 /v1/ 结尾（尾部斜杠），"
                           "拼接后会变成 /v1//chat/completions")
            elif '/v1' not in base_url:
                print_fail(f"base_url 中缺少 /v1: {base_url!r}")
                print_info("应改为: http://localhost:11434/v1")
            else:
                print_warn(f"base_url 格式异常: {base_url!r}")
        else:
            print_ok(f"base_url 格式正确: {base_url!r}")

    if not model:
        print_fail("model 为空")
    else:
        print_ok(f"model: {model!r}")

    # ---- 3. 实际请求 ----
    print_header("3. 实际请求测试")

    if not base_url:
        print_fail("无 base_url，无法测试")
        return 1

    if not model:
        print_fail("无 model，无法测试")
        return 1

    success = test_request(base_url, model, api_key)

    # ---- 4. 结论 ----
    print_header("4. 结论")

    if success:
        print_ok("编辑器配置的 base_url 和 model 可以正常调用")
        print_info("如果编辑器内仍报 404，请检查：")
        print_info("  1. 配置保存后是否重启了编辑器")
        print_info("  2. 是否有旧的 keybindings.json 或缓存覆盖")
    else:
        print_fail("请求失败")
        print()
        print_info("建议：")
        print_info("  1. 打开编辑器：工具 → AI 助手 → ⚙ 配置 AI")
        print_info("  2. 提供商选 Ollama (本地)")
        print_info("  3. API Key 留空")
        print_info("  4. 模型填: llama3.2 或 llama3.2:latest")
        print_info("  5. Base URL 填: http://localhost:11434/v1")
        print_info("  6. 点 🔌 测试连接，看到 ✓ 后保存")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())