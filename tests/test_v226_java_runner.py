# -*- coding: utf-8 -*-
"""Java 单文件运行准备"""


def test_parse_java_and_batch(tmp_path):
    from core.java_runner import build_batch, parse_java

    src = tmp_path / "Hello.java"
    src.write_text(
        "public class Hello { public static void main(String[] a){} }\n", encoding="utf-8"
    )
    assert parse_java(src.read_text(encoding="utf-8")) == ("", "Hello")
    bat = build_batch("javac", "java", str(src), str(tmp_path), "Hello")
    assert "javac" in bat and "Hello" in bat
