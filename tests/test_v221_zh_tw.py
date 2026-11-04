# -*- coding: utf-8 -*-
"""v2.21 P1-2：繁体中文语言包"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_available_and_tr(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "zh_TW")
    from core.i18n_json import AVAILABLE, clear_cache, tr, tr_menu

    clear_cache()
    assert AVAILABLE.get("zh_TW") == "繁體中文"
    assert tr("保存") == "儲存"
    assert tr("文件") == "檔案"
    assert tr_menu("文件(&F)") == "檔案(&F)"
    assert tr("不存在的原文") == "不存在的原文"


def test_pack_complete():
    zh = json.load(open(os.path.join(ROOT, "locale", "zh_CN", "strings.json"), encoding="utf-8"))
    tw = json.load(open(os.path.join(ROOT, "locale", "zh_TW", "strings.json"), encoding="utf-8"))
    assert len(tw) >= len(zh) >= 5218
    assert tw["首选项"] == "偏好設定"
    assert tw["插件市场"] == "外掛市場"


def test_coverage_check_zh_tw(monkeypatch):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "qc_cov_tw", os.path.join(ROOT, "tools", "i18n_coverage.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("QINGCAO_LANG", "zh_CN")
    old = sys.argv
    sys.argv = [
        "i18n_coverage.py",
        "--check",
        "--min-corpus",
        "100",
        "--lang",
        "zh_TW",
        "--out",
        os.path.join(ROOT, "docs", "i18n_coverage_report.md"),
    ]
    try:
        assert mod.main() == 0
    finally:
        sys.argv = old
