# 插件开发

## 目录结构

```
plugins/
└── my_plugin/
    ├── plugin.json      # 插件清单（必需）
    ├── __init__.py      # 插件入口（必需）
    └── README.md        # 插件说明（可选）
```

## 最小可用插件

### 1. `plugin.json`

```json
{
  "name": "my_plugin",
  "display_name": "我的插件",
  "version": "1.0.0",
  "description": "插件简介",
  "author": "your-name",
  "license": "MIT",
  "type": "plugin",
  "category": "tool",
  "tags": ["demo"],
  "permissions": ["editor_read", "dialog"],
  "dependencies": [],
  "plugin_dependencies": [],
  "api_version": "2.0.0",
  "enabled": true,
  "auto_load": true,
  "load_order": 100,
  "hot_reload": true
}
```

字段说明：

| 字段 | 必需 | 说明 |
|---|---|---|
| `name` | ✅ | 唯一标识，**必须是合法 Python 标识符**（`[A-Za-z_][A-Za-z0-9_]*`），否则校验失败 |
| `display_name` | | 界面上显示的名称，留空则用 `name` |
| `version` | ✅ | 语义化版本 |
| `permissions` | | 权限列表，见下文 |
| `main_class` | | 入口文件中的主类名，**默认 `Plugin`** |
| `entry_point` | | 入口文件名，**默认 `__init__.py`** |
| `auto_load` | | 是否随编辑器启动自动加载 |
| `load_order` | | 加载顺序，越小越先（默认 100） |
| `hot_reload` | | 设为 `false` 可让本插件退出热重载 |

### 2. `__init__.py`

```python
# -*- coding: utf-8 -*-
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "my_plugin"
    VERSION = "1.0.0"
    DESCRIPTION = "我的插件"
    AUTHOR = "your-name"

    def on_activate(self):
        """插件激活时调用；此时 self.api 已可用"""
        self.api.log("插件已激活")

        self.api.add_menu(
            "工具/我的插件/执行",
            self.run_action,
            shortcut="Ctrl+Alt+U",
        )

    def on_deactivate(self):
        """插件卸载时调用"""
        self.api.log("插件已卸载")

    def run_action(self):
        text = self.api.get_current_text()
        self.api.show_message("文件信息", f"字符数: {len(text)}")
```

> **关键**：编辑器加载时先执行 `plugin_instance.activate(api)`
> （由 `PluginBase` 提供，会设置 `self.api`），然后才回调
> `on_activate()`。因此**在 `on_activate` 里可以直接用 `self.api`**，
> 不要在 `__init__` 里访问它。

## 权限

插件必须在 `plugin.json` 中声明所需权限。**首次启用时会弹出确认
对话框**（危险权限必须由用户手动允许，可勾选"记住"）。

| 权限 | 说明 | 危险 |
|---|---|---|
| `editor_read` | 读取编辑器内容（`get_current_text` / `get_selected_text`） | |
| `editor_write` | 修改编辑器内容（`insert_text` / `set_editor_text` 等） | |
| `filesystem` | 读写本地文件、访问插件私有数据目录 | |
| `network` | HTTP 请求（`http_get` / `http_post` / `download_file`） | ⚠️ |
| `process` | 执行系统命令 / Python 代码 | ⚠️ |
| `clipboard` | 读写剪贴板 | |
| `dialog` | 显示对话框、访问主窗口 | |
| `terminal` | 使用集成终端 | ⚠️ |
| `lsp` | 注册 LSP 服务（`register_lsp`） | |
| `debugger` | 调试功能 | ⚠️ |

### 权限是 API 门控，不是安全沙箱

> ⚠️ **务必理解这一点**：编辑器目前**没有进程级隔离**。插件与编辑器
> 在同一进程、同一解释器中运行，`permissions` 只在 `PluginAPI` 的
> 方法边界上做检查。
>
> 插件仍然可以直接 `import subprocess`、`import socket`、`open(...)`，
> 绕过所有声明。因此：
>
> - **只安装来自可信来源的插件**；
> - 不要把手写恶意插件当作被防护的场景。
>
> 仓库中曾有一套沙箱原型（`plugin_sandbox.py` / `sandbox_runtime.py`），
> 但经实测它**无法启动**（`PluginSandbox.start()` 返回 `False`、状态卡在
> `RESTARTING`），且没有任何生产调用方。为避免误导，**该原型已从代码库
> 移除**（如需查阅，见 git 历史 `2.1.1` 之前的提交）。
>
> 真要做进程隔离是一项结构性改造：现有 `PluginAPI` 大量操作 QWidget
> （面板、菜单、对话框），子进程拿不到这些对象，API 边界需要重新设计。

### 未声明权限时的表现

调用无权限的 API 不会抛异常，而是**在状态栏提示并返回失败值**：

```python
def run(self):
    if not self.api.require_permission("filesystem"):
        return                      # 已提示用户，安全返回
    data = self.api.read_file("/some/path")
```

也可以主动查询：

```python
if self.api.has_permission("network"):
    ...
```

## 生命周期

| 阶段 | 触发 |
|---|---|
| 发现 | 扫描 `plugins/` 下的子目录，解析 `plugin.json` |
| 加载 | `importlib` 执行 `__init__.py` |
| 激活 | 实例化主类 → `activate(api)` → `on_activate()` |
| 卸载 | `deactivate()` → `on_deactivate()` → `api.cleanup()` |

`api.cleanup()` 会自动清理插件通过 API 注册的资源（菜单、工具栏、
面板、快捷键、事件订阅、命令），因此**不必手工反注册**。但如果插件
自己创建了线程/文件句柄，请在 `on_deactivate` 中释放。

## 热重载

编辑器默认监控 `plugins/` 与插件源码文件；检测到变更后自动执行
unload → load → activate。控制方式：

- 全局开关：首选项中的 `plugin_hot_reload`
- 单插件退出：在 `plugin.json` 中设 `"hot_reload": false`

> 适用于开发调试。若插件持有长连接、后台线程或外部状态，建议关闭
> 其热重载，避免重入问题。

## 日志与调试

```python
self.api.log("普通信息")
self.api.show_status("状态栏消息", timeout=3000, level="info")
self.api.show_message("标题", "内容")
```

运行日志写入 `logs/runtime.log`；插件加载错误的完整堆栈也会打印到
控制台。插件管理面板会显示每个插件的状态与错误信息。

## 打包 Python 依赖

`plugin.json` 的 `dependencies` 声明 PyPI 包名（如 `["requests"]`）。
插件市场安装流程会据此 `pip install`；**手动安装的插件需要自行
安装依赖**。

## 参考

- [API 文档](api/index.md) — `PluginAPI` 完整接口
- 脚手架：`python tools/create_plugin.py my_plugin`
- 官方示例：`plugins/demo/`（最小示例）、`plugins/wordcount/`（带面板）
