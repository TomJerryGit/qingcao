# -*- coding: utf-8 -*-
"""CI 队列/耗时统计（R3）：GitHub Actions job 级 P50/P95。

python tools/ci_queue_stats.py --days 14 --workflows Test,Release
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request


API = "https://api.github.com"


def _req(url, token=""):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "qc-ci-queue")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_ts(ts):
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def job_queue_seconds(job):
    """排队时间：job created_at → started_at（run 级 created=started，无意义）。"""
    try:
        return (parse_ts(job["started_at"]) - parse_ts(job["created_at"])).total_seconds()
    except Exception:
        return None


def job_duration_seconds(job):
    try:
        return (parse_ts(job["completed_at"]) - parse_ts(job["started_at"])).total_seconds()
    except Exception:
        return None


def percentile(values, pct):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return 0.0
    idx = min(len(vals) - 1, round(pct / 100.0 * (len(vals) - 1)))
    return vals[idx]


def summarize_jobs(jobs):
    by_wf = {}
    for j in jobs:
        name = j.get("workflow_name") or j.get("name") or "unknown"
        q = job_queue_seconds(j)
        d = job_duration_seconds(j)
        rec = by_wf.setdefault(name, {"queue": [], "duration": []})
        if q is not None:
            rec["queue"].append(q)
        if d is not None:
            rec["duration"].append(d)
    rows = []
    for name, rec in by_wf.items():
        rows.append(
            {
                "workflow": name,
                "jobs": len(rec["duration"]),
                "queue_p50": round(percentile(rec["queue"], 50), 1),
                "queue_p95": round(percentile(rec["queue"], 95), 1),
                "duration_p50": round(percentile(rec["duration"], 50), 1),
                "duration_p95": round(percentile(rec["duration"], 95), 1),
            }
        )
    return sorted(rows, key=lambda x: -x["jobs"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "TomJerryGit/qingcao"))
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--workflows", default="Test,Release")
    ap.add_argument("--report", default=os.path.join("docs", "ci_queue_report.md"))
    ap.add_argument("--json", default=os.path.join("data", "ci_queue_stats.json"))
    args = ap.parse_args(argv)
    wanted = {w.strip() for w in args.workflows.split(",") if w.strip()}
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=args.days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    list_url = "%s/repos/%s/actions/runs?per_page=100&created=>=%s" % (API, args.repo, since)
    runs = _req(list_url, args.token).get("workflow_runs", []) or []
    jobs = []
    used = 0
    for run in runs:
        if wanted and (run.get("name") not in wanted):
            continue
        if used >= args.limit:
            break
        used += 1
        try:
            data = _req(
                "%s/repos/%s/actions/runs/%s/jobs?per_page=100" % (API, args.repo, run["id"]),
                args.token,
            )
        except Exception:
            continue
        for job in data.get("jobs", []) or []:
            job["workflow_name"] = run.get("name")
            jobs.append(job)
    rows = summarize_jobs(jobs)
    result = {"days": args.days, "runs": used, "jobs": len(jobs), "rows": rows}
    os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
    with open(args.json, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    lines = [
        "# CI 队列 / 耗时统计（job 级，最近 %d 天）" % args.days,
        "",
        "- 运行样本：%d · job 样本：%d" % (used, len(jobs)),
        "",
        "| 工作流 | job 数 | 队列 P50 | 队列 P95 | 耗时 P50 | 耗时 P95 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| %s | %d | %.1fs | %.1fs | %.1fs | %.1fs |"
            % (
                r["workflow"],
                r["jobs"],
                r["queue_p50"],
                r["queue_p95"],
                r["duration_p50"],
                r["duration_p95"],
            )
        )
    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
    with open(args.report, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("[ci-queue] runs=%d jobs=%d -> %s" % (used, len(jobs), args.report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
