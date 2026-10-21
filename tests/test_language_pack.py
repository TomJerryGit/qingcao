# -*- coding: utf-8 -*-
"""声明式语言包（Notepad++ UDL 等价物）测试"""
import json

import pytest


def _pack_data(**over):
    data = {
        "name": "MyLang",
        "extensions": [".mylang", ".ml"],
        "keywords": ["if", "else", "return"],
        "line_comment": "//",
        "block_comment": ["/*", "*/"],
        "strings": ['"'],
        "folding": {"start": "{", "end": "}"},
    }
    data.update(over)
    return data


def _write(tmp_path, name="mylang.qingcao-lang.json", **over):
    p = tmp_path / name
    p.write_text(json.dumps(_pack_data(**over), ensure_ascii=False),
                 encoding="utf-8")
    return p


def test_load_and_validate(tmp_path):
    from core.language_pack import load_pack

    pack = load_pack(str(_write(tmp_path)))
    assert pack.name == "MyLang"
    assert ".mylang" in pack.extensions
    assert "if" in pack.keywords
    assert pack.line_comment == "//"

    bad = tmp_path / "bad.qingcao-lang.json"
    bad.write_text('{"keywords": ["x"]}', encoding="utf-8")
    with pytest.raises(ValueError):
        load_pack(str(bad))


def test_discover_register_and_lookup(tmp_path):
    from core import language_pack as lp

    _write(tmp_path)
    mapping = lp.discover_packs([str(tmp_path)])
    assert ".mylang" in mapping and ".ml" in mapping

    lp.reset_cache()
    pack = lp.load_pack(str(_write(tmp_path, name="second.qingcao-lang.json")))
    lp.register_pack(pack)
    assert lp.get_pack_for_extension("mylang") is pack
    assert lp.get_pack_for_extension(".Mylang") is pack
    lp.reset_cache()


def test_lexer_factory_uses_language_pack(qapp, tmp_path):
    from core import language_pack as lp
    from ui.editor_view import create_lexer_for_extension
    from ui.generic_lexer import GenericLexer

    lp.reset_cache()
    pack = lp.load_pack(str(_write(tmp_path)))
    lp.register_pack(pack)
    try:
        lexer = create_lexer_for_extension(".mylang")
        assert isinstance(lexer, GenericLexer)
    finally:
        lp.reset_cache()


def test_generic_lexer_styles(qapp):
    from PyQt5.Qsci import QsciScintilla

    from core.language_pack import LanguagePack
    from ui.generic_lexer import (
        STYLE_COMMENT,
        STYLE_KEYWORD,
        STYLE_NUMBER,
        STYLE_STRING,
        create_generic_lexer,
    )

    pack = LanguagePack(_pack_data())
    sc = QsciScintilla()
    sc.setText('if x = 12 // note\n"abc"\n')
    lexer = create_generic_lexer(pack, sc)
    sc.setLexer(lexer)
    sc.SendScintilla(QsciScintilla.SCI_COLOURISE, 0, -1)

    def style_at(pos):
        return sc.SendScintilla(QsciScintilla.SCI_GETSTYLEAT, pos)

    assert style_at(0) == STYLE_KEYWORD      # 'i' of if
    assert style_at(7) == STYLE_NUMBER       # '1' of 12
    assert style_at(10) == STYLE_COMMENT     # '/'
    assert style_at(19) == STYLE_STRING      # '"abc"'
    sc.deleteLater()
