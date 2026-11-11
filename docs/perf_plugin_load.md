# 启动 / 插件加载性能专项（v2.25）

## 剖析结论（cProfile，真实启动序列）

- 总耗时 2.06s 中 **processEvents 占 1.08s（52%）**，`builtins.exec` 0.68s；
- 各插件 `_load_plugin` 实测：`ai_assistant 0.111s`（已延后 600ms），其余 9 个均 **≤0.003s**；
- 因此 plugin_ready 的耗时**主要不是插件代码**，而是首帧期间的 Qt 事件/布局处理 + 100ms 定时器延迟。

## 优化

- 插件加载定时器 **100ms → 50ms**：保留首帧绘制优先，同时减少就绪等待；
- （前序）启动主题幂等缓存：重复 `apply_startup_theme` 近 0。

## 基准结果（auto 容差）

| 指标 | 优化前 | 优化后 | 硬上限 |
|---|---|---|---|
| mainwindow | 0.909s | **0.632s** | 1.5s ✅ |
| plugin_ready_after | 2.296s | **0.846s** | 3.0s ✅ |
| plugins_fully_ready | 2.793s | **1.754s** | — |
| theme_reapply | 0.379s | **0.000s** | — |
| open_50mb | 5.250s | **3.120s** | 8.0s ✅ |

## 后续

- processEvents 主导 → 下一步可拆解首帧控件 QSS/polish 成本、延迟非关键面板构造；
- 插件代码本身已足够轻（≤0.11s），不建议再压。
