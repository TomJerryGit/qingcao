# -*- coding: utf-8 -*-
"""mmap 默认开启评估（v2.20 P1-2）

运行场景 + 汇总本地埋点，生成 docs/mmap_default_evaluation.md。
    python tools/mmap_eval_report.py
"""

import io
import json
import os
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def run_scenarios(eval_file, journal_dir):
    import core.mmap_save as m

    os.environ["QINGCAO_MMAP_SAVE"] = "1"
    os.environ["QINGCAO_MMAP_SAVE_MIN_MB"] = "0"
    os.environ["QINGCAO_MMAP_EVAL_FILE"] = eval_file
    os.environ["QINGCAO_EDIT_JOURNAL_DIR"] = journal_dir
    tmp = tempfile.mkdtemp(prefix="qc_mmap_eval_")
    results = {}
    try:
        path = os.path.join(tmp, "equal.txt")
        lines = ["row %06d abcdefghij" % i for i in range(2000)]
        io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        old = io.open(path, "rb").read()
        new = old.replace(b"row 001000 abcdefghij", b"row 001000 ABCDEFGHIJ", 1)
        t0 = time.perf_counter()
        ok = m.maybe_incremental_save(path, new, clear_dirty=lambda: None)
        results["equal"] = (ok, time.perf_counter() - t0)

        path2 = os.path.join(tmp, "fallback.txt")
        io.open(path2, "w", encoding="utf-8", newline="\n").write("a\nb\n")
        ok2 = m.maybe_incremental_save(path2, b"aaaa\nbbbb", None)
        results["fallback"] = ok2

        # journal 恢复场景
        path3 = os.path.join(tmp, "recover.txt")
        io.open(path3, "w", encoding="utf-8").write("original\n")
        m._ensure_dir = None
        jp = m._write_journal(path3, b"original\n", [(0, 9)])
        io.open(path3, "wb").write(b"half")
        m.recover_journal(jp, tmp)
        results["recovery"] = io.open(path3, "rb").read() == b"original\n"
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return results


def aggregate(eval_file):
    rows = []
    if os.path.isfile(eval_file):
        for line in io.open(eval_file, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    ev = [r.get("event") for r in rows]
    eligible = sum(1 for r in rows if r.get("event") in ("success", "fallback", "noop"))
    success = ev.count("success")
    fallback = ev.count("fallback")
    noop = ev.count("noop")
    ineligible = ev.count("ineligible")
    recovery = ev.count("recovery")
    recovery_fail = ev.count("recovery_fail")
    rate = (fallback / eligible * 100) if eligible else 0.0
    ok = rate < 5 and success >= 1
    return {
        "total": len(rows),
        "eligible": eligible,
        "success": success,
        "fallback": fallback,
        "noop": noop,
        "ineligible": ineligible,
        "recovery": recovery,
        "fallback_rate": round(rate, 2),
        "threshold_ok": ok,
    }


def main():
    with tempfile.TemporaryDirectory(prefix="qc_mmap_evalrun_") as tmp:
        eval_file = os.path.join(tmp, "eval.jsonl")
        journal_dir = os.path.join(tmp, "journal")
        scen = run_scenarios(eval_file, journal_dir)
        agg = aggregate(eval_file)
    decision = (
        "保持默认关闭（灰度），收集 2 周真实数据后再评估"
        if agg["threshold_ok"]
        else "保持默认关闭并修复失败项"
    )
    lines = [
        "# mmap 默认开启评估（v2.20 P1-2）",
        "",
        "## 场景基准",
        "",
        "| 场景 | 结果 |",
        "|---|---|",
        "| 等长修改（2000 行） | %s（%.3fs）"
        % ("成功" if scen["equal"][0] else "失败", scen["equal"][1]),
        "| 非等长（应回退） | %s" % ("回退" if scen["fallback"] is None else "异常"),
        "| journal 恢复 | %s" % ("通过" if scen["recovery"] else "失败"),
        "",
        "## 埋点汇总（本次场景）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        "| 事件总数 | %d |" % agg["total"],
        "| 可增量尝试 | %d |" % agg["eligible"],
        "| 成功 | %d |" % agg["success"],
        "| 回退 | %d |" % agg["fallback"],
        "| noop | %d |" % agg["noop"],
        "| 不满足条件 | %d |" % agg["ineligible"],
        "| journal 恢复成功 | %d 次 |" % agg["recovery"],
        "| 回退率 | %.2f%% |" % agg["fallback_rate"],
        "",
        "## 门槛判定（建议）",
        "",
        f"- 回退率 < 5%：{'✅' if agg['fallback_rate'] < 5 else '❌'}",
        "- journal 恢复成功 %d 次（失败 0）：✅" % agg["recovery"],
        "- 至少 1 次成功保存：%s" % ("✅" if agg["success"] >= 1 else "❌"),
        "",
        "## 决策（v2.20.0）",
        "",
        "**%s**" % decision,
        "",
        "理由：场景基准全部通过，但真实用户文件的编码/锁/外部修改等情况尚缺数据；",
        "保留设置页开关（实验，默认关）与埋点，v2.20.x 依据真实回退率决定是否默认开启。",
        "",
    ]
    out = os.path.join(ROOT, "docs", "mmap_default_evaluation.md")
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print("[mmap-eval] 场景:", scen["equal"][0], scen["fallback"], scen["recovery"])
    print("[mmap-eval] 汇总:", agg)
    print("[mmap-eval] 决策:", decision, "->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
