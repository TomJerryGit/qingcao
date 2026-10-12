# 青草编辑器 (QingCao Editor)

> 青草枯荣，野火重生。

轻量 · 可扩展的跨平台代码编辑器，基于 **PyQt5** + **QScintilla** 构建。

当前版本：**2.1.0**（`version.py` 为唯一权威来源）

---

## 这份文档是什么

本目录是项目的**开发文档**，由 MkDocs 构建。它与仓库里的
[README.md](https://github.com/qingcao-editor/qingcao) 分工不同：

| 文档 | 面向 | 内容 |
|---|---|---|
| README | 首次接触项目的人 | 特性概览、安装、快捷键速查 |
| 本目录 | 使用者与插件作者 | 详细指南、插件 API、FAQ |

## 快速导航

- [快速开始](quickstart.md) — 从零跑起来
- [功能说明](features.md) — 各模块能力与**当前的已知限制**
- [快捷键](shortcuts.md) — 完整键位表
- [插件开发](plugin_dev.md) — 写一个插件
- [API 文档](api/index.md) — `PluginAPI` 接口参考
- [贡献指南](contributing.md) — 提 PR 前该做什么
- [常见问题](faq.md) — 踩坑与排查

## 关于"已知限制"

本项目的 README 曾出现"文档宣称但实现未接线"的情况（例如插件权限
沙箱、热重载、国际化）。修复后这些功能**已真实可用**，但仍有两处
必须明确告知：

1. **插件没有进程级隔离** —— `permissions` 是 API 边界门控，不是
   安全沙箱。只应安装可信来源的插件。
2. **插件市场后端未部署** —— 界面可用，但在线安装不可用。

详见 [功能说明](features.md#已知限制) 与 [常见问题](faq.md)。

## 系统要求

| 项目 | 要求 |
|---|---|
| Python | 3.8 ~ 3.11（推荐 3.11） |
| 操作系统 | Windows 10+ / Ubuntu 20.04+ / macOS 10.14+ |
| 内存 | 至少 4 GB |
| 磁盘 | 至少 500 MB |

> ⚠️ Python 3.13+ 可能缺少 PyQt5 wheel，建议使用 3.8 ~ 3.11。

## 许可证

MIT License，Copyright (c) 2024-2025 hedongwei
