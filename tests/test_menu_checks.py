# -*- coding: utf-8 -*-
"""菜单选中对号 + 主题切换 UnboundLocalError 回归测试"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_theme_switch_imports_qapplication_first():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    i = src.index("def _apply_theme_by_name")
    fn = src[i:i + 1200]
    imp = fn.index("from PyQt5.QtWidgets import QApplication")
    use = fn.index("QApplication.instance")
    assert imp < use, "QApplication 必须在首次使用前导入（UnboundLocalError）"


def test_encoding_menu_checks_current(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        f = tmp_path / "a.txt"
        f.write_text("hello" + chr(10), encoding="utf-8")
        win.tabs.open_file(str(f))
        win._sync_encoding_menu_checks()
        proxy = win.tabs.current_proxy()
        enc = (proxy.document.encoding or "utf-8").lower()
        checked = [str(code).lower()
                   for code, act in win._npp_encoding_actions
                   if act.isChecked()]
        assert enc in checked, (enc, checked)
        eol = getattr(proxy.document.meta, "eol", chr(10))
        eol_checked = [code for code, act in win._npp_eol_actions
                       if act.isChecked()]
        assert eol in eol_checked, (eol, eol_checked)
    finally:
        _close(win)


def test_language_menu_auto_default(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        win._sync_language_menu_checks()
        assert win._npp_language_auto_action.isChecked() is True
    finally:
        _close(win)

def test_encoding_checkmark_follows_document_state(qapp, tmp_path):
    """切换编码后，再次同步时勾选应移动到新编码（NPP 行为）"""
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        f = tmp_path / "b.txt"
        f.write_text("hello" + chr(10), encoding="utf-8")
        win.tabs.open_file(str(f))
        proxy = win.tabs.current_proxy()

        win._sync_encoding_menu_checks()
        first = [str(c).lower() for c, a in win._npp_encoding_actions
                 if a.isChecked()]
        assert first, "首次应有勾选"

        # 模拟编码切换后的文档状态，再同步
        proxy.document.encoding = "gbk"
        win._sync_encoding_menu_checks()
        checked = [str(c).lower() for c, a in win._npp_encoding_actions
                   if a.isChecked()]
        assert "gbk" in checked, checked
        assert len(checked) == 1, "同一时刻只应有一个勾选: %r" % (checked,)
        assert first != checked, "勾选应移动到新编码"

        # EOL 同理
        meta = proxy.document.meta
        if meta is not None:
            meta.eol = "\r\n"
            win._sync_encoding_menu_checks()
            eol_checked = [c for c, a in win._npp_eol_actions if a.isChecked()]
            assert eol_checked == ["\r\n"], eol_checked
    finally:
        _close(win)
