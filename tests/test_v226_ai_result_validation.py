# -*- coding: utf-8 -*-
def test_validate_result():
    from plugins.ai_assistant.validation import validate_result

    assert validate_result("x = 1", "a.py")[0]
    assert not validate_result("def (", "a.py")[0]
    assert validate_result('{"a":1}', "a.json")[0]
    assert not validate_result("{bad", "a.json")[0]
    assert not validate_result("", "a.py")[0]
