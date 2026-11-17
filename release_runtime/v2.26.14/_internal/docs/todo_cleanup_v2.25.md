# TODO/FIXME 清理结论（v2.25.1 复核）

- 原统计“45 处”包含 **功能名/字符串**（如 `todo_panel`、`TODO 面板`、正则 `TODO|FIXME`），并非待办；
- 真实注释标记（`# TODO` / `# FIXME`）复核结果：**0 处**；
- 已修正 1 处易误读注释：`core/builtin_plugins.py` 中 `# TODO 面板` → `# 待办面板`。

## 后续规范

1. 新增 TODO 必须使用 `# TODO(owner): 描述` 或关联 issue；
2. CI 不再以字符串计数作为 TODO 债务指标；改用 `tools/crash_triage` 与 issue 看板；
3. 每迭代复核 `# TODO`/`# FIXME` 注释（当前为 0）。
