# -*- coding: utf-8 -*-
"""国际化管理器"""
import gettext
import os
import sys
from typing import Dict, List, Optional

from PyQt5.QtCore import QCoreApplication, QLocale, QObject, QTranslator, pyqtSignal


class I18nManager(QObject):
    """国际化管理器"""

    language_changed = pyqtSignal(str)

    AVAILABLE_LANGUAGES = [
        ("zh_CN", "简体中文"),
        ("en_US", "English"),
        ("ja_JP", "日本語"),
        ("ko_KR", "한국어"),
    ]

    def __init__(self, locale_dir="locale", parent=None):
        super().__init__(parent)
        self.locale_dir = locale_dir
        self.current_language = "zh_CN"
        self._translator = None
        self._app_translator = None

    def list_languages(self):
        """列出可用语言"""
        return list(self.AVAILABLE_LANGUAGES)

    def current_lang_name(self):
        """当前语言名"""
        for code, name in self.AVAILABLE_LANGUAGES:
            if code == self.current_language:
                return name
        return self.current_language

    def load(self, lang_code):
        """加载语言"""
        app = QCoreApplication.instance()
        if app is None:
            return False

        # 卸载旧 translator
        if self._app_translator:
            app.removeTranslator(self._app_translator)
            self._app_translator = None

        # 加载新的 .qm
        qm_file = os.path.join(self.locale_dir, lang_code, "qingcao.qm")
        if os.path.exists(qm_file):
            translator = QTranslator()
            if translator.load(qm_file):
                app.installTranslator(translator)
                self._app_translator = translator

        # 加载 gettext（用于 Python 字符串）
        try:
            tr = gettext.translation(
                "qingcao", self.locale_dir, languages=[lang_code]
            )
            tr.install()
            self._translator = tr
        except FileNotFoundError:
            # 回退到英文
            try:
                gettext.install("qingcao")
            except Exception:
                pass

        self.current_language = lang_code
        self.language_changed.emit(lang_code)
        return True

    def tr(self, text, context=""):
        """翻译单个字符串"""
        if self._translator:
            return self._translator.gettext(text)
        return text


# 全局单例
_instance = None


def get_i18n():
    global _instance
    if _instance is None:
        _instance = I18nManager()
    return _instance