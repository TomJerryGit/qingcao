# 青草编辑器插件开发指南（v2.25）

## 快速开始

```powershell
python tools/new_plugin.py --name my_plugin --display-name "我的插件"
python main.py
# 工具 → 插件管理 → 重载；工具菜单出现「我的插件/运行示例」
```

## 目录结构

```
plugins/my_plugin/
├── plugin.json     # 清单（必需）
├── __init__.py     # 入口：class Plugin(PluginBase)
└── README.md
```

包式插件（带子模块）可用 `__init__.py` + 相对导入；加载器已支持 `submodule_search_locations`。

## plugin.json 字段

| 字段 | 必需 | 说明 |
|---|---|---|
| `name` | ✅ | 唯一 id（小写 snake_case） |
| `display_name` / `version` / `description` / `author` | ✅ | 展示信息 |
| `license` | 推荐 | 如 MIT |
| `type` | ✅ | `plugin` |
| `category` | 推荐 | `tool` / `other` 等（市场分类） |
| `permissions` | ✅ | 见下表；高风险权限会触发安装确认 |
| `dependencies` | 可选 | 依赖的插件 id 列表 |
| `api_version` | ✅ | 当前 `2.0.0` |
| `enabled` / `auto_load` / `load_order` | 可选 | 加载行为 |
| `homepage` / `tags` / `keywords` | 可选 | 市场展示/搜索 |

## 权限与风险等级

| 权限 | 能力 | 风险 |
|---|---|---|
| `editor_read` / `editor_write` | 读/改编辑器内容 | 低 |
| `dialog` | 弹窗/消息 | 低 |
| `filesystem` | 读写文件 | 中 |
| `network` | 网络请求 | 中 |
| `clipboard` | 剪贴板 | 中 |
| `lsp` | 注册 LSP | 中 |
| `process` | 执行系统命令 | **高** |
| `terminal` | 使用终端 | **高** |
| `debugger` | 调试器 | **高** |

高风险权限在安装/更新时会二次确认（`core/plugin_risk.py`）；沙箱插件优先降低风险等级。

## 生命周期与 API

```python
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "my_plugin"
    VERSION = "1.0.0"
    PERMISSIONS = ["editor_read", "dialog"]

    def on_activate(self):
        self.api.log("已激活")
        self.api.add_menu("工具/我的插件/运行", self.run)
        self.api.add_status_item("我的插件就绪")
        self.api.subscribe("file_opened", self.on_file_opened)

    def on_deactivate(self):
        self.api.log("已停用")

    def run(self):
        text = self.api.get_current_text()
        self.api.show_message("我的插件", f"字符数 {len(text)}")
```

常用能力：
- `add_menu(path, callback)`：菜单项（`工具/...`）；
- `add_status_item(text)` / `remove_status_item`；
- `get_current_text()` / `set_current_text()`（需写权限）；
- `subscribe(event, handler)`：`file_opened` / `file_saved` / `tab_changed` 等；
- `register_settings_schema()` + `get_config()/set_config()`；
- 扩展点：补全/悬停/代码操作/符号提供者（见 `capability_plugins_mixin.py`）。

## 本地安装与打包

- 目录方式：复制到 `plugins/<id>/`；
- 压缩包方式：市场安装支持 zip（根目录含 `plugin.json`）；
- 更新：市场「检查更新」/手动重装；重载插件或重启生效。

## 发布到插件市场

1. 在 `plugins/` 下开发并自测；
2. 打包 `plugins/<id>.zip`；
3. 运行注册表发布流程（维护者）：`python tools/publish_registry_release.py`；
4. 注册表签名（Ed25519）后客户端可校验来源。

## 测试建议

- 单测：`from app.plugins import PluginBase` 后直接测纯逻辑；
- 集成：启动编辑器 → 插件面板重载 → 观察日志；
- 兼容性：清单 `api_version` 与宿主校验；
- 避免在 `on_activate` 做重 IO（会拖慢启动，可延迟到首次使用）。

## 常见问题

| 现象 | 排查 |
|---|---|
| 插件未出现在列表 | `plugin.json` 是否合法、`enabled` 是否为 true |
| 菜单未出现 | `add_menu` 路径是否以 `工具/` 开头；权限是否足够 |
| 安装被拒绝 | 高风险权限需在确认框中允许 |
| 市场不显示评分 | `ratings.json` 验签失败或该插件无评分数据 |
