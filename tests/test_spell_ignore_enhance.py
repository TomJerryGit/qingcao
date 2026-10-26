# -*- coding: utf-8 -*-
"""拼写检查增强：忽略本文件可疑词"""


class _FakeApi:
    def __init__(self, text=""):
        self._text = text
        self.published = None
        self.status_item = None
        self.status = []
        self.menus = []
        self.ctx_menus = []

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
        self.status = ("msg", a[0] if a else "")

    def add_menu(self, path, cb):
        self.menus.append(path)

    def add_editor_context_menu(self, label, cb):
        self.ctx_menus.append(label)

    def register_settings_schema(self, *a, **k):
        pass


def test_ignore_flagged_words_appends_and_clears(tmp_path):
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "plugins", "spell_check",
        "__init__.py")
    spec = importlib.util.spec_from_file_location("sp_ignore_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    ignore = tmp_path / "ignore.txt"
    ignore.write_text("qingcao\n", encoding="utf-8")
    api = _FakeApi("Thiss word testt appears")
    plugin = mod.Plugin.__new__(mod.Plugin)
    plugin._checker = None
    plugin._status_item = None
    plugin._ignore = mod.load_ignore_words(str(ignore))
    plugin._ignore_path = str(ignore)
    plugin.api = api

    added = plugin.ignore_flagged_words()
    assert added >= 1
    content = ignore.read_text(encoding="utf-8").lower()
    assert "thiss" in content
    assert "qingcao" in content
    assert api.published == []
    assert plugin._ignore >= {"thiss"}


def test_ignore_when_no_issues(tmp_path):
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "plugins", "spell_check",
        "__init__.py")
    spec = importlib.util.spec_from_file_location("sp_ignore_mod2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    api = _FakeApi("a b c")
    plugin = mod.Plugin.__new__(mod.Plugin)
    plugin._checker = None
    plugin._status_item = None
    plugin._ignore = set()
    plugin._ignore_path = str(tmp_path / "ignore2.txt")
    plugin.api = api
    assert plugin.ignore_flagged_words() == 0
    assert api.published == [] or api.published is None