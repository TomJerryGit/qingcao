# 架构拆分第五批（v2.25 阶段 2.1）

| 模块 | 拆分前 | 拆分后 | 结构 |
|---|---|---|---|
| `infrastructure/icon_manager.py` | 1,568 | **609** | `icon_manager_common`(152) + `_cache`(87) + `_providers`(686) |

- 公共：头/常量/`IconState`/`CacheEntry`（动态 `__all__`）；
- 缓存：`IconCache`；
- 提供者：`IconProvider` 及 SVG/PNG/Theme/Emoji/Builtin 实现；
- 主模块：`IconManager` + 便捷函数，保持全部对外导入兼容；
- 架构门禁新增 `test_icon_manager_split`（主 <750，最大子模块 <800）。
