# -*- coding: utf-8 -*-
"""Sprint 2：剩余插件用户文案白名单（≤5）"""

import glob
import io


ROOT = "."


def test_remaining_plugin_i18n_within_whitelist():
    hits = []
    for path in glob.glob("plugins/**/*.py", recursive=True):
        if "__pycache__" in path:
            continue
        for no, line in enumerate(io.open(path, encoding="utf-8", errors="ignore"), 1):
            if 'show_status("' in line or 'show_message("' in line:
                if "tr(" in line or not any("\u4e00" <= c <= "\u9fff" for c in line):
                    continue
                hits.append("%s:%d" % (path, no))
    assert len(hits) <= 5, hits
