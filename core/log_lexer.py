#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""日志语法高亮器"""
import re

from PyQt5.Qsci import QsciLexerCustom
from PyQt5.QtGui import QColor, QFont


class LogLexer(QsciLexerCustom):
    """日志文件高亮器"""

    STYLE_DEFAULT = 0
    STYLE_ERROR = 1
    STYLE_WARN = 2
    STYLE_INFO = 3
    STYLE_IP = 4
    STYLE_TIMESTAMP = 5
    STYLE_URL = 6
    STYLE_NUMBER = 7

    def __init__(self, parent=None):
        super().__init__(parent)

        # 设置样式
        self.setDefaultColor(QColor("#d4d4d4"))
        self.setDefaultPaper(QColor("#1e1e1e"))
        self.setDefaultFont(QFont("Consolas", 11))

        # 错误（红）
        self.setColor(QColor("#f14c4c"), self.STYLE_ERROR)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_ERROR)

        # 警告（黄）
        self.setColor(QColor("#f0ad4e"), self.STYLE_WARN)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_WARN)

        # 信息（灰绿）
        self.setColor(QColor("#6a9955"), self.STYLE_INFO)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_INFO)

        # IP（青）
        self.setColor(QColor("#00bcd4"), self.STYLE_IP)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_IP)

        # 时间戳（绿）
        self.setColor(QColor("#4caf50"), self.STYLE_TIMESTAMP)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_TIMESTAMP)

        # URL（蓝）
        self.setColor(QColor("#4dabf7"), self.STYLE_URL)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_URL)

        # 数字（浅绿）
        self.setColor(QColor("#b5cea8"), self.STYLE_NUMBER)
        self.setPaper(QColor("#1e1e1e"), self.STYLE_NUMBER)

        # 规则
        self._rules = [
            (re.compile(r'\b(ERROR|CRITICAL|FATAL|Exception)\b', re.IGNORECASE),
             self.STYLE_ERROR),
            (re.compile(r'\b(WARN|WARNING)\b', re.IGNORECASE),
             self.STYLE_WARN),
            (re.compile(r'\b(INFO|DEBUG|TRACE)\b', re.IGNORECASE),
             self.STYLE_INFO),
            (re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'),
             self.STYLE_IP),
            (re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}'),
             self.STYLE_TIMESTAMP),
            (re.compile(r'https?://\S+'),
             self.STYLE_URL),
            (re.compile(r'\b\d+\b'),
             self.STYLE_NUMBER),
        ]

    def language(self):
        return "Log"

    def description(self, style):
        return ""

    def styleText(self, start, end):
        """样式化文本"""
        self.startStyling(start)

        editor = self.parent()
        if editor is None:
            return

        text = editor.text()[start:end]

        # 先全部标记为默认样式
        self.setStyling(len(text), self.STYLE_DEFAULT)

        # 逐个规则应用
        for pattern, style in self._rules:
            for m in pattern.finditer(text):
                # 设置样式
                self.startStyling(start + m.start())
                self.setStyling(m.end() - m.start(), style)