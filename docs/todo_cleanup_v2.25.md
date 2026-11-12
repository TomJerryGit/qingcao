# TODO/FIXME 清理计划（v2.25）

- 总计：45 处（源码，排除 tools/_archive）

| 文件 | 数量 |
|---|---|
| `plugins/todo_panel/__init__.py` | 17 |
| `tools/health_check.py` | 11 |
| `core/code_smell.py` | 5 |
| `tools/audit_stubs.py` | 4 |
| `tools/i18n_scope.py` | 2 |
| `tools/new_plugin.py` | 2 |
| `core/builtin_plugins.py` | 1 |
| `core/problems.py` | 1 |
| `core/search.py` | 1 |
| `tools/feature_inventory.py` | 1 |

## 处理策略

1. 高价值：与安全/崩溃/数据丢失相关的 TODO 优先（P0/P1）；
2. 体验类：随对应模块迭代顺手清理；
3. 长期项：转为 GitHub Issue（带 `TODO` 标签），每季度复核；
4. 禁止新代码提交裸 TODO（评审时要求带 issue 链接或负责人）。
