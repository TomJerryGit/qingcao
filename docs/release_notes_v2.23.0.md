# 青草编辑器 v2.23.0 发布说明

> 发布日期：2026-11-09 · 版本：2.23.0
> 主题：**架构拆分 / 终端 PTY / CI 可定位性**

## 重构（巨石拆分）
| 原文件 | 原行数 | 现状 |
|---|---|---|
| core/editor.py | 3920 | 1818（common + 6 Mixin） |
| ui/main_window.py | 3268 | 244（common + 5 Mixin） |
| ui/plugin_store.py | 2964 | 1120（client/detail） |
| app/plugins.py | 2553 | 217（plugin_api） |
| infrastructure/theme_loader.py | 2355 | 1314（theme_model） |

最大单文件 3920 → 1818 行；对外 API 通过 re-export 保持。

## 新增
- 终端交互 PTY 模式（PTY 按钮、Ctrl+C 中断、尺寸同步、无 pywinpty 自动回退）；
- CI flaky 面包屑 + 频率门禁（last_stage.json、近 7 天 >3 降并行建议）；
- 应用内反馈入口（本机 JSONL）、终端命令历史、mmap 埋点 target、日韩试点语言包；
- 网络超时审计 + 更新检查 QNetworkAccessManager 迁移。

## 验证
- 152 个测试文件分片并行全绿；CI test/lint 双绿；
- 打包产物含 pywinpty 资源（_internal/winpty）。

## 升级
v2.22.0 → v2.23.0 无数据迁移；PTY 不可用时自动回退单命令模式。
