# QingCao Editor v2.24.5 发布说明

> 2026-11-11 · 上一版本：v2.24.4

## 修复（重要）
- **终端面板崩溃修复**：P1–P6 的 raw/历史按钮此前误挂到 `TerminalTab`（单命令终端），导致 TerminalPanel 构造失败；已全部移入 `PtyTerminalTab`，终端面板可正常打开，raw/history/屏幕渲染/鼠标回流均就位。

## UX / 市场
- 市场深化：按社区评分排序；插件卡片**双击/回车**打开详情；
- 动态快捷键参考（F1，可搜索，含未绑定项）；
- 工具栏 tooltip 补快捷键；命令面板「最近使用/全部」分组标题 + 分类筛选；
- 真实评分聚合上线（16 插件，average=5.0 count=1，签名 ratings.json）。

## 性能
- 启动主题幂等、插件加载 100→50ms：plugin_ready **2.296→0.846s**、mainwindow 0.632s、open_50mb 3.1s；
- AI 插件 requests 惰性检测（省 ~0.4s）；
- 面板惰性属性代理 + 非关键面板首帧后 50ms 预热；
- QSS 批量适配关闭重绘（startup_theme 0.068→0.050s）。

## 验证
- 定向测试（终端 P1–P6、UX、市场、性能、主题）全部通过；
- 发布资产含 ZIP + SHA256 + Ed25519 `.sig`。
