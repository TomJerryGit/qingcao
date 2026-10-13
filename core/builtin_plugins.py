# -*- coding: utf-8 -*-
"""内置插件清单（打包与权限授权共用的**单一可信来源**）

为什么需要这个模块
------------------
打包时 `QingCaoEditor.spec` 把整个 `plugins/` 目录作为数据文件打进包，
所以**内置插件与从插件市场下载的第三方插件位于同一目录**，无法靠路径
区分。

而权限确认对话框（`PermissionConfirmDialog`）对危险权限是**模态阻塞**的：
必须用户点"允许"才继续。这带来一个真实缺陷：

    内置插件（AI 助手 network / Git process / Python 调试 process）
    在首次启动时会各弹一个模态框。用户漏点其中一个、或对话框被主窗口
    遮挡，该插件就**永久不激活**，而且界面上没有任何提示 ——
    表现为"AI/Git 菜单根本没有"。

修复思路：**内置插件自动授权**（它们随主程序一同安装，来源可信），
第三方插件仍然强制弹框确认。

维护约定（重要）
----------------
新增内置插件时必须同时：
  1. 在此处加入 `BUILT_IN_PLUGINS`；
  2. 在 `build.py` 的 `PLUGIN_RUNTIME_DEPS` 里补上它的运行时依赖（若有）。

`tests/test_builtin_plugins.py` 会校验本清单与磁盘上的插件目录一致，
防止遗漏后出现"插件装进包但不加载"或反之的漂移。
"""
from typing import FrozenSet


# 随程序一同发布的内置插件（目录名，与 plugin.json 的 name 一致）
BUILT_IN_PLUGINS: FrozenSet[str] = frozenset({
    "ai_assistant",       # AI 助手（network）
    "demo",               # 示例插件
    "git_deep",           # Git 深度集成（process）
    "json_formatter",     # JSON 格式化
    "logtail",            # 日志监视
    "markdown_preview",   # Markdown 预览
    "my_plugin",          # 示例插件
    "python_debugger",    # Python 调试器（process）
    "todo_panel",         # TODO 面板
    "wordcount",          # 字数统计
})


def is_built_in(plugin_name: str) -> bool:
    """判断是否为随程序发布的内置插件（大小写不敏感）"""
    return (plugin_name or "").strip().lower() in BUILT_IN_PLUGINS

