# -*- coding: utf-8 -*-
"""检查插件设置 schema 覆盖率（P2 体验）。"""

import glob
import io
import os
import sys


def scan(root="plugins"):
    rows = []
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        if not os.path.isdir(d):
            continue
        name = os.path.basename(d)
        src = ""
        for f in glob.glob(os.path.join(d, "*.py")):
            src += io.open(f, encoding="utf-8", errors="ignore").read()
        rows.append(
            {
                "name": name,
                "has_schema": ("register_settings_schema" in src or "def config_schema" in src),
            }
        )
    return rows


def main(argv=None):
    rows = scan(argv[1] if argv and len(argv) > 1 else "plugins")
    missing = [r["name"] for r in rows if not r["has_schema"]]
    print("[settings] plugins=%d missing=%s" % (len(rows), ",".join(missing) or "0"))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
