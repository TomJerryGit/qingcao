# -*- coding: utf-8 -*-
"""Sprint 2：i18n 快照测试（zh/en/ja/ko）"""

import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SNAPSHOT = os.path.join(ROOT, "tests", "fixtures_i18n_snapshot.json")


def _snapshot():
    return json.load(io.open(SNAPSHOT, encoding="utf-8-sig"))


def test_snapshot_matches_all_locales():
    from core import plugin_i18n as i18n

    for locale in ("zh_CN", "en_US", "ja_JP", "ko_KR"):
        i18n.set_locale(locale)
        for key, values in _snapshot().items():
            assert i18n.tr(key) == values[locale], (locale, key)


def test_missing_key_detected():
    from core import plugin_i18n as i18n

    i18n.set_locale("en_US")
    assert i18n.tr("not.exist.key") == "not.exist.key"


def test_placeholders_preserved():
    from core import plugin_i18n as i18n

    i18n.set_locale("en_US")
    assert "{n}" in i18n.tr("wordcount.words")
