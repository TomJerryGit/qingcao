# 青草编辑器 v2.14.1 发布说明

> 发布日期：2026-10-29 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.14.1`）
> 类型：**缺陷修复版**（建议 v2.14.0 用户升级）

---

## 一句话概括

v2.14.1 修复 v2.14.0 中 AI 助手插件激活错误，并彻底修复插件面板
主题适配（工具栏/表头/搜索框/列表随主题正确切换，浅色对比度恢复）。

---

## 修复内容

### AI 助手插件错误（重要）

- 根因：`_requests_ok()` 惰性依赖检查自递归 → RecursionError；
- 修复：返回 `_REQUESTS_OK`，并修正 `refresh_theme` 插入位置；
- 验证：打包版插件报告 `ai_assistant 状态=ACTIVATED`。

### 插件面板主题

- 修复主题应用顺序：先 `adapt_widget_styles`，后 `notify_widgets`；
- 面板按主题类型直接生成 QSS（light / dark / high_contrast）；
- 工具栏、表头、搜索框、下拉列表、树列表统一配色；
- 修复浅色主题文字接近白色的问题（对比度恢复正常）。

### 其他

- 欢迎页与窗口调色板随主题同步；
- 新增 GUI 主题冒烟工具与截图对比：
  `tools/smoke_plugin_theme.py`，
  产物 `docs/smoke_plugin_theme_*.png`、`docs/smoke_plugin_panel_*.png`。

---

## 验证

- 分片并行全量通过；ruff 0；`tools/check_version` 通过；
- 真实 GUI 冒烟：浅色/深色截图对比（平均像素差异 > 600）。

---

## 升级注意事项

1. v2.14.0 → v2.14.1 无数据迁移；
2. 若插件面板仍显示旧样式，重启应用即可；
3. 本版本仅为修复，不包含新功能。
