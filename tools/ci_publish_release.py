# -*- coding: utf-8 -*-
"""CI 发布工具（Python 版，替代 curl/PowerShell）

在自托管 Runner 上创建/更新 GitHub Release 并上传资产：
* 幂等：GET 404 → 创建；已存在 → 更新；已存在同名资产且 size>0 → 跳过
* 重试：网络错误/5xx/429 指数退避
* 校验：结束前回查资产，缺任一文件即失败
* 只依赖标准库（urllib），不受 PowerShell 5.1 编码问题影响

用法：
    GH_TOKEN=... GITHUB_REPOSITORY=owner/repo python tools/ci_publish_release.py
    python tools/ci_publish_release.py --dry-run --tag v2.6.1
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


def get_version() -> str:
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def notes_path(tag: str) -> str:
    p = os.path.join(ROOT, "docs", "release_notes_%s.md" % tag)
    return p if os.path.exists(p) else os.path.join(ROOT, "CHANGELOG.md")


def asset_paths(version: str):
    zip_path = os.path.join(ROOT, "dist",
                            "QingCaoEditor-v%s-windows.zip" % version)
    return zip_path, zip_path + ".sha256.txt"


def build_payload(tag: str, body: str) -> dict:
    return {
        "tag_name": tag,
        "name": "QingCaoEditor %s" % tag,
        "body": body,
        "draft": False,
        "prerelease": False,
    }


def extract_changelog_summary(version: str, limit: int = 6) -> str:
    """从 CHANGELOG.md 提取当前版本条目作为 Release 变更摘要"""
    path = os.path.join(ROOT, "CHANGELOG.md")
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return ""
    header = "## [%s]" % version
    collecting = False
    items = []
    for line in lines:
        if line.startswith("## ["):
            if collecting:
                break
            collecting = line.startswith(header)
            continue
        if collecting and line.startswith("- "):
            items.append(line.strip())
            if len(items) >= limit:
                break
    return "\n".join(items)


def compose_body(body: str, zip_path: str, sha_path: str,
                 prev_size: float = None) -> str:
    """在发布说明后自动附加包体积/哈希报告（P3）

    prev_size: 上一版本 ZIP 大小（字节）；提供时附体积变化。
    """
    import hashlib
    import os
    lines = ["", "---", "", "## 包信息（自动生成）", "",
             "| 文件 | 大小 |", "|---|---|"]
    for path in (zip_path, sha_path):
        try:
            size = os.path.getsize(path) / 1048576.0
            lines.append("| `%s` | %.2f MB |"
                         % (os.path.basename(path), size))
        except OSError:
            continue
    try:
        size = os.path.getsize(zip_path)
        if prev_size and prev_size > 0:
            delta = size - prev_size
            pct = delta / prev_size * 100.0
            lines += ["", "| 对比 | 变化 |", "|---|---|",
                      "| 较上一版 | %+.2f MB (%+.1f%%) |"
                      % (delta / 1048576.0, pct)]
        else:
            lines += ["", "| 对比 | 变化 |", "|---|---|",
                      "| 较上一版 | 首次发布/未知 |"]
    except OSError:
        pass
    try:
        h = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        lines += ["", "```", "SHA256: %s" % h.hexdigest().upper(), "```"]
    except OSError:
        pass
    return body.rstrip() + "\n" + "\n".join(lines) + "\n"


def needed_asset_names(version: str):
    return ["QingCaoEditor-v%s-windows.zip" % version,
            "QingCaoEditor-v%s-windows.zip.sha256.txt" % version]


def api_request(method, url, token, data=None,
                content_type="application/json", retries=5, timeout=120):
    headers = {
        "Authorization": "Bearer %s" % token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "qingcao-ci-release",
    }
    if data is not None:
        headers["Content-Type"] = content_type
    last_error = ""
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw.decode("utf-8"))
                                     if raw else {})
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 404 and method == "GET":
                return 404, {"error": body}
            last_error = "HTTP %d %s" % (e.code, body[:400])
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise SystemExit("[release] %s %s 失败: %s"
                             % (method, url, last_error))
        except Exception as e:
            last_error = str(e)
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise SystemExit("[release] %s %s 失败: %s"
                             % (method, url, last_error))
    raise SystemExit("[release] 重试耗尽: %s" % last_error)


def upload_asset(token, repo, release_id, path):
    name = os.path.basename(path)
    with open(path, "rb") as f:
        data = f.read()
    url = "%s/repos/%s/releases/%d/assets?name=%s" % (
        UPLOADS, repo, release_id, urllib.parse.quote(name))
    status, resp = api_request(token=token, method="POST", url=url,
                               data=data,
                               content_type="application/octet-stream")
    if not isinstance(resp, dict) or not resp.get("name") \
            or int(resp.get("size") or 0) <= 0:
        raise SystemExit("[release] 上传校验失败: %r" % (resp,))
    print("[release] 已上传: %s (%.1f MB)"
          % (resp["name"], resp["size"] / 1048576))
    return resp


def previous_release_size(base: str, token: str, tag: str):
    """查询最近一个非当前 tag 的 Release 的 windows.zip 大小（字节）"""
    try:
        status, rels = api_request(
            "GET", "%s/releases?per_page=30" % base, token)
        if not isinstance(rels, list):
            return None
        for rel in rels:
            if not isinstance(rel, dict) or rel.get("tag_name") == tag:
                continue
            for asset in rel.get("assets") or []:
                name = str(asset.get("name") or "")
                if (name.startswith("QingCaoEditor-v")
                        and name.endswith("-windows.zip")):
                    size = int(asset.get("size") or 0)
                    return size if size > 0 else None
        return None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="CI Release 发布")
    ap.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    version = get_version()
    tag = args.tag or ("v" + version)
    notes = notes_path(tag)
    zip_path, sha_path = asset_paths(version)
    print("[release] version=%s tag=%s" % (version, tag))
    print("[release] notes=%s" % os.path.relpath(notes, ROOT))
    for p in (zip_path, sha_path):
        print("[release] asset %s 存在=%s"
              % (os.path.basename(p), os.path.exists(p)))
    if args.dry_run:
        print("[release] dry-run 结束")
        return 0
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        raise SystemExit("[release] 缺少 GH_TOKEN / GITHUB_REPOSITORY")
    for p in (zip_path, sha_path):
        if not os.path.exists(p):
            raise SystemExit("[release] 缺少资产: %s" % p)
    with open(notes, encoding="utf-8") as f:
        body = f.read()
    try:
        prev_size = previous_release_size(
            "%s/repos/%s" % (API, repo), token, tag)
    except Exception:
        prev_size = None
    if prev_size:
        print("[release] 上一版体积: %.2f MB" % (prev_size / 1048576.0))
    body = compose_body(body, zip_path, sha_path, prev_size)
    try:
        summary = extract_changelog_summary(version)
    except Exception:
        summary = ""
    if summary:
        body += "\n\n## 变更摘要（自动生成）\n\n" + summary + "\n"
    payload = json.dumps(build_payload(tag, body),
                         ensure_ascii=False).encode("utf-8")
    base = "%s/repos/%s" % (API, repo)
    status, rel = api_request("GET", "%s/releases/tags/%s" % (base, tag),
                              token)
    if status == 404:
        status, rel = api_request("POST", "%s/releases" % base, token,
                                  data=payload)
        print("[release] 已创建 Release")
    else:
        status, rel = api_request(
            "PATCH", "%s/releases/%s" % (base, rel["id"]), token,
            data=payload)
        print("[release] 已更新 Release")
    rel_id = rel.get("id")
    if not rel_id:
        raise SystemExit("[release] Release id 缺失: %r" % (rel,))
    existing = {a.get("name") for a in (rel.get("assets") or [])
                if int(a.get("size") or 0) > 0}
    needed = needed_asset_names(version)
    for p in (zip_path, sha_path):
        name = os.path.basename(p)
        if name in existing:
            print("[release] 资产已存在，跳过: %s" % name)
            continue
        upload_asset(token, repo, rel_id, p)
    status, rel2 = api_request("GET", "%s/releases/tags/%s" % (base, tag),
                               token)
    names = {a.get("name") for a in (rel2.get("assets") or [])}
    missing = [n for n in needed if n not in names]
    if missing:
        raise SystemExit("[release] Release 缺少资产: %s" % missing)
    print("[release] RELEASE_OK %s assets=%s" % (tag, ",".join(sorted(names))))
    return 0


if __name__ == "__main__":
    sys.exit(main())