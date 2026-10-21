# 插件脚手架（tools/new_plugin.py）

对应 Notepad++ 的 pluginTemplate：把第三方插件门槛从"读 2000 行 PluginAPI"
降到"填几个参数"。生成的 manifest 与代码**默认通过**
`tests/test_plugin_conformance.py` 的清单规则。

## 用法

```powershell
python tools/new_plugin.py --name hello_tool
python tools/new_plugin.py --name json_paths `
    --display-name "JSON 路径" `
    --permissions editor_read,editor_write,dialog `
    --points settings,status,hover,diagnostics,symbols
```

| 参数 | 说明 |
|---|---|
| `--name` | 内部名，`[a-z][a-z0-9_]{2,30}` |
| `--display-name` | 显示名（默认同 name） |
| `--permissions` | 逗号分隔，默认 `editor_read` |
| `--points` | settings,status,completion,hover,diagnostics,background,code_action,context_menu,decoration,symbols |
| `--output` / `--force` | 输出目录 / 覆盖已存在目录 |

## 生成内容

```
plugins/<name>/
├── plugin.json    # 必填字段齐全（含 api_version/load_order）
└── __init__.py    # PluginBase 子类 + 生命周期 + 所选扩展点示例
```

## 下一步

```powershell
python -m pytest tests/test_plugin_conformance.py -q
# 在「工具 → 插件管理」启用
```
