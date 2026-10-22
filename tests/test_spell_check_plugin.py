# -*- coding: utf-8 -*-
"""拼写检查插件（DSpellCheck 对应）测试"""
import ast
import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugins", "spell_check")


def _manifest():
    return json.load(open(os.path.join(PLUGIN_DIR, "plugin.json"),
                          encoding="utf-8"))


def _load_plugin():
    path = os.path.join(PLUGIN_DIR, "__init__.py")
    spec = importlib.util.spec_from_file_location("spell_check_plugin",
                                                  path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    plugin = mod.Plugin.__new__(mod.Plugin)
    plugin._checker = None
    plugin._status_item = None
    plugin._ignore = set()
    plugin._ignore_path = ""
    return mod, plugin


def test_manifest_is_valid():
    data = _manifest()
    assert data["name"] == "spell_check"
    for key in ("display_name", "version", "description", "author",
                "license", "type", "category", "tags", "permissions",
                "api_version", "enabled", "auto_load"):
        assert key in data, "manifest 缺字段 %s" % key
    assert "editor_read" in data["permissions"]
    assert data["auto_load"] is True


def test_plugin_registers_menu_settings_and_diagnostics():
    src = open(os.path.join(PLUGIN_DIR, "__init__.py"),
               encoding="utf-8").read()
    tree = ast.parse(src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert {"on_activate", "on_deactivate", "check_current",
            "_check_text"} <= methods
    assert "register_settings_schema" in src
    assert "add_menu" in src
    assert "publish_diagnostics" in src


def test_check_text_finds_typos_and_skips_code():
    _mod, plugin = _load_plugin()
    text = (
        "This sentence is fine.\n"
        "Thiss word is misspelled.\n"
        "API myVar snake_case http://example.com 123\n"
    )
    issues = plugin._check_text(text, min_length=4, limit=50)
    words = {i["message"].split("：")[-1] for i in issues}
    assert "Thiss" in words, words
    # 代码标识符/缩写不报
    assert "API" not in words
    assert "myVar" not in words
    assert "snake_case" not in words
    # 行号正确
    assert all(0 <= i["line"] <= 2 for i in issues)


def test_check_text_respects_limit_and_min_length():
    _mod, plugin = _load_plugin()
    text = " ".join(["zzzz"] * 100)
    issues = plugin._check_text(text, min_length=4, limit=10)
    assert len(issues) == 10
    assert plugin._check_text("", min_length=4, limit=10) == []
    assert plugin._check_text("a b c", min_length=4, limit=10) == []


def test_ignore_words_file_loading(tmp_path):
    import importlib.util as _iu
    path = os.path.join(PLUGIN_DIR, "__init__.py")
    spec = _iu.spec_from_file_location("spell_ignore_mod", path)
    mod = _iu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    f = tmp_path / "ignore.txt"
    f.write_text("# comment\nQingCao\n  myword  \n\n#x\n", encoding="utf-8")
    words = mod.load_ignore_words(str(f))
    assert words == {"qingcao", "myword"}

    _m, plugin = _load_plugin()
    plugin._ignore = {"qingcao"}
    assert plugin._known("QingCao") is True
    assert plugin._known("myword") is False
    issues = plugin._check_text("qingcao myword", min_length=4, limit=10)
    flagged = {i["message"].split("：")[-1].lower() for i in issues}
    assert "qingcao" not in flagged
    assert "myword" in flagged


def test_default_ignore_file_and_menus():
    default = os.path.join(ROOT, "data", "spell_ignore.txt")
    assert os.path.exists(default), "缺少默认忽略词文件"
    _m, _plugin = _load_plugin()
    src = open(os.path.join(PLUGIN_DIR, "__init__.py"), encoding="utf-8").read()
    assert "reload_ignore" in src
    assert "open_ignore_file" in src
    assert "spell_ignore.txt" in src


class _FakeApi:
    def __init__(self, text="Thiss is a testt."):
        self._text = text
        self.published = None
        self.status = []
        self.status_item = None
        self.menu_count = 0

    def log(self, *a, **k):
        pass

    def get_current_text(self):
        return self._text

    def publish_diagnostics(self, issues):
        self.published = list(issues)
        return len(issues)

    def clear_diagnostics(self):
        self.published = []

    def add_status_item(self, text):
        self.status_item = text
        return "item-1"

    def set_status_item_text(self, item, text):
        self.status = (item, text)

    def show_status(self, *a, **k):
        pass

    def add_menu(self, *a, **k):
        self.menu_count += 1

    def register_settings_schema(self, *a, **k):
        pass


def test_check_current_publishes_and_updates_status():
    _mod, plugin = _load_plugin()
    api = _FakeApi()
    plugin.api = api
    plugin.check_current()
    assert api.published, "应发布诊断"
    words = [i["message"] for i in api.published]
    assert any("Thiss" in w or "testt" in w for w in words), words
    assert api.status == ("item-1", "拼写: %d" % len(api.published))

    plugin.clear()
    assert api.status == ("item-1", "拼写: 0")
