# -*- coding: utf-8 -*-
"""插件安全审计 CLI（P2 沙箱第一阶段）

用法：
    python -m tools.audit_plugins                     # 审计 plugins/ 全部
    python -m tools.audit_plugins path/to/plugin      # 审计指定目录
    python -m tools.audit_plugins --json              # 机器可读输出
    python -m tools.audit_plugins --strict            # 有 review/warn 也返回 1

退出码：0 = 无 reject；1 = 存在 reject（--strict 下含 review/warn）。
"""
import argparse
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from infrastructure.plugin_sandbox import audit_plugin, audit_plugins_root  # noqa: E402


_ICON = {"pass": "✅", "warn": "⚠️", "review": "🔍", "reject": "⛔"}


def main():
    ap = argparse.ArgumentParser(description="插件安全沙箱审计")
    ap.add_argument("paths", nargs="*", help="插件目录（默认 plugins/）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--strict", action="store_true",
                    help="warn 也视为失败")
    args = ap.parse_args()

    results = []
    paths = args.paths or [os.path.join(ROOT, "plugins")]
    for path in paths:
        path = os.path.abspath(path)
        if os.path.exists(os.path.join(path, "plugin.json")):
            results.append(audit_plugin(path))
        else:
            results.extend(audit_plugins_root(path))

    if args.json:
        print(json.dumps([r.to_dict() for r in results],
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            name = os.path.basename(r.plugin_dir.rstrip("\\/"))
            print("%s %-22s verdict=%-6s findings=%d missing=%s"
                  % (_ICON.get(r.verdict, "?"), name, r.verdict,
                     len(r.findings),
                     ",".join(r.missing_permissions) or "-"))
            for f in r.findings[:5]:
                print("    [%s] %s"% (f.severity, f.message))
        summary = {}
        for r in results:
            summary[r.verdict] = summary.get(r.verdict, 0) + 1
        print("\n汇总: " + ", ".join(
            "%s=%d" % (k, v) for k, v in sorted(summary.items())))

    bad = [r for r in results if r.verdict == "reject"]
    if args.strict:
        bad += [r for r in results if r.verdict in ("review", "warn")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
