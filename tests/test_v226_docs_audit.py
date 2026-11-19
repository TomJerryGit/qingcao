# -*- coding: utf-8 -*-
"""Sprint 4：文档链接巡检"""

import io
import os


def test_missing_and_existing_links(tmp_path):
    from tools.docs_audit import check_links

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ok.md").write_text("[a](ok.md)\n[b](https://x)\n", encoding="utf-8")
    (docs / "bad.md").write_text("[c](missing.md)\n", encoding="utf-8")
    missing = check_links(str(tmp_path))
    assert any("missing.md" in x for x in missing)
