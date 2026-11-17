# 架构拆分第五批（v2.25 阶段 2.1）

| 模块 | 拆分前 | 拆分后 | 结构 |
|---|---|---|---|
| `infrastructure/icon_manager.py` | 1,568 | **609** | `icon_manager_common`(152) + `_cache`(87) + `_providers`(686) |

- 公共：头/常量/`IconState`/`CacheEntry`（动态 `__all__`）；
- 缓存：`IconCache`；
- 提供者：`IconProvider` 及 SVG/PNG/Theme/Emoji/Builtin 实现；
- 主模块：`IconManager` + 便捷函数，保持全部对外导入兼容；
- 架构门禁新增 `test_icon_manager_split`（主 <750，最大子模块 <800）。

## 能力接线拆分（v2.25 阶段 2.3）

| 模块 | 拆分前 | 拆分后 | 内容 |
|---|---|---|---|
| `ui/mixins/capability_wiring_mixin.py` | 1,537 | **75** | 聚合入口 + 格式菜单 |
| `capability_wiring_common.py` | — | 52 | 公共导入 |
| `capability_keyseq_mixin.py` | — | 275 | 多键快捷键/过滤器 |
| `capability_plugins_mixin.py` | — | 326 | 插件扩展点注册 |
| `capability_panels_mixin.py` | — | 553 | 面板/导出/工具菜单 |
| `capability_commands_mixin.py` | — | 292 | 插件命令/调试/启动主题 |

- 组合方式：`CapabilityWiringMixin(KeySequenceMixin, PluginsMixin, PanelsExportMixin, CommandsThemeMixin)`；
- 静态测试改为拼接 `ui/mixins/capability_*.py` 读取，避免拆分导致误报；
- 顺带修复 `TerminalTab.clear_output` 残留的 `_screen` 引用（非 PTY 标签无屏幕缓冲）。

## 阶段 2.4：三个 1,500 行文件

| 模块 | 拆分前 | 拆分后 | 结构 |
|---|---|---|---|
| `ui/global_search_panel.py` | 1,514 | **986** | common(149) + tree(370) + panel |
| `ui/keymap_editor.py` | 1,503 | **676** | common(288) + dialogs(496) + editor |
| `core/lsp_client.py` | 1,501 | **1,217** | utils(292，含 `_default_capabilities`/URI/能力/`dump`) + client |

- 拆分后均 <1,300；`GlobalSearchPanel`/`KeymapEditor`/`LspClient`/`LspServerRegistry` 等对外导入保持兼容；
- 修复装饰器方法（`@staticmethod`）随方法块迁移，避免 `IndentationError`。

## 阶段 2.6：架构门禁（棘轮）

- 业务代码默认 **≤1,300 行**；
- 全局（除归档）**≤1,800 行**；
- 历史长尾 10 个文件列入白名单：上限 ≤1,500，且**一旦降到 ≤1,300 必须移除**（测试强制）；
- 新增文件/拆分产物不得再突破 1,300。

## 阶段 R2：三个 1.4k 文件拆分（v2.26.1）

| 模块 | 拆分前 | 拆分后 | 子模块 |
|---|---|---|---|
| `ui/directory_tree.py` | 1,478 | **1,072** | `directory_tree_ops.py`（右键菜单/文件操作 417） |
| `core/macro.py` | 1,455 | **610** | `macro_common.py`(88) + `macro_recorder.py`(781) |
| `ui/plugin_store.py` | 1,432 | **1,081** | `plugin_store_card.py`（卡片+评分筛选辅助 358） |

- 架构白名单 10 → **7**；`test_v225_architecture_ratchet` 通过；
- 相关测试（macro/directory/plugin_store/market/架构）：20/20。
