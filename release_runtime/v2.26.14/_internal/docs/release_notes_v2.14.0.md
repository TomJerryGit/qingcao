# 青草编辑器 v2.14.0 发布说明

> 发布日期：2026-10-29 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.14.0`）
> 主题：**插件全面提振**（分析 → 性能 → UI/主题 → 安全 → 市场）

---

## 一句话概括

v2.14.0 对全部 13 个插件做了系统性分析与提升：导入性能实测
（ai_assistant 1.8ms / python_debugger 8.9ms）、插件面板主题统一适配、
调试器权限收敛、wordcount 沙箱试点、插件市场元数据完备并纳入 CI。

---

## 插件分析（详见 `docs/plugin_analysis_v2.13.md`）

- 12→13 个插件完成 AST 级结构扫描（LOC/扩展点/重依赖/QSS/线程/IO/网络）；
- 建立插件导入性能基准（`tools/bench_plugins.py`），修正预热缺陷后的真实数据：
  - ai_assistant **1.8ms**、python_debugger **8.9ms**、其余 **0.3~0.5ms**；
- 安全审计：python_debugger review（eval/compile 为调试器固有）；其余 pass/warn 均属预期。

## 插件功能与 UI

- 宿主启动主题路径统一递归适配 → **插件面板启动即跟随主题**；
- wordcount/todo_panel/logtail/markdown_preview/ai_assistant 实现
  `refresh_theme(theme)` 精准刷新（含 ai 子控件内联 QSS）；
- ai_assistant 可选依赖 `requests` 改为惰性 → 消除约 0.9s 潜在导入开销。

## 性能与安全

- 插件性能预算门禁接入 CI：ai_assistant ≤150ms、python_debugger ≤60ms、
  其余 ≤30ms（×2 容差），真正防回退；
- python_debugger manifest 补充 `process` 权限；eval 表达式限长 4000 字符。

## 插件沙箱

- 沙箱协议 `status_text(text)` 支持传入当前文本；
- 新增 `plugins/wordcount_sandbox` 试点：子进程计算并回报「字数/字符/行」，
  保留原 wordcount 进程内实现（无功能回退）。

## 插件市场

- 全部 13 个插件补齐 `homepage`/`keywords`，并具备 `category`/`license`/`description`；
- `tools/check_plugin_market.py --strict` 纳入 CI 校验。

## 测试

- 分片并行全量通过（105+ 测试文件 → 2 片）；ruff 0；check_version 通过。

## 升级注意事项

1. v2.13.0 → v2.14.0 无数据迁移、无接口破坏；
2. 新增沙箱试点插件默认启用，可在插件面板禁用；
3. 插件市场字段为后续在线市场预留，不影响加载。

## 已知限制

- python_debugger 的 eval/compile 仍属调试器必要能力（已限长与权限声明）；
- 插件在线市场/安装仍需服务端与安全审查；
- 跨屏 DPI 与系统高对比度极端组合仍建议真机复核。
