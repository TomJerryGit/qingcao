# -*- coding: utf-8 -*-
"""评分运营自动收集：GitHub Issue（plugin-rating）→ community_ratings.json。

python tools/collect_issue_ratings.py --dry-run
python tools/collect_issue_ratings.py --apply
环境变量：GITHUB_REPOSITORY、GITHUB_TOKEN（issues: read）。
幂等：已处理的 issue 编号记录在 data/ratings_ingested.json。
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.github.com"
COMMUNITY = os.path.join(ROOT, "community_ratings.json")
INGESTED = os.path.join(ROOT, "data", "ratings_ingested.json")
LABEL = "plugin-rating"

_RE_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def _req(url, token=""):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "qc-ratings-ingest")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_issues(repo, token="", label=LABEL):
    url = "%s/repos/%s/issues?state=all&labels=%s&per_page=100" % (API, repo, label)
    return _req(url, token)


def parse_issue_body(body):
    """从 Issue 表单正文中提取评分 JSON（优先 ```json 代码块）。"""
    if not body:
        return None
    m = _RE_JSON_BLOCK.search(body)
    candidates = [m.group(1)] if m else []
    candidates.append(body[body.find("{") : body.rfind("}") + 1] if "{" in body else "")
    for raw in candidates:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("plugins"), dict):
            return data
    return None


def merge_submission(community, submission, issue_no):
    """把一份用户评分按“1 用户 1 票”并入聚合。"""
    plugins = submission.get("plugins") if isinstance(submission, dict) else None
    if not isinstance(plugins, dict):
        return community
    out = json.loads(json.dumps(community or {}))
    out.setdefault("version", 1)
    out.setdefault("plugins", {})
    src = "issue:%s" % issue_no
    for name, rec in plugins.items():
        try:
            if "average" in rec:
                avg = float(rec["average"])
                cnt = max(1, int(rec.get("count", 1)))
            else:
                avg = float(rec.get("stars", 0))
                cnt = 1
        except Exception:
            continue
        if avg <= 0:
            continue
        cur = out["plugins"].get(name)
        if cur:
            total = cur.get("count", 1) + cnt
            cur["average"] = round(
                (cur.get("average", 0) * cur.get("count", 1) + avg * cnt) / total, 2
            )
            cur["count"] = total
            srcs = set(cur.get("sources") or [])
            srcs.add(src)
            cur["sources"] = sorted(srcs)
        else:
            out["plugins"][name] = {"average": round(avg, 2), "count": cnt, "sources": [src]}
    out["source"] = "issues+manual"
    return out


def load_json(path, default):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return default


def run(repo, token, dry_run=False):
    community = load_json(COMMUNITY, {"version": 1, "plugins": {}})
    ingested = load_json(INGESTED, {"issues": []})
    done = set(int(x) for x in ingested.get("issues", []))
    issues = fetch_issues(repo, token)
    added = 0
    for issue in issues:
        if "pull_request" in issue:
            continue
        num = int(issue.get("number", 0))
        if not num or num in done:
            continue
        parsed = parse_issue_body(issue.get("body") or "")
        if parsed is None:
            print("[ingest] 跳过 #%s（未找到有效评分 JSON）" % num)
            continue
        community = merge_submission(community, parsed, num)
        done.add(num)
        added += 1
    result = {"community": community, "issues": sorted(done), "added": added}
    if not dry_run and added:
        io.open(COMMUNITY, "w", encoding="utf-8", newline="\n").write(
            json.dumps(community, ensure_ascii=False, indent=2, sort_keys=True)
        )
        os.makedirs(os.path.dirname(INGESTED), exist_ok=True)
        io.open(INGESTED, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"issues": sorted(done)}, ensure_ascii=False, indent=2)
        )
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if not args.repo:
        print("[ingest] 缺少 --repo / GITHUB_REPOSITORY")
        return 1
    result = run(args.repo, args.token, dry_run=not args.apply)
    print(
        "[ingest] 新增 %d 条 issue 评分；community 插件数 %d（dry_run=%s）"
        % (result["added"], len(result["community"].get("plugins") or {}), not args.apply)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
