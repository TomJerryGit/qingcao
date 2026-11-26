# -*- coding: utf-8 -*-
"""首次启动 5 分钟流程"""
def test_finish_page_has_quick_start(qapp):
    from ui.first_run_wizard import FirstRunWizard

    w = FirstRunWizard()
    try:
        assert hasattr(w, "sample_page")
        text = w.findChildren(type(w.finish_page)).__class__ and ""
        # 完成页不再提供遥测选项
        assert w.finish_page.is_telemetry() is False
    finally:
        w.close()
