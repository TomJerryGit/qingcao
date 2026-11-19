# -*- coding: utf-8 -*-
"""AI 自动调试闭环：运行→捕获错误→AI 修复→校验→应用→复测。

Sprint 3：取消、轮次历史、回滚点（备份文件）。
"""

import ast
import io
import os

from core.ai_runner import run_python_file


MAX_ROUNDS = 3


def extract_code(text):
    raw = str(text or "").strip()
    if "```" not in raw:
        return raw
    parts = raw.split("```")
    for part in parts[1:]:
        lines = part.splitlines()
        if lines and lines[0].strip().lower() in ("python", "py", "python3"):
            lines = lines[1:]
        code = "\n".join(lines).strip()
        if code:
            return code
    return raw


def validate_python(code):
    try:
        ast.parse(code)
    except SyntaxError as e:
        return (False, "语法错误：第 %s 行 %s" % (e.lineno, e.msg))
    return (True, "")


def _restore(path, original):
    try:
        io.open(path, "w", encoding="utf-8", newline="\n").write(original)
    except OSError:
        pass


def auto_debug(
    path,
    ai_call,
    max_rounds=MAX_ROUNDS,
    timeout=15,
    on_progress=None,
    cancel_event=None,
    backup_dir=None,
):
    path = os.path.abspath(str(path))
    if not os.path.isfile(path) or not path.lower().endswith(".py"):
        return {"ok": False, "error": "仅支持 .py 文件"}
    original = io.open(path, encoding="utf-8", errors="replace").read()
    rounds = max(1, int(max_rounds))
    backups = []
    if backup_dir:
        os.makedirs(backup_dir, exist_ok=True)
        b = os.path.join(backup_dir, "original.py.bak")
        io.open(b, "w", encoding="utf-8", newline="\n").write(original)
        backups.append(b)
    history = []
    code = original

    def cancelled():
        _restore(path, original)
        return {
            "ok": False,
            "cancelled": True,
            "error": "已取消（已回滚）",
            "rounds": len(history),
            "history": history,
            "backups": backups,
        }

    for round_no in range(1, rounds + 1):
        if cancel_event is not None and cancel_event.is_set():
            return cancelled()
        result = run_python_file(path, timeout=timeout)
        entry = {
            "round": round_no,
            "ok": bool(result.get("ok")),
            "exit_code": result.get("exit_code"),
            "error": result.get("error") or "",
            "timed_out": bool(result.get("timed_out")),
        }
        history.append(entry)
        if on_progress:
            on_progress(round_no, result)
        if result.get("ok"):
            return {
                "ok": True,
                "rounds": round_no - 1,
                "history": history,
                "result": result,
                "backups": backups,
            }
        if cancel_event is not None and cancel_event.is_set():
            return cancelled()
        prompt = (
            "你是 Python 调试助手。程序运行失败，请只输出修复后的完整代码，"
            "不要解释。\n\n错误输出：\n%s\n\n当前代码：\n%s"
            % (result.get("stderr") or result.get("error") or "", code)
        )
        try:
            answer = ai_call(prompt)
        except Exception as e:
            _restore(path, original)
            return {
                "ok": False,
                "error": "AI 调用失败: %s" % e,
                "rounds": round_no - 1,
                "history": history,
                "backups": backups,
            }
        if cancel_event is not None and cancel_event.is_set():
            return cancelled()
        fixed = extract_code(answer)
        valid, verr = validate_python(fixed)
        if not valid:
            entry["fix_error"] = verr
            continue
        try:
            io.open(path, "w", encoding="utf-8", newline="\n").write(fixed)
        except OSError as e:
            return {
                "ok": False,
                "error": str(e),
                "rounds": round_no,
                "history": history,
                "backups": backups,
            }
        code = fixed
        if backup_dir:
            b = os.path.join(backup_dir, "round_%d.py.bak" % round_no)
            io.open(b, "w", encoding="utf-8", newline="\n").write(fixed)
            backups.append(b)

    final = run_python_file(path, timeout=timeout)
    if not final.get("ok"):
        _restore(path, original)
        return {
            "ok": False,
            "error": "达到最大轮数仍未修复（已回滚）",
            "rounds": rounds,
            "history": history,
            "result": final,
            "backups": backups,
        }
    return {
        "ok": True,
        "rounds": rounds,
        "modified": code != original,
        "history": history,
        "result": final,
        "backups": backups,
    }
