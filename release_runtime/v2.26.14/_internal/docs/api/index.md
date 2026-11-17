# PluginAPI 参考

`PluginAPI` 是插件与编辑器交互的唯一入口（`app/plugins.py`）。
所有方法都按插件声明的 `permissions` 做门控。

获取方式：在 `on_activate()` 中通过 `self.api` 使用。

> **权限标注约定**：下表 `权限` 列为空表示无需权限；标 `—` 表示为
> 只读查询。方法在缺权限时**不抛异常**，而是提示状态栏并返回
> 失败值（`None` / `False` / `""`）。

---

## 权限管理

| 方法 | 权限 | 说明 |
|---|---|---|
| `has_permission(perm)` | — | 是否拥有某权限 |
| `require_permission(perm)` | — | 检查并提示；返回 `bool` |
| `revoke_permission(perm)` | — | 撤销权限 |
| `grant_permission(perm)` | — | 仅宿主可调用；插件自行调用会被拒绝 |
| `get_main_window()` | `dialog` | 获取主窗口 |

> `api.win` 属性**已弃用**，保留仅为兼容旧插件，访问时会打印告警。
> 新代码请用 `get_main_window()`。

## 编辑器访问

| 方法 | 权限 | 说明 |
|---|---|---|
| `current_editor()` | — | 当前活动编辑器代理（`EditorProxy`）或 `None` |
| `all_editors()` | — | 所有打开的编辑器代理 |
| `get_editor_count()` | — | 打开的编辑器数量 |
| `get_selected_text()` | `editor_read` | 当前选中文本 |
| `get_current_text()` | `editor_read` | 当前编辑器全文 |
| `get_current_filepath()` | `editor_read` | 当前文件路径 |
| `get_cursor_position()` | `editor_read` | `(行, 列)`，从 0 开始 |
| `insert_text(text, at_cursor=True)` | `editor_write` | 插入文本 |
| `replace_selected_text(text)` | `editor_write` | 替换选中内容 |
| `set_editor_text(text)` | `editor_write` | 替换全文 |
| `open_file(filepath)` | `editor_write` | 在编辑器中打开文件 |
| `save_current_file()` | `editor_write` | 保存当前文件 |
| `new_tab(title="")` | `editor_write` | 新建标签页 |
| `close_current_tab()` | `editor_write` | 关闭当前标签 |
| `goto_line(line)` | `editor_read` | 跳转到行（从 0 开始） |
| `goto_position(position)` | `editor_read` | 跳转到字符位置 |
| `select_range(start, end)` | `editor_read` | 选中范围 |
| `highlight_text(pattern)` | `editor_read` | 高亮所有匹配 |
| `clear_highlights()` | `editor_read` | 清除高亮 |

## UI 注册

| 方法 | 权限 | 说明 |
|---|---|---|
| `add_menu(path, callback, shortcut="")` | — | 添加菜单项，`path` 形如 `"工具/我的功能"` |
| `remove_menu(action)` | — | 移除菜单项 |
| `add_toolbar_action(text, callback, icon="")` | — | 添加工具栏按钮 |
| `register_shortcut(shortcut, callback)` | — | 注册全局快捷键 |
| `add_panel(title, widget, area=..., visible=False)` | — | 添加可停靠面板 |
| `remove_panel(dock)` / `toggle_panel(dock)` | — | 移除 / 切换面板 |
| `register_command(name, callback, description="")` | — | 注册命令（可在命令面板搜索） |
| `execute_command(name)` / `list_commands()` | — | 执行 / 列出命令 |
| `register_lexer(extension, lexer_factory)` | — | 注册自定义语法高亮 |
| `get_lexer(extension)` | — | 获取 lexer |
| `register_lsp(language_id, server_command, extensions)` | `lsp` | 注册 LSP 服务器 |
| `get_lsp_server(language_id)` | `lsp` | 获取 LSP 启动命令 |

## 事件总线

| 方法 | 权限 | 说明 |
|---|---|---|
| `subscribe(event_name, callback)` | — | 订阅事件 |
| `unsubscribe(event_name, callback)` | — | 取消订阅 |
| `emit_event(event)` | — | 发射事件 |
| `send_message(target_plugin, message)` | — | 向其他插件发消息 |

事件名示例：`file_opened`、`file_saved`、`cursor_moved`、`status_message`。
具体事件类定义见 `core/events.py`。

## 对话框与提示

| 方法 | 权限 | 说明 |
|---|---|---|
| `show_status(message, timeout=..., level=...)` | — | 状态栏消息 |
| `show_notification(title, message, level=...)` | `dialog` | 通知 |
| `show_message(title, message, icon=...)` | `dialog` | 消息框 |
| `ask_yes_no(title, message)` | `dialog` | 是/否询问 |
| `ask_string(title, label, default="")` | `dialog` | 输入字符串 |
| `ask_integer(title, label, default=0, min_val=..., max_val=..., step=1)` | `dialog` | 输入整数 |
| `ask_item(title, label, items, current=0)` | `dialog` | 列表选择 |
| `open_file_dialog(title, directory, file_filter)` | `dialog` | 打开文件 |
| `open_files_dialog(...)` | `dialog` | 打开多文件 |
| `save_file_dialog(...)` | `dialog` | 保存文件 |
| `choose_directory(title, directory)` | `dialog` | 选择目录 |
| `show_text_dialog(title, text, width=..., height=...)` | `dialog` | 显示文本 |

## 文件系统

| 方法 | 权限 | 说明 |
|---|---|---|
| `read_file(filepath, encoding="utf-8")` | `filesystem` | 读取文本 |
| `read_file_bytes(filepath)` | `filesystem` | 读取二进制 |
| `write_file(filepath, content, encoding="utf-8")` | `filesystem` | 写入文本 |
| `write_file_bytes(filepath, content)` | `filesystem` | 写入二进制 |
| `file_exists(filepath)` | `filesystem` | 是否存在 |
| `is_directory(path)` | `filesystem` | 是否目录 |
| `list_directory(path)` | `filesystem` | 列出目录内容 |
| `get_plugin_data_dir()` | `filesystem` | 插件私有数据目录（自动创建） |
| `get_config(key, default=None)` | — | 读插件配置（QSettings） |
| `set_config(key, value)` | — | 写插件配置 |
| `save_plugin_config(data)` | `filesystem` | 存 JSON 配置到数据目录 |
| `load_plugin_config()` | `filesystem` | 读 JSON 配置 |

> 注意：`get_plugin_data_dir()` 与 `save_plugin_config()` **需要
> `filesystem` 权限**。早期版本它们是免权限的写盘后门，已修复。

## 网络

| 方法 | 权限 | 说明 |
|---|---|---|
| `http_get(url, timeout=10, headers=None)` | `network` | HTTP GET |
| `http_post(url, data=None, json_data=None, timeout=10, headers=None)` | `network` | HTTP POST |
| `download_file(url, filepath, timeout=...)` | `network` + `filesystem` | 下载文件 |

## 剪贴板

| 方法 | 权限 | 说明 |
|---|---|---|
| `get_clipboard()` | `clipboard` | 读剪贴板 |
| `set_clipboard(text)` | `clipboard` | 写剪贴板 |

## 进程执行

| 方法 | 权限 | 说明 |
|---|---|---|
| `run_command(command, cwd=None, timeout=...)` | `process` | 执行系统命令并返回输出 |
| `run_python(code)` | `process` | **在当前进程**执行 Python 代码 |

> ⚠️ `run_python` 直接在主解释器中 `exec`，等同于插件取得全部能力。
> 仅供可信插件使用。

## 主题

| 方法 | 权限 | 说明 |
|---|---|---|
| `get_current_theme()` | — | 当前主题路径 |
| `apply_theme(theme_path)` | — | 应用主题 |

## 其它

| 方法 | 说明 |
|---|---|
| `log(message)` | 写日志 |
| `cleanup()` | 清理所有注册资源（卸载时自动调用） |
| `get_api_version()` | API 版本（当前 `2.0.0`） |
| `get_plugin_name()` | 当前插件名 |

> 插件 API 版本（`api_version` / `CURRENT_API_VERSION`）与应用版本
> （`version.py`）是**两个独立的版本号**：API 版本描述接口契约，
> 应用版本描述编辑器自身。

## PluginBase

插件主类应继承 `PluginBase`（`app/plugins.py`）：

```python
class PluginBase:
    NAME = ""
    VERSION = ""
    DESCRIPTION = ""
    AUTHOR = ""
    PERMISSIONS = []

    def __init__(self):
        self.api = None

    def activate(self, api):
        """由 PluginLoader 调用：设置 self.api 后回调 on_activate()"""
        self.api = api
        self.on_activate()

    def deactivate(self):
        """由 PluginLoader 调用：回调 on_deactivate() 并清理资源"""
        try:
            self.on_deactivate()
        finally:
            if self.api:
                self.api.cleanup()

    def on_activate(self):
        """子类重写：实现激活逻辑"""

    def on_deactivate(self):
        """子类重写：实现清理逻辑"""
```

> 上表与代码保持一致；若发现文档与 `app/plugins.py` 不符，
> **以代码为准**并欢迎提 Issue。
