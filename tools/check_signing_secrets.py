# -*- coding: utf-8 -*-
"""检查 Authenticode 相关 GitHub Secrets 是否已配置（只读 names，不读取值）。

python tools/check_signing_secrets.py --repo TomJerryGit/qingcao
环境变量：GITHUB_TOKEN（需 repo admin 才能列 secrets）。
"""

import argparse
import json
import os
import sys
import urllib.request


API = "https://api.github.com"
REQUIRED = ("WINDOWS_SIGN_CERT_BASE64", "WINDOWS_SIGN_CERT_PASSWORD")


def _req(url, token):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "qc-sign-check")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def missing(names):
    return [n for n in REQUIRED if n not in names]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "TomJerryGit/qingcao"))
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = ap.parse_args(argv)
    if not args.token:
        print("[sign-check] SKIP：未设置 GITHUB_TOKEN（需 repo admin 才能列出 secrets）")
        return 0
    try:
        data = _req("%s/repos/%s/actions/secrets" % (API, args.repo), args.token)
    except Exception as e:
        print("[sign-check] 无法读取 secrets（权限不足/网络）：%s" % e)
        return 1
    names = {s.get("name") for s in data.get("secrets", [])}
    for n in REQUIRED:
        print("[sign-check] %-32s %s" % (n, "configured" if n in names else "MISSING"))
    miss = missing(names)
    if miss:
        print("[sign-check] 待配置：%s（见 docs/authenticode_setup_steps.md）" % ", ".join(miss))
        return 1
    print("[sign-check] OK：下次发布将自动 Authenticode 签名")
    return 0


if __name__ == "__main__":
    sys.exit(main())
