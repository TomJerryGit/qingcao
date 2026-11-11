# UX 发现性：命令面板最近使用 + 菜单搜索（v2.24.x）

## 已实现
- **最近使用排序修复**：原 `_sort_by_usage` 用标题作 key，与历史 `action:` key 不一致 → 排序永远无效；现统一 `_usage_key`；
- **跨会话持久化**：使用历史写入 `QSettings("QingCao","CommandPalette")`，最多 500 条，重启后仍按最近/频率排序；
- **菜单搜索**：`Ctrl+Shift+P` 命令面板加载全部菜单动作/插件命令，输入即可模糊搜索并执行（相当于菜单内搜索）；
- 测试：`tests/test_v224_palette_recent.py`（排序 key、持久化回环）。

## 后续
- 命令面板分类筛选/最近文件合并；
- 菜单栏内嵌搜索框（可选）。

## 市场深化（v2.25）

- 排序新增「按社区评分」（读取签名 ratings.json 聚合值）；
- 插件卡片支持**双击**或**回车**直接打开详情，详情内可评分；
- 测试：`tests/test_v225_market_deepening.py`。

## 动态快捷键参考（v2.25）

- 帮助 → 快捷键参考（`F1`）：搜索框过滤命令/快捷键/菜单路径；
- 从真实 `menuBar` 递归收集（含未绑定动作），不再使用硬编码列表；
- 快捷键覆盖率 54.5%（97/178）；测试：`tests/test_v225_shortcuts_dialog.py`。

## 发现性二批（v2.25）

- 工具栏按钮 tooltip：`apply_toolbar_tooltips()` 自动附加默认快捷键（如 `保存 (Ctrl+S)`）；
- 命令面板：无搜索词且有历史时显示「── 最近使用 ──」「── 全部 ──」分组标题；方向键导航自动跳过标题；
- 测试：`tests/test_v225_discoverability2.py`。
