# -*- coding: utf-8 -*-
"""发布后自动核验：资产齐全、安装器版本、SHA256 一致。"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request


API = "https://api.github.com"


def expected(version):
    return {
        "zip": "QingCaoEditor-v%s-windows.zip" % version,
        "sha": "QingCaoEditor-v%s-windows.zip.sha256.txt" % version,
        "sig": "QingCaoEditor-v%s-windows.zip.sig" % version,
        "installer": "QingCaoEditor_Setup_v%s.exe" % version,
    }


def evaluate(names, version):
    need = expected(version)
    missing = [v for v in need.values() if v not in names]
    return missing


def _get(url, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": accept,
            "User-Agent": "qc-release-verify",
        },
    )
    return urllib.request.urlopen(req, timeout=120)


def verify_remote(tag, token, repo, download_sha=False):
    version = tag.lstrip("v")
    url = "%s/repos/%s/releases/tags/%s" % (API, repo, tag)
    with _get(url, token) as resp:
        rel = json.loads(resp.read().decode())
    assets = {a["name"]: a for a in rel.get("assets") or []}
    missing = evaluate(set(assets), version)
    if missing:
        return (False, "缺少资产: %s" % missing)
    if download_sha:
        need = expected(version)
        zip_a, sha_a = assets[need["zip"]], assets[need["sha"]]
        with tempfile.TemporaryDirectory() as td:
            zp = os.path.join(td, need["zip"])
            with _get(zip_a["url"], token, accept="application/octet-stream") as r, open(
                zp, "wb"
            ) as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            with _get(sha_a["url"], token, accept="application/octet-stream") as r:
                expected_hash = r.read().decode("ascii").split()[0].lower()
            h = hashlib.sha256()
            with open(zp, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            if h.hexdigest().lower() != expected_hash:
                return (False, "SHA256 不一致")
    return (True, "OK assets=%d" % len(assets))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--download-sha", action="store_true")
    args = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("[release-verify] 缺少 GH_TOKEN / GITHUB_REPOSITORY")
        return 2
    ok, msg = verify_remote(args.tag, token, repo, args.download_sha)
    print("[release-verify] %s %s" % ("PASS" if ok else "FAIL", msg))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
