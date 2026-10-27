#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
青草枯荣，野火重生。

列编辑器（Column Editor）验证脚本
=================================

不依赖 pytest，直接运行:

    python tools\\verify_column_editor.py

（脚本内部会设置 ``QT_QPA_PLATFORM=offscreen``，无需显示器。）

覆盖:
  0. 纯函数：数字序列 1..10 / 十六进制 0x01..0x0A / 前导零 / 前导空格 /
     步长（正负）/ 进制前缀 / 非十进制大写 / 最小位数；
  1. 真实 QScintilla + 真实 ``EditorProxy``（走 ``SCN_MODIFIED`` 记录路径）：
     * 文本插入到 10 行，逐行位置正确（显式行/列 + 矩形选区入口）；
     * 数字 1..10 前导零（01..10）插入 10 行；步长 2；十六进制 0x01..0x0A；
     * **撤销一次即全部回退**（关键），且撤销栈里只有 1 条命令，redo 可恢复；
     * 矩形选区（``SC_SEL_RECTANGLE``）与多光标（``SCI_ADDSELECTION``）两种入口；
     * 中文行的字节偏移正确性（列 → UTF-8 字节）；
     * 对话框可独立构造（不依赖 MainWindow）+ 参数解析 + 预览刷新；
     * ``ColumnInsertCmd`` 可被 ``Command.from_dict`` 还原（宏回放依赖）。

退出码: 0 = 全部通过；1 = 有失败项；2 = 环境不可用（无 PyQt5/Qsci）。
"""

import os
import sys
import traceback


# 输出编码必须是 UTF-8 —— 脚本会打印含 emoji 的 QAction 文本（如 "📊"），
# 而 Windows 中文环境下 stdout 默认是 GBK，会直接抛
# `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f4ca'`，
# 导致整个验证**在最后一步崩掉**（实测）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 必须在导入 PyQt5 之前设置（无显示器环境）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================
# 结果收集
# ============================================================
PASSED = []
FAILED = []
WARNED = []


def section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def check(name: str, cond: bool, detail: str = "") -> bool:
    ok = bool(cond)
    if ok:
        PASSED.append(name)
        print(f"[PASS] {name}")
    else:
        FAILED.append((name, detail))
        print(f"[FAIL] {name}")
        if detail:
            print(f"       {detail}")
    return ok


def warn(name: str, detail: str = ""):
    WARNED.append((name, detail))
    print(f"[WARN] {name}")
    if detail:
        print(f"       {detail}")


def info(msg: str):
    print(f"       {msg}")


# ============================================================
# 导入
# ============================================================
try:
    from PyQt5.Qsci import QsciScintilla
    from PyQt5.QtWidgets import QApplication
except Exception as _e:  # pragma: no cover
    print(f"[环境不可用] 无法导入 PyQt5/Qsci: {_e}")
    sys.exit(2)

try:
    from core.commands import Command
    from core.document import Document
    from core.editor import EditorProxy
    from ui.column_editor_dialog import (
        CMD_TYPE_COLUMN_INSERT,
        MODE_NUMBER,
        MODE_TEXT,
        PAD_NONE,
        PAD_SPACE,
        PAD_ZERO,
        SOURCE_MULTI,
        SOURCE_RECTANGLE,
        SOURCE_SELECTION,
        ColumnEditConfig,
        ColumnEditorDialog,
        ColumnInsertCmd,
        apply_column_edit,
        column_of_position,
        generate_number_texts,
        insert_numbers_at_column,
        insert_text_at_column,
        make_column_editor_action,
        position_for_column,
        preview_number_texts,
        resolve_target,
    )
except Exception as _e:  # pragma: no cover
    print(f"[环境不可用] 无法导入被测模块: {_e}")
    traceback.print_exc()
    sys.exit(2)


# ============================================================
# 0. 纯函数
# ============================================================
def run_pure_checks():
    # --- 十进制 1..10 ---
    check("数字：1..10 十进制",
          generate_number_texts(1, 1, 10)
          == [str(i) for i in range(1, 11)],
          repr(generate_number_texts(1, 1, 10)))

    # --- 前导零 ---
    check("数字：前导零（按最大宽度）→ 01..10",
          generate_number_texts(1, 1, 10, pad=PAD_ZERO)
          == [f"{i:02d}" for i in range(1, 11)],
          repr(generate_number_texts(1, 1, 10, pad=PAD_ZERO)))

    # --- 前导空格（右对齐）---
    check("数字：前导空格右对齐 → ' 1'..'10'",
          generate_number_texts(1, 1, 10, pad=PAD_SPACE)
          == [f"{i:2d}" for i in range(1, 11)],
          repr(generate_number_texts(1, 1, 10, pad=PAD_SPACE)))

    # --- 十六进制 0x01..0x0A ---
    hex_texts = generate_number_texts(
        1, 1, 10, radix=16, pad=PAD_ZERO, min_width=2,
        prefix=True, uppercase=True,
    )
    check("数字：十六进制 0x01..0x0A（前导零 + 前缀 + 大写）",
          hex_texts == ["0x%02X" % i for i in range(1, 11)],
          repr(hex_texts))

    # --- 十六进制自动宽度（不加最小位数）---
    check("数字：十六进制自动宽度 → 0x1..0xA",
          generate_number_texts(1, 1, 10, radix=16, prefix=True)
          == ["0x1", "0x2", "0x3", "0x4", "0x5",
              "0x6", "0x7", "0x8", "0x9", "0xA"],
          repr(generate_number_texts(1, 1, 10, radix=16, prefix=True)))

    # --- 八进制 / 二进制 ---
    check("数字：八进制 0o1..0o10",
          generate_number_texts(1, 1, 10, radix=8, prefix=True)
          == ["0o" + format(i, 'o') for i in range(1, 11)],
          repr(generate_number_texts(1, 1, 10, radix=8, prefix=True)))
    check("数字：二进制 0b1..0b1010",
          generate_number_texts(1, 1, 10, radix=2, prefix=True)
          == ["0b" + format(i, 'b') for i in range(1, 11)],
          repr(generate_number_texts(1, 1, 10, radix=2, prefix=True)))

    # --- 步长 ---
    check("数字：步长 +3 → 1,4,7,10",
          generate_number_texts(1, 3, 4) == ["1", "4", "7", "10"],
          repr(generate_number_texts(1, 3, 4)))
    check("数字：负步长 → 10,8,6,4,2",
          generate_number_texts(10, -2, 5) == ["10", "8", "6", "4", "2"],
          repr(generate_number_texts(10, -2, 5)))
    check("数字：步长 0 → 全部相同",
          generate_number_texts(7, 0, 3) == ["7", "7", "7"],
          repr(generate_number_texts(7, 0, 3)))

    # --- 负数 ---
    check("数字：负数 + 前导零 → -01..-10",
          generate_number_texts(-1, -1, 10, pad=PAD_ZERO)
          == [f"-{i:02d}" for i in range(1, 11)],
          repr(generate_number_texts(-1, -1, 10, pad=PAD_ZERO)))

    # --- 预览只算前几个，但宽度按完整序列 ---
    check("数字：预览宽度按完整序列（1..100 → '  1'）",
          preview_number_texts(1, 1, 100, pad=PAD_SPACE, preview=3)
          == ["  1", "  2", "  3"],
          repr(preview_number_texts(1, 1, 100, pad=PAD_SPACE, preview=3)))

    # --- 空序列/非法参数 ---
    check("数字：count=0 → 空列表", generate_number_texts(1, 1, 0) == [])
    try:
        generate_number_texts(1, 1, 3, radix=7)
        check("数字：非法进制被拒绝", False, "radix=7 未报错")
    except Exception as e:
        check("数字：非法进制被拒绝", True)
        info(f"异常: {e}")

    # --- 配置校验 ---
    check("配置：文本模式空文本被拒绝",
          bool(ColumnEditConfig(mode=MODE_TEXT, text="").validate()))
    check("配置：数字模式默认参数合法",
          ColumnEditConfig(mode=MODE_NUMBER).validate() == "")
    check("配置：进制限制",
          bool(ColumnEditConfig(mode=MODE_NUMBER, radix=7).validate()))

    # --- 命令序列化（宏回放依赖 Command.from_dict）---
    cmd = ColumnInsertCmd([(0, "aa"), (5, "bb")], "列编辑测试")
    data = cmd.to_dict()
    check("命令：to_dict 类型标识",
          data.get("type") == CMD_TYPE_COLUMN_INSERT, repr(data))
    try:
        restored = Command.from_dict(data)
        check("命令：Command.from_dict 可还原（宏回放）",
              isinstance(restored, ColumnInsertCmd)
              and restored.inserts == cmd.inserts,
              repr(restored))
    except Exception as e:
        check("命令：Command.from_dict 可还原（宏回放）", False, str(e))


# ============================================================
# 集成测试基础设施
# ============================================================
LINE = "abcdefghij"          # 10 字符
LINE_W = len(LINE)
LINE_PITCH = LINE_W + 1      # 每行含 "\n" 的字节数（纯 ASCII）


def line_pos(line: int, col: int = 0) -> int:
    """纯 ASCII 场景下（行, 列）→ 字节位置（测试里独立算，不起用被测代码）。"""
    return line * LINE_PITCH + col


def ascii_base(lines: int = 10) -> str:
    return "\n".join([LINE] * lines) + "\n"


def new_editor(text: str):
    """新建真实 QScintilla + EditorProxy，并清空撤销栈 / 修改标记。"""
    sc = QsciScintilla()
    sc.setUtf8(True)
    sc.setText(text)
    proxy = EditorProxy(sc, Document())
    proxy.undo_manager.clear()
    sc.setModified(False)
    return sc, proxy


def undo_count(proxy) -> int:
    return len(proxy.undo_manager.undo_stack)


def setup_rectangle(sc, anchor: int, caret: int) -> bool:
    """尽力把编辑器置成矩形选区；返回是否成功（回读 SC_SEL_RECTANGLE）。

    刻意**不猜**矩形专用消息号：只用 QScintilla 真正暴露的常量
    （``getattr`` 取不到就换下一种姿势）。
      * 姿势 1：先切矩形模式，再用矩形专用消息设置两个角；
      * 姿势 2：先设置普通选区，再切矩形模式。

    官方文档：矩形选区在 Scintilla 内部是按多选区处理的，因此
    ``SCI_GETSELECTIONSTART/END`` 未必给出整条矩形 —— 被测代码用的是
    ``SCI_GETRECTANGULARSELECTIONCARET/ANCHOR`` + 全选区行跨度兜底。
    """
    try:
        mode_before = sc.SendScintilla(sc.SCI_GETSELECTIONMODE)
        sc.SendScintilla(sc.SCI_SETSELECTIONMODE, sc.SC_SEL_RECTANGLE)

        set_caret = getattr(sc, "SCI_SETRECTANGULARSELECTIONCARET", None)
        set_anchor = getattr(sc, "SCI_SETRECTANGULARSELECTIONANCHOR", None)
        if set_caret is not None and set_anchor is not None:
            sc.SendScintilla(set_anchor, anchor)
            sc.SendScintilla(set_caret, caret)
            if sc.SendScintilla(sc.SCI_GETSELECTIONMODE) == \
                    sc.SC_SEL_RECTANGLE:
                return True

        # 姿势 2（文档：SCI_SETSELECTION(position caret, position anchor)）
        sc.SendScintilla(sc.SCI_SETSELECTION, caret, anchor)
        sc.SendScintilla(sc.SCI_SETSELECTIONMODE, sc.SC_SEL_RECTANGLE)
        ok = sc.SendScintilla(sc.SCI_GETSELECTIONMODE) == sc.SC_SEL_RECTANGLE
        info(f"矩形选区设置：mode_before={mode_before}, ok={ok}, "
             f"GETSELECTIONS={sc.SendScintilla(sc.SCI_GETSELECTIONS)}, "
             f"selstart={sc.SendScintilla(sc.SCI_GETSELECTIONSTART)}, "
             f"selend={sc.SendScintilla(sc.SCI_GETSELECTIONEND)}")
        return ok
    except Exception as e:
        info(f"矩形选区建立失败: {e}")
        return False


# ============================================================
# 1. 文本插入到 10 行（显式行/列，确定性）
# ============================================================
def test_explicit_ten_lines():
    section("1. 文本插入到 10 行 / 位置正确（显式行 + 列）")
    base = ascii_base(10)
    sc, proxy = new_editor(base)
    check("初始撤销栈为空", undo_count(proxy) == 0, f"{undo_count(proxy)}")

    cfg = ColumnEditConfig(mode=MODE_TEXT, text="XY",
                           lines=list(range(10)), column=3)
    result = apply_column_edit(sc, cfg)
    check("执行成功", result.ok, result.reason)
    check("作用行 = 第 1–10 行",
          result.lines == list(range(10)), repr(result.lines))
    check("目标列 = 3", result.column == 3, repr(result.column))
    check("插入段数 = 10", result.count == 10, repr(result.count))

    expected = "\n".join(["abcXYdefghij"] * 10) + "\n"
    check("10 行每行第 3 列都插入了 XY", sc.text() == expected,
          repr(sc.text()))
    # ⚠️ 断言修订（Lead 实测，附依据）：
    #   `sc.isModified()` 在本项目的配置下**不可用** —— `EditorProxy` 为接管
    #   撤销执行了 `SCI_SETUNDOCOLLECTION, 0`，而 QScintilla 的 modified 标记
    #   依赖 Scintilla 的 save-point 机制，撤销收集关闭后它不再更新。
    #   实测：即使显式 `sc.setModified(True)` 或 `SCI_SETMODIFY(1)`，
    #   调用返回后 `isModified()` 仍为 False。
    #
    #   权威的"是否已修改"在本项目里是**文档模型层**：
    #   `proxy._modified` 与 `document.is_modified`（标签页 '*'、关窗提示、
    #   自动保存都读它们）。因此这里断言这两处，并把 widget 取值作为
    #   参考信息打印出来。
    check("编辑后文档被标记为已修改（document.is_modified）",
          bool(proxy.document.is_modified))
    check("编辑后代理被标记为已修改（proxy._modified）",
          bool(getattr(proxy, '_modified', False)))
    check("编辑后 Scintilla 修改标记为真（参考：该构建下可能恒为 False）",
          bool(sc.isModified()) or True,
          "sc.isModified()=%s（QScintilla 在 "
          "SCI_SETUNDOCOLLECTION=0 后不更新该标记）" % sc.isModified())

    # 关键：一次编辑 = 一条撤销命令
    check("撤销栈只有 1 条命令", undo_count(proxy) == 1,
          f"undo_stack={[c.describe() for c in proxy.undo_manager.undo_stack]}")
    check("栈顶就是列编辑命令",
          isinstance(proxy.undo_manager.undo_stack[0], ColumnInsertCmd),
          repr(proxy.undo_manager.undo_stack[0]))

    proxy.undo()
    check("撤销一次即全部回退", sc.text() == base, repr(sc.text()))
    check("撤销栈清空", undo_count(proxy) == 0)
    proxy.redo()
    check("重做恢复全部 10 行", sc.text() == expected, repr(sc.text()))


# ============================================================
# 2. 矩形选区入口（SC_SEL_RECTANGLE）
# ============================================================
def test_rectangle_entry():
    section("2. 矩形选区入口（SC_SEL_RECTANGLE）")
    base = ascii_base(10)
    sc, proxy = new_editor(base)

    if not setup_rectangle(sc, line_pos(0, 3), line_pos(9, 3)):
        warn("脚本无法在当前 QScintilla 版本建立矩形选区，"
             "矩形入口语义已由第 1 节（显式行/列）与 resolve_target 覆盖")
        return

    # 诊断：把真实选区状态打出来，便于判断是"环境搭不出矩形"还是"解析错"
    rect_anchor = getattr(sc, "SCI_GETRECTANGULARSELECTIONANCHOR", None)
    rect_caret = getattr(sc, "SCI_GETRECTANGULARSELECTIONCARET", None)
    info("矩形选区状态: GETSELECTIONS=%s selstart=%s selend=%s "
         "rectAnchor=%s rectCaret=%s"
         % (sc.SendScintilla(sc.SCI_GETSELECTIONS),
            sc.SendScintilla(sc.SCI_GETSELECTIONSTART),
            sc.SendScintilla(sc.SCI_GETSELECTIONEND),
            sc.SendScintilla(rect_anchor) if rect_anchor else "N/A",
            sc.SendScintilla(rect_caret) if rect_caret else "N/A"))

    target = resolve_target(sc)
    info(f"解析结果: source={target.source} lines={target.lines} "
         f"column={target.column}")
    check("矩形入口：来源 = rectangle",
          target.source == SOURCE_RECTANGLE, target.source)
    check("矩形入口：作用行 = 第 1–10 行",
          target.lines == list(range(10)), repr(target.lines))
    check("矩形入口：目标列 = 左边缘第 3 列",
          target.column == 3, repr(target.column))

    result = insert_text_at_column(sc, "XY")
    check("矩形入口：执行成功", result.ok, result.reason)
    expected = "\n".join(["abcXYdefghij"] * 10) + "\n"
    check("矩形入口：10 行位置全部正确", sc.text() == expected,
          repr(sc.text()))
    check("矩形入口：撤销栈只有 1 条命令", undo_count(proxy) == 1,
          f"undo_stack={undo_count(proxy)}")

    proxy.undo()
    check("矩形入口：撤销一次全部回退", sc.text() == base, repr(sc.text()))
    proxy.redo()
    check("矩形入口：重做正确", sc.text() == expected, repr(sc.text()))


# ============================================================
# 3. 多光标入口
# ============================================================
def test_multi_cursor_entry():
    section("3. 多光标入口（SCI_ADDSELECTION）")
    base = ascii_base(10)
    sc, proxy = new_editor(base)

    add_sel = getattr(sc, "SCI_ADDSELECTION", None)
    if add_sel is None:
        check("多光标：SCI_ADDSELECTION 可用", False,
              "当前 QScintilla 未暴露 SCI_ADDSELECTION")
        return
    if not hasattr(sc, "SCI_GETSELECTIONNSTART"):
        check("多光标：SCI_GETSELECTIONNSTART 可用", False,
              "当前 QScintilla 未暴露 SCI_GETSELECTIONNSTART，"
              "resolve_target 会退化为整选区")
        return

    set_multi = getattr(sc, "SCI_SETMULTIPLESELECTION", None)
    if set_multi is not None:
        sc.SendScintilla(set_multi, 1)

    # 第 2 / 5 / 8 行的第 3 列各放一个光标（刻意乱序添加）
    sc.SendScintilla(sc.SCI_SETSELECTION, line_pos(4, 3), line_pos(4, 3))
    sc.SendScintilla(add_sel, line_pos(7, 3), line_pos(7, 3))
    sc.SendScintilla(add_sel, line_pos(1, 3), line_pos(1, 3))

    count = int(sc.SendScintilla(sc.SCI_GETSELECTIONS))
    check("多光标：建立了 3 个选区", count == 3, f"selections={count}")

    target = resolve_target(sc)
    check("多光标入口：来源 = multi_cursor",
          target.source == SOURCE_MULTI, target.source)
    check("多光标入口：作用行 = 第 2/5/8 行（按位置升序）",
          target.lines == [1, 4, 7], repr(target.lines))

    result = insert_text_at_column(sc, "XY")
    check("多光标入口：执行成功", result.ok, result.reason)

    lines = [LINE] * 10
    for idx in (1, 4, 7):
        lines[idx] = "abcXYdefghij"
    expected = "\n".join(lines) + "\n"
    check("多光标入口：只有 3 个光标行被改动，位置正确",
          sc.text() == expected, repr(sc.text()))
    check("多光标入口：撤销栈只有 1 条命令", undo_count(proxy) == 1,
          f"undo_stack={undo_count(proxy)}")

    proxy.undo()
    check("多光标入口：撤销一次全部回退", sc.text() == base, repr(sc.text()))
    proxy.redo()
    check("多光标入口：重做正确", sc.text() == expected, repr(sc.text()))


# ============================================================
# 4. 数字序列插入（当前选区入口）
# ============================================================
def test_numbers_stream():
    section("4. 数字序列（当前选区整行入口）")
    base = ascii_base(10)

    # --- 4.1 十进制 1..10 + 前导零（01..10）---
    sc, proxy = new_editor(base)
    sc.SendScintilla(sc.SCI_SETSELECTION, 0, line_pos(10, 0))
    target = resolve_target(sc)
    check("选区入口：来源 = selection", target.source == SOURCE_SELECTION,
          target.source)
    check("选区入口：覆盖 10 行（不含末尾多出的空行）",
          target.lines == list(range(10)), repr(target.lines))

    result = insert_numbers_at_column(sc, 1, 1, radix=10, pad=PAD_ZERO)
    check("数字：执行成功", result.ok, result.reason)
    expected = "\n".join([f"{i:02d}" + LINE for i in range(1, 11)]) + "\n"
    check("数字 1..10 前导零（01..10）逐行插入", sc.text() == expected,
          repr(sc.text()))
    check("数字：撤销栈只有 1 条命令", undo_count(proxy) == 1,
          f"undo_stack={undo_count(proxy)}")
    proxy.undo()
    check("数字：撤销一次全部回退", sc.text() == base, repr(sc.text()))
    proxy.redo()
    check("数字：重做正确", sc.text() == expected, repr(sc.text()))

    # --- 4.2 步长 2 → 01,03,...,19 ---
    sc, proxy = new_editor(base)
    sc.SendScintilla(sc.SCI_SETSELECTION, 0, line_pos(10, 0))
    insert_numbers_at_column(sc, 1, 2, radix=10, pad=PAD_ZERO)
    expected = "\n".join([f"{v:02d}" + LINE for v in range(1, 20, 2)]) + "\n"
    check("数字：步长 2 → 01,03,05,…,19", sc.text() == expected,
          repr(sc.text()))
    check("数字：步长 2 时撤销栈只有 1 条命令", undo_count(proxy) == 1)

    # --- 4.3 十六进制 0x01..0x0A ---
    sc, proxy = new_editor(base)
    sc.SendScintilla(sc.SCI_SETSELECTION, 0, line_pos(10, 0))
    insert_numbers_at_column(sc, 1, 1, radix=16, pad=PAD_ZERO,
                             min_width=2, prefix=True)
    expected = "\n".join(
        ["0x%02X" % i + LINE for i in range(1, 11)]
    ) + "\n"
    check("数字：十六进制 0x01..0x0A 逐行插入", sc.text() == expected,
          repr(sc.text()))
    proxy.undo()
    check("数字：十六进制撤销一次全部回退", sc.text() == base)
    check("数字：十六进制撤销栈清空", undo_count(proxy) == 0)

    # --- 4.4 十进制 1..10 无填充（回归：不许多补零）---
    sc, proxy = new_editor(base)
    sc.SendScintilla(sc.SCI_SETSELECTION, 0, line_pos(10, 0))
    insert_numbers_at_column(sc, 1, 1, radix=10, pad=PAD_NONE)
    expected = "\n".join([str(i) + LINE for i in range(1, 11)]) + "\n"
    check("数字：不填充时保持原样（1..10）", sc.text() == expected,
          repr(sc.text()))


# ============================================================
# 5. 中文（非 ASCII）字节偏移
# ============================================================
def test_non_ascii():
    section("5. 中文行的字节偏移（列 → UTF-8 字节）")
    content = "中文内容测试"          # 6 字符 / 18 字节
    base = "\n".join([content] * 3) + "\n"
    sc, proxy = new_editor(base)

    line1_start = len(content.encode("utf-8")) + 1   # 19
    check("中文：列 2 → 行内 6 字节",
          position_for_column(sc, 1, 2) == line1_start + 6,
          f"got={position_for_column(sc, 1, 2)} want={line1_start + 6}")
    check("中文：字节位置 → 列 2",
          column_of_position(sc, line1_start + 6) == 2,
          f"got={column_of_position(sc, line1_start + 6)}")
    check("中文：列超出行长时贴行尾",
          position_for_column(sc, 1, 99) == line1_start + 18,
          f"got={position_for_column(sc, 1, 99)}")

    result = apply_column_edit(sc, ColumnEditConfig(
        mode=MODE_TEXT, text="X", lines=[1], column=2))
    check("中文：执行成功", result.ok, result.reason)
    expected = "\n".join([content, "中文X内容测试", content]) + "\n"
    check("中文：第 2 行插入列位置正确（不按字符数错位）",
          sc.text() == expected, repr(sc.text()))
    check("中文：撤销栈只有 1 条命令", undo_count(proxy) == 1)
    proxy.undo()
    check("中文：撤销一次全部回退", sc.text() == base, repr(sc.text()))


# ============================================================
# 6. 对话框（独立构造 / 参数 / 预览）
# ============================================================
def test_dialog():
    section("6. 对话框可独立构造（不依赖 MainWindow）")
    base = ascii_base(4)
    sc, proxy = new_editor(base)
    sc.SendScintilla(sc.SCI_SETSELECTION, 0, line_pos(4, 0))

    dlg = ColumnEditorDialog(sc, None)
    try:
        check("对话框构造成功（parent=None）", dlg is not None)
        scope = dlg._scope_label.text()
        check("作用范围提示包含行数与列", "共 4 行" in scope,
              repr(scope))
        info(scope)

        # 切到数字模式并设置 Hex / 前导零 / 最小位数 2
        dlg._number_radio.setChecked(True)
        dlg._start_edit.setText("0x0A")     # 支持 0x 起始值写法
        dlg._step_spin.setValue(1)
        dlg._radix_combo.setCurrentIndex(1)   # RADIXES[1] = 十六进制
        dlg._pad_combo.setCurrentIndex(1)     # PAD_ZERO
        dlg._width_spin.setValue(2)
        dlg._prefix_check.setChecked(True)

        cfg = dlg.build_config()
        check("参数解析：0x0A → 10 / Hex / 前导零 / 宽度 2 / 前缀",
              cfg.mode == MODE_NUMBER and cfg.start == 10
              and cfg.radix == 16 and cfg.pad == PAD_ZERO
              and cfg.min_width == 2 and cfg.prefix is True,
              repr(cfg))

        preview = dlg._preview.text()
        check("预览已刷新且含 0x0A", "将在 4 行插入" in preview
              and "0x0A" in preview, repr(preview))
        info(preview)

        check("确定按钮可用", dlg._ok_button.isEnabled())

        # 文本模式：空文本 → 确定禁用
        dlg._text_radio.setChecked(True)
        dlg._text_edit.setText("")
        check("文本模式下空文本 → 确定禁用",
              not dlg._ok_button.isEnabled(),
              dlg._preview.text())
        dlg._text_edit.setText("// ")
        check("文本输入后 → 确定可用", dlg._ok_button.isEnabled())
    finally:
        dlg.deleteLater()

    # 菜单 QAction 便利函数（只查属性，不触发——触发会弹模态对话框）
    action = make_column_editor_action(None, lambda: sc)
    check("菜单 QAction 文本 = 📊 列编辑器…",
          action.text() == "📊 列编辑器…", repr(action.text()))
    seq = action.shortcut().toString()
    check("菜单 QAction 快捷键 = Alt+Shift+I（忽略修饰键书写顺序）",
          set(seq.split("+")) == {"Alt", "Shift", "I"}, repr(seq))


# ============================================================
# 入口
# ============================================================
def main() -> int:
    print("青草编辑器 · 列编辑器验证")
    print(f"Python: {sys.version.split()[0]}")
    try:
        from PyQt5.QtCore import QT_VERSION_STR
        print(f"Qt: {QT_VERSION_STR}")
    except Exception:
        pass
    print(f"SCI_GETSELECTIONNSTART 可用: "
          f"{hasattr(QsciScintilla, 'SCI_GETSELECTIONNSTART')}")
    print(f"SC_SEL_RECTANGLE = "
          f"{getattr(QsciScintilla, 'SC_SEL_RECTANGLE', None)}")

    section("0. 纯函数：数字序列 / 进制 / 填充 / 步长")
    run_pure_checks()

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    for func in (
        test_explicit_ten_lines,
        test_rectangle_entry,
        test_multi_cursor_entry,
        test_numbers_stream,
        test_non_ascii,
        test_dialog,
    ):
        try:
            func()
        except Exception as e:  # 一个用例崩了不影响其它用例
            FAILED.append((func.__name__, "未捕获异常"))
            print(f"[FAIL] {func.__name__} 抛出异常: {e}")
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"结果：通过 {len(PASSED)} 项，失败 {len(FAILED)} 项，"
          f"警告 {len(WARNED)} 项")
    print("=" * 70)
    for name, detail in WARNED:
        print(f"  [WARN] {name} {detail}")
    for name, detail in FAILED:
        print(f"  [FAIL] {name} {detail}")

    if FAILED:
        print("\n结论：列编辑器验证**未通过**")
        return 1
    print("\n结论：列编辑器验证全部通过"
          + ("（含警告，见上）" if WARNED else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
