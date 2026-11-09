# -*- coding: utf-8 -*-
"""插件安装风险分级（v2.24 安全闭环）。

高权限插件在安装/更新前必须显式确认；沙箱可降低一档风险。
"""

HIGH_RISK_PERMISSIONS = frozenset({"process", "terminal", "debugger"})
MEDIUM_RISK_PERMISSIONS = frozenset({"filesystem", "network", "clipboard", "lsp"})
LEVEL_LABELS = {"high": "高", "medium": "中", "low": "低"}


def classify_plugin_risk(permissions, sandboxed=False):
    """返回 high / medium / low。

    - process/terminal/debugger：默认 high；已被沙箱隔离则降为 medium；
    - filesystem/network/clipboard/lsp：沙箱外 medium，沙箱内 low；
    - 其他：low。
    """
    perms = {str(p) for p in (permissions or []) if p}
    if perms & HIGH_RISK_PERMISSIONS:
        return "medium" if sandboxed else "high"
    if sandboxed:
        return "low"
    if perms & MEDIUM_RISK_PERMISSIONS:
        return "medium"
    return "low"


def risk_message(info, action="安装"):
    """返回 (标题, 正文, 等级)。"""
    perms = [str(p) for p in (getattr(info, "permissions", None) or [])]
    sandboxed = bool(getattr(info, "sandbox", False))
    level = classify_plugin_risk(perms, sandboxed=sandboxed)
    title = "高风险插件" if level == "high" else "插件权限确认"
    name = getattr(info, "display_title", None) or getattr(info, "name", "?")
    text = (
        "插件 %s 请求以下权限：\n\n%s\n\n风险等级：%s%s\n\n"
        "高权限插件可执行本机命令/访问文件，请仅安装可信来源。\n\n是否继续%s？"
        % (
            name,
            "\n".join("• " + p for p in perms) if perms else "（无声明权限）",
            LEVEL_LABELS.get(level, level),
            "（已沙箱）" if sandboxed else "（未沙箱）",
            action,
        )
    )
    return title, text, level
