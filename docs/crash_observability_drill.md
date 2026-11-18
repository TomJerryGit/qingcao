# 崩溃可观测性演练（Sprint 1 / task-19）

日期：2026-11-18

## 步骤

1. `python tools/crash_capture.py --enable data/crash_dumps_drill`；
2. 子进程受控崩溃：
   - `python -c "import ctypes; ctypes.string_at(0)"`
   - `python -c "import os; os.abort()"`
3. 等待 10–15 秒检查 `.dmp`；
4. `python tools/crash_capture.py --disable`；
5. 检查 HKCU LocalDumps 键已删除。

## 结果

| 项 | 结果 |
|---|---|
| 启用/禁用注册表 | ✅ 正常 |
| 清理残留 | ✅ `key_removed=True` |
| dump 生成 | ❌ 0 个（两次受控崩溃均未产生） |

## 结论与后续

- 开关生命周期无副作用，可作为运维工具；
- 当前环境 WER LocalDumps **未实际产生 dump**，可能与本机 WER 策略/服务有关；
- 因此不能依赖 WER 作为唯一崩溃取证手段；后续需评估：
  - Windows Error Reporting 服务/策略是否禁用；
  - 使用 ProcDump/自建 faulthandler/ETW 作为补充；
- 在拿到真实 dump 前，原生崩溃根因仍只能靠日志/复跑定位。

## 补充结论（2026-11-18）

- 失败根因：`WerSvc` 服务 **Stopped / Disabled**，当前会话无管理员权限无法启动（Access denied）；
- 引入 **ProcDump**（Sysinternals 官方）作为替代：
  - 工具：`tools/procdump_capture.py`
  - 二进制目录：`tools/procdump/`（不提交仓库，见 .gitignore）
- 演练结果：
  - `procdump64 -accepteula -ma -e 1 -x data/crash_dumps_drill python -c "import ctypes; ctypes.CFUNCTYPE(None)(0)()"`
  - 成功生成 **35.88MB** dump：`data/crash_dumps_drill/python.exe_261118_161542.dmp`
- 后续：CI/本地崩溃复现优先用 ProcDump；WER 需管理员启用服务后再评估。
