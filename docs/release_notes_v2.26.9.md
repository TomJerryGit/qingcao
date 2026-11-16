# QingCao Editor v2.26.9 发布说明

> 2026-11-16 · 上一版本：v2.26.8

## B3 调试器宿主服务（D1–D7）
- `core/debug_service.py`：RPC（start/stop/continue/step/set_breakpoints/locals/stack/eval）+ 事件；
- 真实 `DebugSession` 启停、无孤儿清理、shutdown；
- 断点/单步/变量/栈真实脚本端到端（processEvents 轮询）；
- 宿主调试面板（栈/变量）；`PluginAPI.debug_*`；
- broker `debug_*` + `python_debugger` 隔离分支（隔离激活通过）；
- 故障注入：factory/stop 失败、error 事件安全清理。

## 说明
- 默认 `QINGCAO_DEBUGGER_HOST=1` **关闭**，可回退进程内路径；
- 真实断点/变量 e2e 已通过；隔离插件 UI 级自动化仍待后续。

## 验证
- 调试器相关 19/19；全量测试 3 片通过；ruff/format 全绿。
