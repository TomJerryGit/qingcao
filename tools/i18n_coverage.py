# -*- coding: utf-8 -*-
"""i18n 覆盖率报告（v2.19 P1-2 长尾）

统计：模板总条目、英文映射数；重点 UI 文件（偏好页/欢迎页/菜单/接线）的
中文串翻译覆盖率。输出 Markdown 报告。

用法:
    python tools/i18n_coverage.py --out docs/i18n_coverage_report.md
"""

import argparse
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "locale", "zh_CN", "strings.json")
EN = os.path.join(ROOT, "locale", "en_US", "strings.json")
TARGETS = (
    "ui/preferences_panel.py",
    "ui/welcome_widget.py",
    "ui/mixins/menu_builder_mixin.py",
    "ui/mixins/capability_wiring_mixin.py",
)


def _extract(path):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from extract_i18n_strings import extract_from_source

    src = io.open(path, encoding="utf-8", errors="replace").read()
    return set(extract_from_source(src))


def _tr_like(text, en):
    if text in en:
        return True
    for suffix in ("：", ":", "..."):
        if text.endswith(suffix) and text[: -len(suffix)].strip() in en:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "i18n_coverage_report.md"))
    args = ap.parse_args()
    template = json.load(io.open(TEMPLATE, encoding="utf-8"))
    en = json.load(io.open(EN, encoding="utf-8"))
    rows = []
    total = 0
    translated = 0
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        strings = _extract(path)
        hit = sum(1 for s in strings if _tr_like(s, en))
        total += len(strings)
        translated += hit
        ratio = (hit / len(strings) * 100) if strings else 0.0
        rows.append((rel, len(strings), hit, ratio))
    ui_ratio = (translated / total * 100) if total else 0.0
    tpl_ratio = (len(set(template) & set(en)) / len(template) * 100) if template else 0.0
    lines = [
        "# i18n 覆盖率报告（v2.19 P1-2）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        "| 模板条目（zh_CN） | %d |" % len(template),
        "| 英文映射条目（en_US） | %d |" % len(en),
        "| 模板覆盖率 | %.1f%% |" % tpl_ratio,
        "| 重点 UI 覆盖率 | %.1f%% |" % ui_ratio,
        "",
        "## 重点文件",
        "",
        "| 文件 | 中文串 | 已翻译 | 覆盖率 |",
        "|---|---|---|---|",
    ]
    for rel, n, hit, ratio in rows:
        lines.append("| `%s` | %d | %d | %.1f%% |" % (rel, n, hit, ratio))
    lines += [
        "",
        "## 说明",
        "",
        "- 模板来自 `tools/extract_i18n_strings.py`（全仓 5218 条）；",
        "- 首批优先覆盖：菜单、欢迎页、偏好页与常用动作；",
        "- 未翻译项安全回退中文；长尾继续分批补充。",
        "",
    ]
    io.open(args.out, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print(
        "[i18n] template=%d en=%d ui_ratio=%.1f%% -> %s"
        % (len(template), len(en), ui_ratio, args.out)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
