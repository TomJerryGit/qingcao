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
