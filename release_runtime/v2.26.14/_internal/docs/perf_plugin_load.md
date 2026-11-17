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

## 首帧/QSS 与插件激活拆解（v2.25 续）

cProfile 热点：
- `processEvents` 1.08s（首帧布局/绘制/QSS polish，占比最大）；
- `plugin_loader.load_deferred` 0.535s，其中 **`_activate_plugin` 内 `import requests` 0.388s**；
- `_restore_session` 0.295s（窗口构造期恢复会话）。

优化：
- **AI 插件 requests 惰性检测**：`_requests_ok()` 改用 `importlib.util.find_spec`，激活时不再真正 import requests（省约 0.4s）；
- 复核：plugins_fully_ready 1.754→**1.583s**；open_50mb 1.844s（本轮机器波动，仍远低于 8s 硬上限）。

后续（未做，需谨慎）：
- 非关键面板（perf_monitor/plugins_panel）延迟到首帧后构造：测试有直接属性访问，需先加 `__getattr__` 惰性代理；
- 会话恢复延后到首帧后（需保证快速关闭时仍保存）。
