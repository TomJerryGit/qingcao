# -*- coding: utf-8 -*-
"""GitHub Releases 静态注册表发布（v2.21 P1-3）

零域名：registry.json + 插件 zip 作为 GitHub Release 资产。
    python tools/publish_registry_release.py --dry-run
    python tools/publish_registry_release.py --token <github_token>
"""

import argparse
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

REPO = "TomJerryGit/qingcao"
TAG = "plugin-registry"
API = "https://api.github.com"
DEFAULT_OUT = os.path.join(ROOT, "data", "registry_github")


def release_base_url(repo=REPO, tag=TAG):
    return "https://github.com/%s/releases/download/%s" % (repo, tag)


def registry_url(repo=REPO, tag=TAG):
    return release_base_url(repo, tag) + "/registry.json"


def asset_download_url(repo, tag, name):
    return release_base_url(repo, tag) + "/" + name


def build_assets(out_dir, repo=REPO, tag=TAG, only=None, key_hex="", app_version=""):
    from build_plugin_registry import build

    registry, out_json = build(
        "plugins",
        out_dir,
        release_base_url(repo, tag),
        only=only or None,
        key_hex=key_hex,
        app_version=app_version,
    )
    return registry, out_json


def build_ratings(out_dir, src=None):
    """聚合本地评分并写入 ratings.json（静态、零服务端）。"""
    from build_ratings_aggregate import aggregate

    data = aggregate(src) if src else aggregate()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "ratings.json")
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    return path, data


def _request(method, url, token, data=None, headers=None):
    import urllib.request

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github+json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def ensure_release(token, repo=REPO, tag=TAG):
    import urllib.error

    try:
        return _request("GET", "%s/repos/%s/releases/tags/%s" % (API, repo, tag), token)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    payload = json.dumps(
        {
            "tag_name": tag,
            "name": "Plugin Registry Assets",
            "body": "Static registry for the in-app Plugin Market.",
        }
    ).encode("utf-8")
    return _request(
        "POST",
        "%s/repos/%s/releases" % (API, repo),
        token,
        data=payload,
        headers={"Content-Type": "application/json"},
    )


def upload_asset(token, repo, release, path, name=None):
    name = name or os.path.basename(path)
    for asset in release.get("assets", []):
        if asset.get("name") == name:
            try:
                _request(
                    "DELETE", "%s/repos/%s/releases/assets/%d" % (API, repo, asset["id"]), token
                )
            except Exception:
                pass
    upload_url = release["upload_url"].split("{")[0] + "?name=" + name
    import urllib.request

    with io.open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(upload_url, data=data, method="POST")
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--tag", default=TAG)
    ap.add_argument("--only", default="")
    ap.add_argument("--key-hex", default=os.environ.get("QINGCAO_PLUGIN_SIGN_KEY", ""))
    ap.add_argument("--app-version", default="")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    registry, out_json = build_assets(
        args.out, args.repo, args.tag, only=only, key_hex=args.key_hex, app_version=args.app_version
    )
    ratings_path, ratings = build_ratings(args.out)
    print("[registry-release] 构建 %d 个插件 -> %s" % (len(registry["plugins"]), out_json))
    print(
        "[registry-release] ratings.json 插件 %d 条 -> %s"
        % (len(ratings.get("plugins", {})), ratings_path)
    )
    print("[registry-release] REGISTRY_URL=%s" % registry_url(args.repo, args.tag))
    if args.dry_run or not args.token:
        if not args.dry_run:
            print("[registry-release] 未提供 GITHUB_TOKEN，已跳过上传（dry-run）")
        return 0
    release = ensure_release(args.token, args.repo, args.tag)
    paths = [out_json, ratings_path] + [
        os.path.join(args.out, "plugins", n)
        for n in sorted(os.listdir(os.path.join(args.out, "plugins")))
        if n.endswith(".zip")
    ]
    for path in paths:
        print(
            "[registry-release] 已上传:",
            upload_asset(args.token, args.repo, release, path).get("browser_download_url"),
        )
    print("[registry-release] OK: %s" % registry_url(args.repo, args.tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
