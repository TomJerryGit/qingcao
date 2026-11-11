# -*- coding: utf-8 -*-
"""发布前置门禁：等待指定 SHA 的 Test / Security / Lint 工作流成功。

python tools/ci_release_gate.py --sha <sha> --wait-min 30
环境变量：GITHUB_REPOSITORY、GITHUB_TOKEN（actions: read）。

退出码：0 全部成功；1 失败/超时/无运行。
"""

import argparse
import json
import os
import sys
import time
import urllib.request


API = "https://api.github.com"
WORKFLOWS = ("test.yml", "security.yml", "lint.yml")


def _req(url, token=None):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "qc-release-gate")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def workflow_latest(repo, workflow, sha, token=None):
    url = "%s/repos/%s/actions/workflows/%s/runs?head_sha=%s&per_page=5" % (
        API,
        repo,
        workflow,
        sha,
    )
    data = _req(url, token)
    runs = data.get("workflow_runs") or []
    return runs[0] if runs else None


def evaluate(run):
    """返回 (ok, state, message)。ok=True 仅当 success。"""
    if not run:
        return (None, "missing", "无该 SHA 的运行")
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status != "completed":
        return (None, "pending", "status=%s" % status)
    if conclusion == "success":
        return (True, "success", "run %s" % run.get("id"))
    return (False, str(conclusion), "run %s %s" % (run.get("id"), conclusion))


def wait_all(repo, sha, token, wait_min, interval, workflows=WORKFLOWS):
    deadline = time.time() + wait_min * 60
    pending = set(workflows)
    results = {}
    while pending and time.time() < deadline:
        for wf in list(pending):
            run = workflow_latest(repo, wf, sha, token)
            ok, state, msg = evaluate(run)
            results[wf] = (ok, state, msg)
            print("[gate] %-14s %-9s %s" % (wf, state, msg))
            if ok is not None:
                pending.discard(wf)
        if pending:
            time.sleep(interval)
    for wf in pending:
        results[wf] = (False, "timeout", "等待超时")
        print("[gate] %-14s timeout" % wf)
    return all(results.get(wf, (False,))[0] is True for wf in workflows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--wait-min", type=int, default=30)
    ap.add_argument("--interval", type=int, default=20)
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    ap.add_argument("--workflows", default=",".join(WORKFLOWS))
    args = ap.parse_args(argv)
    if not args.sha or not args.repo:
        print("[gate] 缺少 --sha / --repo")
        return 1
    wfs = tuple(x.strip() for x in args.workflows.split(",") if x.strip())
    ok = wait_all(args.repo, args.sha, args.token, args.wait_min, args.interval, wfs)
    print("[gate] RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
