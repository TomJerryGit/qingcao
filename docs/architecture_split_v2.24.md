# v2.24 架构拆分第二批（W1）

## 成果

| 模块 | 拆分前 | 拆分后 | 结构 |
|---|---|---|---|
| `app/plugin_api.py` | 2,027 | **503** | `plugin_api_common.py`(162) + `editor`(236) + `ui`(634) + `data`(309) + `events`(517) |
| `ui/editor_view.py` | 1,906 | **537** | `editor_view_common.py`(411) + `input`(667) + `paint`(235) + `completion`(233) + `lexer`(145) |
| `plugins/ai_assistant/__init__.py` | 2,872 | **1,242** | `ai_common.py`(305) + `ai_worker.py`(151) + `ai_result_dialog.py`(744) + `ai_config_dialog.py`(386) + `ai_panel.py`(464) |

- `PluginAPI` 由 4 个 Mixin + 核心权限/生命周期组成，**104 个公开方法保持可用**；
- `EditorWidget` 由 4 个 Mixin + 核心配置/主题/指标组成，`issubclass(EditorWidget, QsciScintilla)` 保持；
- ai_assistant 的 `AIWorker/AIResultDialog/AIConfigDialog/OllamaPanel/Plugin` 全部从包根 re-export，兼容既有导入。

## 加载器增强：包式插件
- `plugin_loader._import_module` 对 `__init__.py` 入口设置 `submodule_search_locations`，支持插件内部相对导入（拆分后的 ai_assistant 依赖此能力）；
- 非包插件（单文件 `__init__.py` 不在包目录？仍按原逻辑）不受影响；
- 回归：`tests/test_v224_architecture_split.py`、`test_builtin_plugin_migrations.py`、`test_ai_enhancements.py`。

## 验收
- 新文件均 ≤ 1,500 行（目标）；`PluginAPI`/`EditorWidget` MRO 与公开方法回归通过；
- 全量测试（分片）与 CI 通过。

## 剩余巨石（下一批候选）
按 v2.23 审计：`app/tabs.py`、`core/content_provider.py`、`core/document.py`、`core/editor.py`、`ui/outline_panel.py`、`app/session.py`、`plugins/ai_assistant/__init__.py`(仍 1,242，可继续拆 Plugin 方法)。
