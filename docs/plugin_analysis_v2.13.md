# 插件全面分析报告（v2.13.0 基线）

> 工具: `tools/analyze_plugins.py` / `tools/bench_plugins.py` / `tools/audit_plugins.py`

## 1. 功能与结构一览

| 插件 | 版本 | 启用 | 沙箱 | LOC | 扩展点 | 重依赖 | refresh_theme | 硬编码QSS | 线程 | 文件IO | 网络 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ai_assistant | 1.0.0 | ✓ | ✗ | 3233 | add_menu,add_panel,add_status_item,register_comman | requests | ✗ | 19 | 3 | 0 | 16 |
| demo | 1.0.0 | ✓ | ✗ | 36 | add_menu,add_status_item,register_settings_schema | - | ✗ | 0 | 0 | 0 | 0 |
| git_deep | 1.0.0 | ✓ | ✗ | 187 | add_menu,add_status_item,register_command,register | - | ✗ | 0 | 0 | 0 | 0 |
| json_formatter | 1.0.0 | ✓ | ✗ | 279 | add_editor_context_menu,add_menu,clear_diagnostics | - | ✗ | 0 | 0 | 0 | 0 |
| logtail | 1.0.0 | ✓ | ✗ | 248 | add_menu,add_status_item,register_settings_schema | - | ✗ | 2 | 0 | 0 | 0 |
| markdown_preview | 1.0.0 | ✓ | ✗ | 217 | add_menu,clear_diagnostics,publish_diagnostics,reg | - | ✗ | 1 | 0 | 0 | 0 |
| my_plugin | 1.0.0 | ✓ | ✗ | 43 | add_menu,register_settings_schema | - | ✗ | 0 | 0 | 0 | 0 |
| python_debugger | 2.0.0 | ✓ | ✗ | 1906 | add_menu,clear_all_breaks,clear_breakpoints | - | ✗ | 0 | 3 | 0 | 28 |
| sandbox_demo | 1.0.0 | ✗ | ✓ | 31 | - | - | ✗ | 0 | 0 | 0 | 0 |
| spell_check | 1.0.0 | ✓ | ✓ | 340 | add_editor_context_menu,add_menu,add_status_item,c | - | ✗ | 0 | 0 | 0 | 1 |
| todo_panel | 1.0.0 | ✓ | ✗ | 312 | add_menu,add_status_item,register_settings_schema | - | ✗ | 2 | 0 | 0 | 1 |
| wordcount | 1.0.0 | ✓ | ✗ | 215 | add_menu,add_status_item,register_settings_schema | - | ✗ | 3 | 0 | 0 | 0 |

## 2. 导入增量耗时（预热宿主模块后）

| 插件 | import_ms（增量） | 字节 |
|---|---|---|
| ai_assistant | 713.4 | 120557 |
| python_debugger | 14.0 | 25229 |
| spell_check | 1.9 | 15173 |
| wordcount | 1.4 | 6792 |
| markdown_preview | 1.3 | 7446 |
| todo_panel | 1.2 | 9607 |
| demo | 1.0 | 1096 |
| logtail | 1.0 | 7585 |
| json_formatter | 0.8 | 10063 |
| git_deep | 0.7 | 5577 |
| sandbox_demo | 0.6 | 1063 |
| my_plugin | 0.5 | 1265 |

## 3. 关键发现

- **性能**：预热宿主模块后，插件增量导入耗时见上表；
  此前 5.2s 的 ai_assistant 读数主要来自宿主模块首次导入（真实运行时已加载）。
- **UI/主题**：多数插件面板硬编码深色 QSS、未实现 `refresh_theme`；
  宿主已在启动/切换主题时递归 `adapt_widget_styles` 统一适配（本次修复启动路径）。
- **安全**：`python_debugger` 使用 eval/compile + subprocess（review）；
  `spell_check` 文件写操作（已沙箱化）。
- **沙箱就绪**：spell_check / sandbox_demo；只读类插件可继续迁移。

## 4. 提升计划

### Batch 1（本次已做）
- 启动主题统一递归适配插件面板硬编码 QSS；
- 新增分析/基准工具与测试，建立基线。

### Batch 2（下一步）
- 插件面板实现 `refresh_theme(theme)` 精准刷新；
- ai_assistant 配置/对话 UI 统一主题；
- wordcount 等只读插件沙箱试点。

### Batch 3（中长期）
- python_debugger 安全复核与权限收敛；
- 插件性能预算纳入 CI；
- 市场预留字段（分类/截图/许可）。

## 5. Batch 2 执行结果（2026-10-28）

- ai_assistant 可选依赖 requests 改为惰性检测：**713ms -> 380ms（-47 percent）**；
- wordcount / todo_panel / logtail / markdown_preview 增加 refresh_theme(theme) 精准刷新（adapt_qss_colors），切主题不再依赖全量递归；
- 当前增量导入 Top3：ai_assistant 380.3ms, markdown_preview 210.2ms, spell_check 52.5ms。

## 6. Batch 3 执行结果（2026-10-28）

- python_debugger：manifest 补充 `process` 权限；eval 表达式限制 4000 字符（仍在调试目标子进程内执行）；
- 插件性能预算门禁：`tools/bench_plugins.py --check --factor 3.0`，已接入 CI；
- wordcount 沙箱试点：新增 `plugins/wordcount_sandbox`（sandbox:true），宿主状态栏通过 RPC 传入当前文本，插件返回「字数/字符/行」；
- 沙箱协议扩展：`status_text(text)` 支持文本参数（worker/manager/宿主）。

## 7. Batch 4 执行结果（2026-10-29）

- 修正插件基准工具 sys.path 缺陷（预热此前静默失败，数字虚高）；
- 真实增量导入：**ai_assistant 1.8ms、python_debugger 8.9ms**，均远低于 150ms 目标；
- ai_assistant 增加 `refresh_theme(theme)`：面板基样式 + 子控件内联 QSS 统一适配主题；
- 插件市场元数据：全部 13 个插件补齐 `homepage`/`keywords`，新增 `tools/check_plugin_market.py` 校验（category/license/homepage/keywords/description）。
