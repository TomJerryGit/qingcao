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
