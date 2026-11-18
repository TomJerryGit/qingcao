# -*- coding: utf-8 -*-
"""插件 i18n 基础：中文回退 + 英文字典（后续扩展到 ja/ko）。"""

import os


_LOCALE = os.environ.get("QINGCAO_LOCALE", "zh_CN")
_EN = {
    "plugin.submit_community": "Submit to Community",
    "plugin.save_rating": "Save Rating",
    "plugin.install_local": "Install Local",
    "plugin.update_all": "Update All",
    "plugin.search_placeholder": "Search plugins...(Ctrl+F)",
    "plugin.settings_title": "Plugin Settings - {name}",
    "plugin.compare": "Compare",
    "plugin.refresh": "Refresh",
    "plugin.filter": "Filter",
    "plugin.market": "Plugin Market",
    "plugin.install": "Install",
    "plugin.uninstall": "Uninstall",
    "plugin.enable": "Enable",
    "plugin.disable": "Disable",
    "plugin.settings": "Settings",
    "plugin.usage": "Usage",
    "plugin.rating": "Rating",
    "common.close": "Close",
    "common.cancel": "Cancel",
    "common.save": "Save",
    "common.search": "Search",
}
_JA = {
    "plugin.market": "プラグイン市場",
    "plugin.install": "インストール",
    "plugin.uninstall": "アンインストール",
    "plugin.enable": "有効化",
    "plugin.disable": "無効化",
    "plugin.settings": "設定",
    "plugin.usage": "使用状況",
    "plugin.rating": "評価",
    "common.close": "閉じる",
    "common.cancel": "キャンセル",
    "common.save": "保存",
    "common.search": "検索",
}
_KO = {
    "plugin.market": "플러그인 마켓",
    "plugin.install": "설치",
    "plugin.uninstall": "제거",
    "plugin.enable": "활성화",
    "plugin.disable": "비활성화",
    "plugin.settings": "설정",
    "plugin.usage": "사용 통계",
    "plugin.rating": "평점",
    "common.close": "닫기",
    "common.cancel": "취소",
    "common.save": "저장",
    "common.search": "검색",
}
_ZH = {}


def set_locale(locale):
    global _LOCALE
    _LOCALE = str(locale or "zh_CN")


def get_locale():
    return _LOCALE


def tr(key, default=None, **kwargs):
    loc = _LOCALE.lower()
    if loc.startswith("en"):
        table = _EN
    elif loc.startswith("ja"):
        table = _JA
    elif loc.startswith("ko"):
        table = _KO
    else:
        table = _ZH
    text = table.get(key)
    if text is None:
        text = default if default is not None else key
    try:
        return text.format(**kwargs) if kwargs else text
    except Exception:
        return text
