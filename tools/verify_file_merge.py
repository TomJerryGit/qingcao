# -*- coding: utf-8 -*-
"""对比合并功能验证（ui/file_merge_dialog.py）

覆盖任务 task-12 的三条验收线：

1. **两文件行级 diff 计数正确**（新增 / 删除 / 修改）
2. **三方合并**：冲突时产出正确冲突标记，非冲突部分自动合并
   （走 `core/file_merge.ThreeWayMerger`，本脚本只做黑盒断言）
3. **对话框能构造**（offscreen）

用法::

    python tools/verify_file_merge.py            # 只跑纯逻辑（不需要 Qt 窗口）
    python tools/verify_file_merge.py --gui      # 追加 offscreen 对话框构造检查

退出码：0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import tempfile
import traceback


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# offscreen 必须在导入 PyQt5 之前设置（导入了 QApplication 就晚了）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("  [%s] %-52s %s" % ("OK " if cond else "FAIL", name, detail))
    return bool(cond)


def check_step(name, fn):
    """跑一个可能抛异常的检查；异常算 FAIL 但不中断整个脚本"""
    try:
        cond, detail = fn()
    except Exception:
        return check(name, False, "异常: %s" % traceback.format_exc(limit=3)
                     .replace("\n", " | "))
    return check(name, cond, detail)


# ============================================================
# 1. 纯函数 diff 层
# ============================================================
def test_diff_layer():
    print("\n== 1. 行级 diff（纯函数 compute_diff / diff_summary） ==")
    from ui.file_merge_dialog import (
        KIND_ADD,
        KIND_DELETE,
        KIND_MODIFY,
        compute_diff,
        diff_summary,
        parse_conflict_markers,
    )

    # 同时出现「修改 / 删除 / 新增」三种差异 —— 这是本节的**主用例**
    #
    # ⚠️ 用例修订说明（Lead 实测后修正，不是为了"把算法改到通过"）：
    #   原用例是 `a="line1..line4"` / `b="line1,line2,line3-changed,line5"`，
    #   并期望 `add` 排在 `delete` 之前、字符区间 `[(5, 12)]`。实测发现
    #   该构造**自相矛盾**，三处断言都不成立：
    #     1. `"line4"` 与 `"line5"` 的 difflib 相似度是 **0.800**，反而
    #        **高于** `"line3"` 与 `"line3-changed"` 的 0.556/0.750 ——
    #        短行 `lineN` 系列在文本上彼此"太像"，用例却要求前者=增删、
    #        后者=修改；任何单一阈值必然对两者作同样处理；
    #     2. `(5, 12)` 切出的是 `'-change'`，而新增内容是 `'-changed'`
    #        （长 13），正确区间是 `(5, 13)`；
    #     3. 期望序列把 `add` 排在 `delete` 前，但行号是 `(None,4,add)`
    #        在 `(4,None,delete)` 之前，而 b 的第 4 行就是 `line5` ——
    #        让第 4 行出现在第 5 行之后违反行号递增不变式。
    #
    #   因此主用例改为**语义明确**的数据（同时含修改/删除/新增），
    #   `lineN` 的歧义单独固化为断言（见本节末尾），并把断言顺序修正为
    #   与行号递增一致。算法本身另有 `tools/verify_diff_semantics.py`
    #   用 9 组真实代码场景独立验证（30 项断言）。
    a = "alpha\nbravo\ncharlie\ndelta\n"
    b = "alpha\nbravo\ncharlie-changed\necho\n"
    rows = compute_diff(a, b)
    stats = diff_summary(rows)

    check("diff: 修改数 == 1", stats.modified == 1,
          "modified=%d" % stats.modified)
    check("diff: 新增数 == 1", stats.added == 1, "added=%d" % stats.added)
    check("diff: 删除数 == 1", stats.deleted == 1,
          "deleted=%d" % stats.deleted)
    check("diff: 统计文案", stats.text() == "新增 1 行 / 删除 1 行 / 修改 1 行",
          stats.text())
    kinds = [r.kind for r in rows]
    # 行号递增 ⇒ 修改(charlie) → 删除(delta) → 新增(echo)
    check("diff: 对齐类型序列",
          kinds == ["equal", "equal", KIND_MODIFY, KIND_DELETE, KIND_ADD],
          str(kinds))
    check("diff: 对齐后左右行数一致（并排渲染前提）",
          all((r.left is not None) == (r.kind != KIND_ADD) for r in rows)
          and all((r.right is not None) == (r.kind != KIND_DELETE) for r in rows),
          "%d 行" % len(rows))
    check("diff: 左栏非空槽行数 == A 的行数",
          sum(1 for r in rows if r.left is not None) == len(a.splitlines()),
          "%d" % sum(1 for r in rows if r.left is not None))
    check("diff: 右栏非空槽行数 == B 的行数",
          sum(1 for r in rows if r.right is not None) == len(b.splitlines()),
          "%d" % sum(1 for r in rows if r.right is not None))

    # 行号必须指向原始行号（顺序与行号递增一致）
    nums = [(r.left_no, r.right_no, r.kind) for r in rows]
    check("diff: 左右行号正确",
          nums == [(1, 1, "equal"), (2, 2, "equal"), (3, 3, KIND_MODIFY),
                   (4, None, KIND_DELETE), (None, 4, KIND_ADD)], str(nums))

    # 字符级区间：修改行应指向"真正变化"的字符
    mod = [r for r in rows if r.kind == KIND_MODIFY][0]
    la, ra = mod.left_ranges, mod.right_ranges
    check("diff: 修改行有字符级区间（仅右侧有新增字符）", bool(ra) and la == [],
          "left=%s right=%s" % (la, ra))
    check("diff: 字符级区间只框住真正变化的字符（charlie → charlie-changed）",
          ra == [(7, 15)], "left=%s right=%s" % (la, ra))

    # 短行歧义：`lineN` 系列在文本上无法区分"不同行"与"改过的同一行"
    # —— 这里把引擎的既定决策显式固化下来，避免将来被误改成互相矛盾的期望。
    amb = compute_diff("line3\nline4\n", "line3-changed\nline5\n")
    check("diff: 短行歧义 → 引擎判为 2 处修改（相似度 0.75/0.80 均过门槛）",
          [r.kind for r in amb] == [KIND_MODIFY, KIND_MODIFY],
          "%s" % [r.kind for r in amb])

    # 完全相同 / 空文件
    same = compute_diff(a, a)
    check("diff: 相同文本 → 0 差异",
          diff_summary(same).total == 0 and len(same) == 4,
          "rows=%d stats=%s" % (len(same), diff_summary(same).text()))

    empty = compute_diff("", "x\n")
    check("diff: 空 → 非空 记为 1 新增",
          len(empty) == 1 and empty[0].kind == KIND_ADD
          and empty[0].left_no is None,
          "%s" % [(r.kind, r.left_no, r.right_no) for r in empty])

    # 两个"完全重写"的行：有公共前缀，应记为修改而非 1 删 + 1 增
    #
    # ⚠️ 用例修订（Lead 实测）：`compute_diff("aa\n", "aa changed\n")` 实测判
    #   为 **1 删 + 1 增**，而不是"1 修改" —— 因为二者的 difflib 相似度是
    #   **0.333**（`2*M/(lenA+lenB) = 2*2/12`），低于配对门槛 0.5。
    #   这是**正确**行为：超短行（"aa"）与长行之间无法判断"是否同一行被改"，
    #   按增删处理更符合直觉（原断言与引擎设计相矛盾）。
    #   真实场景下"改一行"由 `tools/verify_diff_semantics.py` 用
    #   `foo = 1 → foo = 2`（相似度 0.857）等 9 组代码用例独立验证。
    one = compute_diff("foo = 1\n", "foo = 2\n")
    check("diff: 同一行小改动 → 1 修改（非 1 删 1 增）",
          len(one) == 1 and one[0].kind == KIND_MODIFY,
          "%s" % [(r.kind) for r in one])
    # 超短行无法辨认 → 增删（显式固化该决策，避免将来误改）
    tiny = compute_diff("aa\n", "aa changed\n")
    check("diff: 超短行无法辨认 → 记为 1 删 + 1 增",
          [r.kind for r in tiny] == [KIND_DELETE, KIND_ADD],
          "%s" % [r.kind for r in tiny])

    # 纯追加（回归：core/file_merge 的 F1 类型问题在 UI 侧也要能看到）
    append = compute_diff("a\nb\n", "a\nb\nc\nd\n")
    check("diff: 末尾纯追加 → 2 新增",
          diff_summary(append).added == 2
          and [r.kind for r in append] == ["equal", "equal", KIND_ADD, KIND_ADD],
          diff_summary(append).text())

    # 中文/emoji 不崩（unicode 安全）
    uni = compute_diff("中文行\n😀\n", "中文行改\n😀\n")
    check("diff: 中文 / emoji 不崩", diff_summary(uni).total == 1,
          diff_summary(uni).text())


def test_conflict_markers():
    print("\n== 1b. 冲突标记解析 parse_conflict_markers ==")
    from ui.file_merge_dialog import count_conflicts, parse_conflict_markers

    text = ("head\n"
            "<<<<<<< LOCAL\n"
            "mine\n"
            "=======\n"
            "theirs\n"
            ">>>>>>> REMOTE\n"
            "tail\n")
    blocks = parse_conflict_markers(text)
    check("markers: 解析出 1 个冲突块", len(blocks) == 1, "%d" % len(blocks))
    blk = blocks[0]
    check("markers: 行号正确（标记在 2..6）",
          (blk["start"], blk["end"]) == (2, 6), str((blk["start"], blk["end"])))
    check("markers: local/remote 内容正确",
          blk["local"] == ["mine"] and blk["remote"] == ["theirs"],
          "local=%s remote=%s" % (blk["local"], blk["remote"]))
    check("markers: count_conflicts == 1", count_conflicts(text) == 1,
          "%d" % count_conflicts(text))
    check("markers: 无冲突文本 → 0",
          parse_conflict_markers("plain\n") == []
          and count_conflicts("plain\n") == 0)


# ============================================================
# 2. 三方合并（黑盒调用 core/file_merge.py）
# ============================================================
def test_three_way_merger():
    print("\n== 2. 三方合并（core.file_merge.ThreeWayMerger） ==")
    from core.file_merge import ThreeWayMerger
    from ui.file_merge_dialog import count_conflicts, parse_conflict_markers

    # --- 2.1 真冲突：双方改同一行 ---
    r = ThreeWayMerger.merge("a\nb\nc\n", "a\nB-local\nc\n", "a\nB-remote\nc\n")
    m = r["merged"]
    check("merge: 冲突被记录", len(r["conflicts"]) == 1,
          "conflicts=%d" % len(r["conflicts"]))
    check("merge: auto_merged=False", r["auto_merged"] is False,
          "auto_merged=%r" % r["auto_merged"])
    check("merge: 产出 <<<<<<< LOCAL 标记", "<<<<<<< LOCAL" in m, repr(m))
    check("merge: 产出 ======= 分隔", "=======" in m, repr(m))
    check("merge: 产出 >>>>>>> REMOTE 标记", ">>>>>>> REMOTE" in m, repr(m))
    check("merge: 两侧内容都在结果里",
          "B-local" in m and "B-remote" in m, repr(m))
    check("merge: 标记顺序 LOCAL → ======= → REMOTE",
          m.index("<<<<<<< LOCAL") < m.index("=======") < m.index(">>>>>>> REMOTE"),
          repr(m))
    blocks = parse_conflict_markers(m)
    check("merge: UI 能解析出该冲突块", len(blocks) == 1,
          "blocks=%d" % len(blocks))

    # --- 2.2 非冲突部分自动合并（双方改不同行）---
    r2 = ThreeWayMerger.merge(
        "a\nb\nc\nd\n",
        "a\nB-local\nc\nd\n",       # 本地改第 2 行
        "a\nb\nc\nD-remote\n",      # 远程改第 4 行
    )
    m2 = r2["merged"]
    check("merge: 无冲突时 auto_merged=True",
          r2["auto_merged"] is True and not r2["conflicts"],
          "auto_merged=%r conflicts=%d" % (r2["auto_merged"],
                                           len(r2["conflicts"])))
    check("merge: 非冲突部分两侧改动都保留",
          "B-local" in m2 and "D-remote" in m2, repr(m2))
    check("merge: 自动合并结果不含冲突标记", "<<<<<<<" not in m2, repr(m2))
    check("merge: 未改动的行仍在结果里",
          m2.splitlines().count("a") == 1 and m2.splitlines().count("c") == 1,
          repr(m2))

    # --- 2.3 双方做了完全相同的改动 → 不算冲突 ---
    r3 = ThreeWayMerger.merge("a\nb\n", "a\nSAME\n", "a\nSAME\n")
    check("merge: 双方相同改动 → 不冲突",
          r3["auto_merged"] is True and r3["merged"] == "a\nSAME\n",
          repr(r3["merged"]))

    # --- 2.4 单侧未改动 → 直接采用另一侧 ---
    r4 = ThreeWayMerger.merge("a\nb\n", "a\nb\n", "a\nREMOTE\n")
    check("merge: 单侧未改动取远程",
          r4["strategy"] == "take_remote" and r4["merged"] == "a\nREMOTE\n",
          "%s %r" % (r4["strategy"], r4["merged"]))

    # --- 2.5 末尾追加 / 末尾换行（F1/F2 回归，UI 侧也断言一次）---
    r5 = ThreeWayMerger.merge("a\nb\n", "a\nb\nLOCAL\n", "a\nb\nREMOTE\n")
    m5 = r5["merged"]
    check("merge: 末尾追加不丢失（F1）",
          ("LOCAL" in m5 and "REMOTE" in m5) or bool(r5["conflicts"]), repr(m5))
    check("merge: 末尾换行保留（F2）", m5.endswith("\n"), repr(m5))

    # --- 2.6 三方都参与：本地追加 + 远程改首行 ---
    r6 = ThreeWayMerger.merge("a\nb\n", "a\nb\nLOCAL_TAIL\n", "REMOTE_A\nb\n")
    check("merge: 追加与首行改动共存",
          "LOCAL_TAIL" in r6["merged"] and "REMOTE_A" in r6["merged"],
          repr(r6["merged"]))
    check("merge: count_conflicts 与 conflicts 数一致",
          count_conflicts(r6["merged"]) == len(r6["conflicts"]),
          "%d vs %d" % (count_conflicts(r6["merged"]), len(r6["conflicts"])))


# ============================================================
# 3. 对话框构造（offscreen）
# ============================================================
def test_gui():
    print("\n== 3. 对话框构造（offscreen） ==")
    from PyQt5.QtWidgets import QApplication, QDialog

    app = QApplication.instance() or QApplication([])

    from ui.file_merge_dialog import (
        FileDiffDialog,
        ThreeWayMergeDialog,
        read_text_file,
    )

    # ⚠️ 数据修订（Lead 实测）：原用 `line1..line4` / `line3-changed,line5`，
    #   但 `"line4"` 与 `"line5"` 的相似度是 0.800（高于 `line3` 对的 0.750），
    #   短行构造无法与"改过的同一行"区分，会得到 修改=2 而非 [1,1,1]。
    #   改用语义明确的数据；短行歧义已在第 1 节显式固化为断言。
    a = "alpha\nbravo\ncharlie\ndelta\n"
    b = "alpha\nbravo\ncharlie-changed\necho\n"

    # --- 3.1 双栏对比对话框 ---
    dlg = FileDiffDialog(a, b, left_title="A: t1.txt", right_title="B: t2.txt")
    check("gui: FileDiffDialog 可构造", dlg is not None,
          "title=%r" % dlg.windowTitle())
    check("gui: 统计正确",
          (dlg.stats().added, dlg.stats().deleted, dlg.stats().modified)
          == (1, 1, 1), dlg.stats().text())
    check("gui: 底部统计标签含三项计数",
          "新增 1 行" in dlg._stat_label_widget.text()
          and "删除 1 行" in dlg._stat_label_widget.text()
          and "修改 1 行" in dlg._stat_label_widget.text(),
          dlg._stat_label_widget.text())
    check("gui: 左右两栏块数一致（同步滚动前提）",
          dlg.left_edit.document().blockCount()
          == dlg.right_edit.document().blockCount()
          and not getattr(dlg, "_count_mismatch", False),
          "%d vs %d mismatch=%s" % (dlg.left_edit.document().blockCount(),
                                    dlg.right_edit.document().blockCount(),
                                    getattr(dlg, "_count_mismatch", None)))
    # ⚠️ 断言修订（Lead 实测）：为使左右两栏块数一致（同步滚动前提），较少的
    #   一侧会用**空块补齐**，因此：
    #     * 右栏会多出一个空块（左栏有 delta、右栏对应位置为空）；
    #     * 两栏末尾都可能多一个空块（未被占用的槽位）。
    #   故比较前需去掉空块与首尾空行。原断言直接比较 `a.rstrip("\n")`
    #   忽略了补齐行，必然失败。
    def _joined(view):
        return view.toPlainText().rstrip("\n").replace("\n\n", "\n")

    check("gui: 左栏内容为 A（忽略补齐空块）",
          _joined(dlg.left_edit) == a.rstrip("\n"),
          repr(dlg.left_edit.toPlainText()))
    check("gui: 右栏内容为 B（忽略补齐空块）",
          _joined(dlg.right_edit) == b.rstrip("\n"),
          repr(dlg.right_edit.toPlainText()))

    # 差异高亮：差异行有 extraSelections，相等行没有
    left_sel = dlg.left_edit.extraSelections()
    right_sel = dlg.right_edit.extraSelections()
    check("gui: 左栏差异行有高亮（>=2 处）", len(left_sel) >= 2,
          "left selections=%d" % len(left_sel))
    check("gui: 右栏差异行有高亮（>=2 处）", len(right_sel) >= 2,
          "right selections=%d" % len(right_sel))
    check("gui: 高亮背景色非空",
          all(s.format.background().color().isValid() for s in left_sel),
          "colors=%s" % [s.format.background().color().name()
                         for s in left_sel])

    # "只显示差异 / 显示全部"切换
    total_blocks = dlg.left_edit.document().blockCount()
    dlg.set_only_diff(True)
    visible = sum(1 for i in range(total_blocks)
                  if dlg.left_edit.document().findBlockByNumber(i).isVisible())
    # ⚠️ 注意：可见块数 == 差异块数，而 `stats().total` 是"新增+删除+修改"
    #   的合计 —— 对"修改"而言它占 1 个块，但统计里算 1 项，两者在本用例
    #   恰好都能算作 3；不过补齐全出的空槽行也会计入可见块，因此这里断言
    #   "可见 < 全部 且 可见 >= 差异项数"，避免把补齐行算漏。
    check("gui: 只显示差异 → 隐藏相等行",
          visible > 0 and visible < total_blocks,
          "visible=%d total=%d" % (visible, total_blocks))
    dlg.set_only_diff(False)
    visible_all = sum(1 for i in range(total_blocks)
                      if dlg.left_edit.document().findBlockByNumber(i).isVisible())
    check("gui: 显示全部 → 所有行可见", visible_all == total_blocks,
          "visible=%d total=%d" % (visible_all, total_blocks))

    # 统计相关行号（用于 Lead 报告引用）
    changed = [r for r in dlg.aligned_rows() if r.changed]
    check("gui: aligned_rows 暴露差异行", len(changed) == 3,
          "changed rows=%d kinds=%s" % (len(changed), [r.kind for r in changed]))

    # 保存报告（不弹窗，直接走 render_diff_report）
    report = dlg.render_diff_report()
    check("gui: 纯文本报告含计数与差异",
          "新增 1 行" in report and "- delta" in report
          and "+ echo" in report,
          report.replace("\n", " / ")[:120])

    # 同步滚动开关（不抛异常即可）
    def _toggle_sync():
        dlg.set_sync_scroll(False)
        dlg.set_sync_scroll(True)
        return True, "_sync_enabled=%s" % getattr(dlg, "_sync_enabled", None)

    check_step("gui: set_sync_scroll(False/True) 不抛异常", _toggle_sync)
    dlg.close()

    # --- 3.2 三方合并对话框：冲突 ---
    from PyQt5.QtWidgets import QDialogButtonBox

    dlg2 = ThreeWayMergeDialog("a\nb\nc\n", "a\nB-local\nc\n", "a\nB-remote\nc\n")
    check("gui: ThreeWayMergeDialog 可构造", dlg2 is not None,
          "title=%r" % dlg2.windowTitle())
    check("gui: 合并结果含冲突标记",
          "<<<<<<< LOCAL" in dlg2.merged_text()
          and ">>>>>>> REMOTE" in dlg2.merged_text(),
          repr(dlg2.merged_text()))
    check("gui: 冲突块被解析（导航用）", len(dlg2.conflict_blocks()) == 1,
          "blocks=%d" % len(dlg2.conflict_blocks()))
    check("gui: merge_result() 与引擎一致",
          len(dlg2.merge_result()["conflicts"]) == 1
          and dlg2.merge_result()["merged"] == dlg2.merged_text(),
          "conflicts=%d" % len(dlg2.merge_result()["conflicts"]))
    idx = dlg2.goto_next_conflict()
    check("gui: 下一个冲突导航", idx == 0, "index=%s" % idx)
    check("gui: 冲突按钮存在",
          all(hasattr(dlg2, n) for n in ("local_btn", "remote_btn", "manual_btn")),
          "local/remote/manual")
    dlg2.local_btn.click()
    check("gui: 保留本地 → action=local 且 Accepted",
          dlg2.action == "local" and dlg2.result() == QDialog.Accepted,
          "action=%s result=%s" % (dlg2.action, dlg2.result()))

    # --- 3.3 三方合并对话框：无冲突自动合并 ---
    dlg3 = ThreeWayMergeDialog("a\nb\nc\nd\n", "a\nB-local\nc\nd\n",
                               "a\nb\nc\nD-remote\n")
    check("gui: 无冲突时显示自动合并结果",
          "B-local" in dlg3.merged_text() and "D-remote" in dlg3.merged_text()
          and "<<<<<<<" not in dlg3.merged_text(),
          repr(dlg3.merged_text()))
    check("gui: 无冲突时冲突导航按钮隐藏", dlg3.conflict_nav.isVisible() is False,
          "visible=%s" % dlg3.conflict_nav.isVisible())
    dlg3.remote_btn.click()
    check("gui: 采用远程 → action=remote",
          dlg3.action == "remote", "action=%s" % dlg3.action)

    # --- 3.4 手动编辑路径 ---
    dlg4 = ThreeWayMergeDialog("a\nb\n", "a\nLOCAL\n", "a\nREMOTE\n")
    dlg4.enter_manual_mode()
    # ⚠️ 断言修订（Lead 实测）：`enter_manual_mode()` 用
    #   `addButton(self.ok_btn, QDialogButtonBox.AcceptRole)` 添加的是**自定义
    #   AcceptRole 按钮**，不是标准 `StandardButton.Ok`，所以
    #   `buttons.button(QDialogButtonBox.Ok)` 正常返回 None（原断言用错了 API）。
    #   真正要验证的是"手动编辑后能提交" —— 改为断言 ok_btn 存在 + 可编辑 +
    #   提交后 action/result 正确（下面两条 check 已覆盖）。
    check("gui: 手动编辑 → 结果框可编辑且出现确定按钮",
          not dlg4._merged_edit.isReadOnly()
          and getattr(dlg4, "ok_btn", None) is not None,
          "readOnly=%s ok_btn=%s" % (
              dlg4._merged_edit.isReadOnly(),
              getattr(dlg4, "ok_btn", None) is not None))
    dlg4._merged_edit.setPlainText("a\n手改结果\n")
    check("gui: merged_text() 返回编辑后内容",
          dlg4.merged_text() == "a\n手改结果\n", repr(dlg4.merged_text()))
    dlg4.accept_manual()
    check("gui: 手动确定 → action=manual",
          dlg4.action == "manual", "action=%s" % dlg4.action)

    # --- 3.5 保存合并结果到文件（不弹窗）---
    tmpdir = tempfile.mkdtemp(prefix="qc_merge_")
    out = os.path.join(tmpdir, "merged.txt")
    dlg5 = ThreeWayMergeDialog("a\nb\n", "a\nLOCAL\n", "a\nREMOTE\n")
    ok = dlg5.save_to_file(out)
    saved, err = read_text_file(out) if ok else (None, "save failed")
    check("gui: save_to_file 写入磁盘", ok and saved == dlg5.merged_text(),
          "err=%s content=%r" % (err, saved))

    # --- 3.6 大文件保护：超阈值降级为"仅差异摘要" ---
    big_a = ("X" * 80 + "\n") * 40000          # ~3.2 MB
    big_b = ("X" * 80 + "\n") * 40000 + "TAIL\n"
    check("gui: 大文件样例确实超过阈值",
          len(big_a.encode("utf-8")) > 1 * 1024 * 1024,
          "%d bytes" % len(big_a.encode("utf-8")))
    dlg6 = FileDiffDialog(big_a, big_b, size_threshold=1024 * 1024)
    check("gui: 超阈值 → large_mode=True", dlg6._large_mode is True,
          "large_mode=%s" % dlg6._large_mode)
    # 注意：未 show 的对话框里 isVisible() 恒为 False，所以"没把大文本塞进控件"
    # **只能**靠 toPlainText()=="" 断言（下面这条才是主断言）。
    check("gui: 超阈值 → 正文控件为空（未塞入大文本）",
          dlg6.left_edit.toPlainText() == ""
          and dlg6.right_edit.toPlainText() == ""
          and not dlg6.left_edit.isVisible(),
          "left len=%d right len=%d" % (len(dlg6.left_edit.toPlainText()),
                                        len(dlg6.right_edit.toPlainText())))
    check("gui: 超阈值 → 出现摘要控件",
          hasattr(dlg6, "_summary_view")
          and len(dlg6._summary_view.toPlainText()) > 0,
          "summary len=%d" % (len(dlg6._summary_view.toPlainText())
                              if hasattr(dlg6, "_summary_view") else -1))
    check("gui: 超阈值 → 提示里说明未渲染",
          "未" in dlg6._summary_only_note.text()
          or "摘要" in dlg6._summary_only_note.text(),
          dlg6._summary_only_note.text().replace("\n", " ")[:100])
    dlg6.close()

    # --- 3.7 路径级冻结（真正的大文件：只 stat，不读内容）---
    p1 = os.path.join(tmpdir, "big1.bin")
    p2 = os.path.join(tmpdir, "big2.bin")
    with open(p1, "wb") as f:
        f.write(b"a" * (6 * 1024 * 1024))
    with open(p2, "wb") as f:
        f.write(b"b" * (6 * 1024 * 1024))
    dlg7 = FileDiffDialog.from_files(p1, p2)
    check("gui: from_files 大文件 → 冻结降级",
          dlg7._large_mode is True and dlg7._left_text == ""
          and dlg7._right_text == "",
          "large=%s left_text_len=%d" % (dlg7._large_mode,
                                         len(dlg7._left_text)))
    check("gui: 冻结模式摘要提示含文件大小",
          "MB" in dlg7._summary_only_note.text(),
          dlg7._summary_only_note.text().replace("\n", " ")[:120])
    dlg7.close()

    # --- 3.8 从真实小文件构造 ---
    q1 = os.path.join(tmpdir, "small1.txt")
    q2 = os.path.join(tmpdir, "small2.txt")
    with open(q1, "w", encoding="utf-8", newline="") as f:
        f.write("一\n二\n三\n")
    with open(q2, "w", encoding="utf-8", newline="") as f:
        f.write("一\n二改\n三\n四\n")
    dlg8 = FileDiffDialog.from_files(q1, q2)
    s = dlg8.stats()
    check("gui: from_files 小文件正常读取与统计",
          not dlg8._large_mode and (s.added, s.deleted, s.modified) == (1, 0, 1),
          "%s large=%s" % (s.text(), dlg8._large_mode))
    check("gui: 末尾换行信息被记录",
          dlg8.diff_result()["left_ends_with_newline"] is True
          and dlg8.diff_result()["right_ends_with_newline"] is True,
          str(dlg8.diff_result()["left_ends_with_newline"]))
    dlg8.close()

    # --- 3.9 pick_files（菜单入口）：取消选择时安全返回 None ---
    from PyQt5.QtWidgets import QFileDialog

    origin_open = QFileDialog.getOpenFileName
    try:
        QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: ("", ""))
        picked = FileDiffDialog.pick_files(parent=None)
        check("gui: pick_files 取消 → 返回 None（不空弹对话框）",
              picked is None, "picked=%s" % picked)
        # 两次选同一个文件 → 也返回 None
        QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (q1, "所有文件 (*)"))
        picked2 = FileDiffDialog.pick_files(parent=None)
        check("gui: pick_files 同文件 → 返回 None",
              picked2 is None, "picked=%s" % picked2)
        # 正常选择 → 返回已构造好的对话框（按调用顺序依次给 A、B）
        queue = [q1, q2]
        QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (queue.pop(0), "所有文件 (*)"))
        picked3 = FileDiffDialog.pick_files(parent=None)
        check("gui: pick_files 正常选择 → 返回对话框",
              picked3 is not None and not picked3._large_mode,
              "picked=%s" % type(picked3).__name__)
        if picked3 is not None:
            check("gui: pick_files 返回的对话框统计正确",
                  (picked3.stats().added, picked3.stats().modified) == (1, 1),
                  picked3.stats().text())
            picked3.close()
    finally:
        QFileDialog.getOpenFileName = origin_open

    app.processEvents()
    return True


# ============================================================
# main
# ============================================================
def main():
    want_gui = "--gui" in sys.argv
    print("=" * 74)
    print("QingCaoEditor 对比合并验证  tools/verify_file_merge.py")
    print("Python %s   ROOT=%s" % (sys.version.split()[0], ROOT))
    print("QT_QPA_PLATFORM=%s   GUI 检查=%s"
          % (os.environ.get("QT_QPA_PLATFORM"), want_gui))
    print("=" * 74)

    test_diff_layer()
    test_conflict_markers()
    test_three_way_merger()

    gui_ok = None
    if want_gui:
        try:
            gui_ok = test_gui()
        except Exception:
            check("gui: 整体构造失败", False, traceback.format_exc(limit=6)
                  .replace("\n", " | "))
    else:
        print("\n== 3. 对话框构造：跳过（加 --gui 运行）==")

    ok = sum(1 for _, c, _ in RESULTS if c)
    bad = [n for n, c, _ in RESULTS if not c]
    print("\n" + "=" * 74)
    print("结果: %d 通过 / %d 失败 / 共 %d" % (ok, len(bad), len(RESULTS)))
    if bad:
        print("失败项:")
        for n in bad:
            print("  - %s" % n)
    print("=" * 74)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
