# -*- coding: utf-8 -*-
"""文档与版本一致性巡检（Sprint 4）。"""

import glob
import io
import os
import re
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def version():
    try:
        return io.open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except OSError:
        return ""


def check_version():
    r = subprocess.run(
        [sys.executable, "-m", "tools.check_version"], cwd=ROOT, capture_output=True, text=True
    )
    return (r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip())


def check_notes(ver):
    path = os.path.join(ROOT, "docs", "release_notes_v%s.md" % ver)
    return os.path.isfile(path)


def check_links(root=None):
    root = root or ROOT
    missing = []
    for path in glob.glob(os.path.join(root, "docs", "**", "*.md"), recursive=True):
        try:
            text = io.open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#")[0]
            base = os.path.dirname(path)
            candidates = [os.path.join(base, target), os.path.join(root, target)]
            if not any(os.path.exists(c) for c in candidates):
                missing.append("%s -> %s" % (os.path.relpath(path, root), target))
    return missing


def main(argv=None):
    ver = version()
    ok, out = check_version()
    notes = check_notes(ver)
    links = check_links()
    lines = [
        "# 文档与版本一致性巡检",
        "",
        "- 版本：%s" % ver,
        "- check_version：%s" % ("PASS" if ok else "FAIL"),
        "- Release notes：%s" % ("存在" if notes else "缺失"),
        "- 失效本地链接：%d" % len(links),
        "",
    ]
    if out:
        lines += ["## check_version 输出", "", "```", out, "```", ""]
    if links:
        lines += ["## 失效链接", ""] + ["- " + x for x in links] + [""]
    text = "\n".join(lines)
    out_path = os.path.join(ROOT, "docs", "docs_audit_report.md")
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(text + "\n")
    print(text)
    return 0 if (ok and notes) else 1


if __name__ == "__main__":
    sys.exit(main())
