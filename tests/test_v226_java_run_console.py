# -*- coding: utf-8 -*-
"""Java 单文件在内嵌控制台运行"""
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_run_java_in_console(qapp, tmp_path):
    from core.java_runner import find_tools, prepare

    if not find_tools()["ok"]:
        import pytest
        pytest.skip("JDK 不可用")
    src = tmp_path / "Hello.java"
    src.write_text(
        "public class Hello {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(\"HELLO JAVA\");\n"
        "    }\n"
        "}\n", encoding="utf-8")
    spec = prepare(str(src))
    assert spec["ok"], spec
    from ui.run_console_panel import RunConsolePanel

    panel = RunConsolePanel()
    try:
        panel.run_batch(spec["batch"], cwd=spec["cwd"], label="javac+java")
        for _ in range(200):
            qapp.processEvents(); time.sleep(0.05)
            if "HELLO JAVA" in panel.output.toPlainText():
                break
        assert "HELLO JAVA" in panel.output.toPlainText(), panel.output.toPlainText()
    finally:
        panel.stop(); panel.close()
