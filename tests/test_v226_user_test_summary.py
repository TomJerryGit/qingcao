# -*- coding: utf-8 -*-
"""用户测试汇总脚本"""

import io
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_summarize_and_render(tmp_path):
    from tools.user_test_summary import load, render, summarize

    p = tmp_path / "records.csv"
    p.write_text(
        "user_id,background,version,task1_install,task2_run,task3_save,"
        "task4_search,task5_theme,task6_reopen,total_time_sec,blockers,"
        "quote,severity,would_use_again,notes\n"
        "U01,dev,v1,完成,完成,完成,完成,完成,完成,120,,,P1,yes,\n"
        "U02,user,v1,完成,未完成,,,,,300,找不到运行,,P0,no,\n",
        encoding="utf-8",
    )
    rows = load(str(p))
    assert len(rows) == 2
    report = summarize(rows)
    assert report["total"] == 2
    assert report["tasks"]["安装启动"] == (2, 2)
    assert report["tasks"]["打开并运行"] == (1, 2)
    assert report["p0"] == 1 and report["p1"] == 1
    text = render(report, "v1")
    assert "50%" in text and "P0" in text
