# -*- coding: utf-8 -*-
def test_wizard_has_plugins_and_sample(qapp):
    from ui.first_run_wizard import FirstRunWizard

    w = FirstRunWizard()
    try:
        assert w.plugins_page.get_plugins()
        assert w.sample_page.get_sample() == "python"
    finally:
        w.close()
