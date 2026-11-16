# 插件样例与分类说明（P4）

| 插件 | 类型 | 状态 | 说明 |
|---|---|---|---|
| `demo` | 示例 | 启用 | 最小插件模板（菜单/状态/设置/i18n） |
| `my_plugin` | 脚手架示例 | **默认禁用** | `tools/new_plugin.py` 生成的占位示例 |
| `sandbox_demo` | 示例 | 禁用 | manifest `sandbox:true` 只读子进程示例 |
| `wordcount_sandbox` | 沙箱试点 | 启用 | 字数统计只读沙箱样例 |
| `whitespace_sandbox` | 沙箱诊断 | 启用 | 行尾空白/Tab/超长行 |

## 模板真实采用：line_sort

- 通过 `tools/new_plugin.py` 生成后实现「行排序」：升序/降序/去重，支持选区或整文件；
- 权限：`editor_read`/`editor_write`/`dialog`；设置项 `case_sensitive`；
- 测试：`tests/test_v226_line_sort_plugin.py` + conformance 清单契约。

## 处理原则

- 示例插件保留用于说明扩展点，但默认不干扰普通用户（`my_plugin` 禁用）；
- 市场分类中标记 `sample`/`sandbox`，避免与生产插件混淆；
- 新增插件请以 `demo` 为模板，不使用 `my_plugin` 作为起点。

## 目录与趋势

- 自动生成插件目录：`python tools/plugin_catalog.py` → `docs/plugin_catalog.md`；
- 每周性能趋势：`Ratings Report` 同款 `Perf Trend` 工作流（周一 06:30 UTC）。
