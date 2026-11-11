# -*- coding: utf-8 -*-
"""CI 看守：检测并可选取消超时的 GitHub Actions 运行。

python tools/ci_watchdog.py --max-age-min 120
python tools/ci_watchdog.py --max-age-min 120 --cancel   # 需要 GITHUB_TOKEN(actions: write)

退出码：发现超时运行且未取消 -> 1；否则 0。
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone


API = "https://api.github.com"
DEFAULT_REPO = os.environ.get("GITHUB_REPOSITORY", "TomJerryGit/qingcao")


def _req(url, method="GET", token=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "qc-ci-watchdog")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}


def list_runs(repo, status="in_progress"):
    data = _req("%s/repos/%s/actions/runs?status=%s&per_page=100" % (API, repo, status))
    return data.get("workflow_runs") or []


def parse_time(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def stale_runs(runs, max_age_min, now=None):
    """返回创建时间超过 max_age_min 的运行列表。"""
    now = now or datetime.now(timezone.utc)
    limit = max_age_min * 60
    out = []
    for run in runs or []:
        try:
            age = (now - parse_time(run.get("created_at", ""))).total_seconds()
        except Exception:
            continue
        if age > limit:
            out.append(run)
    return out


def cancel_run(repo, run_id, token):
    return _req(
        "%s/repos/%s/actions/runs/%s/cancel" % (API, repo, run_id),
        method="POST",
        token=token,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="CI watchdog")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--max-age-min", type=int, default=120)
    ap.add_argument("--cancel", action="store_true")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    args = ap.parse_args(argv)

    runs = list_runs(args.repo) + list_runs(args.repo, "queued")
    stale = stale_runs(runs, args.max_age_min)
    for run in stale:
        print(
            "[watchdog] STALE %s id=%s branch=%s status=%s created=%s"
            % (
                run.get("name"),
                run.get("id"),
                run.get("head_branch"),
                run.get("status"),
                run.get("created_at"),
            )
        )
    if not stale:
        print("[watchdog] OK 无超时运行（阈值 %d 分钟）" % args.max_age_min)
        return 0
    if not args.cancel:
        return 1
    if not args.token:
        print("[watchdog] 未提供 GITHUB_TOKEN，无法取消")
        return 1
    for run in stale:
        try:
            cancel_run(args.repo, run.get("id"), args.token)
            print("[watchdog] CANCELLED id=%s" % run.get("id"))
        except Exception as e:
            print("[watchdog] 取消失败 id=%s: %s" % (run.get("id"), e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
