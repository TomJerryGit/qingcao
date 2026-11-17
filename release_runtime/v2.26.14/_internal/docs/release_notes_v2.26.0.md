# QingCao Editor v2.26.0 发布说明

> 2026-11-13 · 上一版本：v2.25.3

## 插件安全与沙箱（P1）
- **B2.2 远程面板**：新增 text / markdown 面板类型；todo_panel、markdown_preview、logtail 加入隔离灰度（隔离集合 7 个：demo/wordcount/json_formatter/todo_panel/markdown_preview/logtail/sandbox_demo）；
- **spell_check**：标准沙箱契约复核（manifest sandbox + worker diagnostics/menu/ignore 方法）；
- **插件拆分**：ai_assistant 入口 1,242→904（Ollama/内联 mixin）；python_debugger 661→589（guards mixin）。

## P0（v2.25.3 已含）
- git 子命令白名单 + 参数数组 + 15s 超时/1MB 输出上限；
- AI 隐私模式（禁网）+ 取消守卫 + 配置页开关。

## 验证
- 隔离 UI（含 todo/markdown/logtail）：6/6；
- AI 超时/取消、插件规范、架构门禁通过。
