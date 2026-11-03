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


def has_cjk(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _tr_like(text, en):
    if text in en:
        return True
    for suffix in ("：", ":", "..."):
        if text.endswith(suffix) and text[: -len(suffix)].strip() in en:
            return True
    return False


def _has_cjk(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _menu_base(text):
    import re

    m = re.match(r"^([^0-9A-Za-z\u4e00-\u9fff]{1,6}\s+)(.+)$", text)
    return m.group(2) if m else text


def menu_runtime_coverage():
    """运行时菜单动作覆盖率（中文 base 文本 → en 词典命中率）"""
    import os as _os
    import sys as _sys

    old_lang = _os.environ.get("QINGCAO_LANG")
    old_plat = _os.environ.get("QT_QPA_PLATFORM")
    _os.environ["QINGCAO_LANG"] = "zh_CN"
    _os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        _sys.path.insert(0, ROOT)
        from PyQt5.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
        QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
        from ui.main_window import MainWindow

        win = MainWindow()
        texts = set()

        def walk(menu):
            for act in menu.actions():
                if act.isSeparator():
                    continue
                label = act.text().replace("&", "")
                if label:
                    texts.add(label)
                if act.menu() is not None:
                    walk(act.menu())

        walk(win.menuBar())
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()

        en = json.load(io.open(EN, encoding="utf-8"))
        bases = {_menu_base(t) for t in texts if _has_cjk(t)}
        hit = len({b for b in bases if b in en or b.rstrip(".:：") in en})
        ratio = (hit / len(bases) * 100) if bases else 0.0
        return (len(bases), hit, ratio)
    except Exception:
        return None
    finally:
        if old_lang is None:
            _os.environ.pop("QINGCAO_LANG", None)
        else:
            _os.environ["QINGCAO_LANG"] = old_lang
        if old_plat is None:
            _os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            _os.environ["QT_QPA_PLATFORM"] = old_plat
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "i18n_coverage_report.md"))
    args = ap.parse_args()
    template = json.load(io.open(TEMPLATE, encoding="utf-8"))
    en = json.load(io.open(EN, encoding="utf-8"))
    menu_cov = menu_runtime_coverage()
    rows = []
    total = 0
    translated = 0
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        strings = {s for s in _extract(path) if has_cjk(s)}
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
        ("| 菜单动作覆盖率（运行时） | %d/%d（%.1f%%） |" % (menu_cov[1], menu_cov[0], menu_cov[2]))
        if menu_cov
        else "| 菜单动作覆盖率（运行时） | n/a |",
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
