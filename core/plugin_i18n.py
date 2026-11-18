# -*- coding: utf-8 -*-
"""插件 i18n 基础：中文回退 + 英文字典（后续扩展到 ja/ko）。"""

import os


_LOCALE = os.environ.get("QINGCAO_LOCALE", "zh_CN")
_EN = {
    "wordcount.chars": "Chars: {n}",
    "wordcount.words": "Words: {n}",
    "wordcount.large": "Wordcount: large file",
    "wordcount.unset": "Not set",
    "ai.inline_inserted": "AI completion inserted (Ctrl+Z to undo)",
    "ai.inline_need_cursor": "Move cursor after existing code (at least 3 columns)",
    "ai.inline_requesting": "Requesting completion…",
    "ai.inline_no_editor": "No editor available",
    "ai.inline_disabled": "Inline completion disabled: Tools → AI Assistant → toggle",
    "ai.inline_unavailable": "Inline completion unavailable",
    "ai.not_configured": "AI not configured: set API in Settings",
    "ai.inserted": "✓ Inserted at cursor",
    "ai.replaced": "✓ Replaced selection",
    "ai.done_time": "✓ Done · {sec:.1f}s",
    "ai.done": "✓ Done",
    "ai.new_session": "New session started · context cleared",
    "spell.cleared": "Spelling results cleared",
    "spell.clean": "No spelling issues",
    "spell.found": "{n} suspicious spellings found",
    "spell.none": "No suspicious spelling found",
    "spell.empty": "Nothing to check",
    "jsonl.done": "JSONL formatted ({n} lines)",
    "jsonl.error": "JSONL Error",
    "json.sorted": "Sorted",
    "json.compressed": "Compressed",
    "json.reported": "JSON errors reported to Problems",
    "json.schema_ok": "✓ Schema validation passed",
    "json.schema_fail": "Schema validation failed: {err}",
    "json.no_schema": "No schema path provided",
    "ai.config_save_failed": "Failed to save AI settings",
    "ai.config_saved": "AI settings updated",
    "ai.auto_debug": "Auto Debug",
    "ai.session_title": "AI Chat (multi-turn)",
    "ai.cache_unavailable": "Cache unavailable",
    "ai.no_content": "AI returned no content",
    "ai.no_code2": "No code",
    "ai.unavailable": "AI unavailable",
    "ai.diff_title": "Preview Diff - {name}",
    "ai.generating": "Generating...",
    "ai.config_title": "AI Assistant Settings",
    "debug.bad_breakpoint": "Cannot set breakpoint here (line out of range)",
    "debug.watch_cleared": "Watch cleared",
    "debug.watch_added": "Watch added: {expr}",
    "debug.cond_cleared": "Conditional breakpoint cleared",
    "debug.cond_set": "Conditional breakpoint: line {line} → {expr}",
    "debug.need_cursor": "Open a file and move the cursor",
    "ai.no_code": "No code to analyze",
    "ai.no_result": "No AI result yet",
    "debug.no_editor": "No active editor",
    "debug.no_session": "No debug session",
    "debug.stopped": "Debugger stopped (host service)",
    "debug.started": "Debugger started (host service)",
    "debug.no_file": "No open file",
    "git.push_failed": "Push failed",
    "git.push_ok": "Push succeeded",
    "git.commit_failed": "Commit failed",
    "git.commit_ok": "Commit succeeded",
    "git.no_file": "No open file",
    "git.no_hunks": "No unstaged hunks",
    "git.error": "Git Error",
    "markdown.ok": "Markdown check passed",
    "markdown.issues": "Markdown check: {n} issues reported",
    "markdown.not_markdown": "Current file is not Markdown",
    "markdown.isolated_export": "Export not supported in isolation",
    "logtail.watching": "Watching: {name}",
    "logtail.none": "(none)",
    "todo.count": "TODO: {n}",
    "todo.filter": "Filter:",
    "markdown.export_failed": "Export failed",
    "markdown.exported": "HTML exported",
    "markdown.open_preview": "Open preview first",
    "markdown.no_headings": "No Markdown headings",
    "logtail.isolated": "Watching current file (isolated)",
    "logtail.no_file": "No open file",
    "logtail.stopped": "Stopped watching",
    "json.formatted": "Formatted successfully",
    "json.error": "JSON Error",
    "json.empty": "No content",
    "line_sort.done": "Sorted {n} lines",
    "line_sort.failed": "Sort failed",
    "line_sort.empty": "No text to sort",
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
