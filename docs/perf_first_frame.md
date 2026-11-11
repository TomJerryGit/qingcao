# 首帧专项：面板惰性代理 + 非关键面板延后（v2.25）

## 改动
- `PanelRegistryMixin.__getattr__`：未预置 `None` 的惰性面板（terminal/lsp/task 等）首次属性访问时自动构造；
- 启动默认面板缩减为 `dir_tree` + `gsearch`（大屏），`plugins_panel` / `perf_monitor` 改为**首帧后 50ms 预热**构造并显示；
- `_prewarm_secondary_panels()` 独立方法，便于测试/手动触发。

## 修复（联调时发现）
- raw/历史按钮此前误插入 `TerminalTab`（单命令终端），导致 TerminalPanel 构造时报
  `'TerminalTab' object has no attribute 'set_raw_mode'`；
- 已把这些按钮/屏幕渲染/鼠标回流全部移到 `PtyTerminalTab`，并回滚 `TerminalTab`。

## 验证
- 终端 P1–P6 测试 + 惰性面板测试 + TestLazyPanels：24/24 通过；
- `TerminalPanel` 与 `PtyTerminalTab` 可正常构造（raw/history 按钮就位）。

## 后续
- 会话恢复/保存对延迟面板的兼容已由 `_prewarm` 的 50ms 与恢复 200ms 顺序保证；
- 可继续压缩首帧 QSS polish（processEvents 主导）。

## QSS polish 专项（v2.25 续）

实测拆解：
- 全局 QSS 对 MainWindow 构造的影响：**0.275s（无 QSS） vs 0.347s（有 QSS，+0.072s）**；
- `load_theme`（首次 apply_qss）0.141s；`apply_qss` 重复调用已被 ThemeLoader 幂等跳过（0.000s）；
- `notify_widgets` 0.063s → 加批量重绘控制后 `apply_startup_theme` **0.068s → 0.050s**；
- 启动主要耗时仍在首帧 `processEvents`（绘制/polish），QSS 解析本身占比不高。

优化：
- `apply_startup_theme` 在 `notify_widgets`/`adapt_widget_styles` 期间 `setUpdatesEnabled(False)`，完成后恢复，减少中间重绘。

结论：QSS 专项收益已接近边际，不建议再拆分 QSS；后续优先减少首帧控件数量（面板延迟）或绘制范围。
