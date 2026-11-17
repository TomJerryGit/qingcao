# 插件开发指南（10 分钟上手）

## 1. 生成脚手架

```powershell
python tools/new_plugin.py --name hello_tool --display-name "Hello" `
  --permissions editor_read,dialog --points settings,status
```

生成：`plugins/<name>/plugin.json` + `__init__.py`（`PluginBase` 子类，默认过 conformance 清单契约）。

## 2. 生命周期与权限

| 钩子 | 说明 |
|---|---|
| `on_activate` | 注册菜单/状态栏/设置/provider；**不要阻塞** |
| `on_deactivate` | 清理定时器/面板/诊断 |

权限按需声明（`plugin.json.permissions`）：`editor_read`、`editor_write`、`dialog`、`filesystem`、`network`、`process`（高危）、`terminal`、`lsp`、`debugger`。

- 网络/进程/终端等高风险能力需用户确认；隔离模式下由宿主 broker 校验。
- 大文件/网络操作使用 `api.run_background`，避免卡 UI。

## 3. 常用扩展点

| 扩展点 | API |
|---|---|
| 菜单/命令 | `add_menu` / `register_command` |
| 状态栏 | `add_status_item` |
| 设置页 | `register_settings_schema` |
| 补全/Hover/代码操作 | `register_*_provider` |
| 诊断 | `publish_diagnostics` / `clear_diagnostics` |
| 面板 | `add_panel`（隔离插件用远程面板） |

## 4. 测试与发布

```powershell
python -m pytest tests/test_plugin_conformance.py -q
python tools/check_plugin_market.py --strict
python tools/plugin_catalog.py
```

- 新插件必须通过 conformance + 市场元数据（homepage/keywords）；
- 推荐 ≥8 个测试用例（权限拒绝/大文件/异常路径）；
- 第三方插件建议签名（Ed25519，见 `docs/key_rotation.md`）。

## 5. 隔离与沙箱

- manifest `"sandbox": true` → 只读子进程（symbols/hover/diagnostics 等）；
- B2.1/B2.2 隔离集合：demo/wordcount/json_formatter/todo_panel/markdown_preview/logtail；
- 高风险插件暂留进程内（B2.2/B3 规划）。

## 6. 参考

- `demo`（最小模板）、`line_sort`（模板真实采用）、`wordcount`（远程面板）、`json_formatter`（provider）。
