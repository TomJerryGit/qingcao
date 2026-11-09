# 终端 PTY 依赖验证（v2.23 D4）

> 结论：**pywinpty 3.1.2 可用**，最小交互会话验证通过（cmd echo），可进入集成阶段。

## 1. 依赖

- `pywinpty>=3.0.0; sys_platform == "win32"`（requirements 已加入）；
- Windows 10 1809+ 使用 ConPTY 后端；
- 未安装/非 Windows：`HAS_WINPTY=False`，终端继续使用单命令模式（降级安全）。

## 2. API 封装

`ui/pty_session.py::PtySession`：
- `PtyProcess.spawn(argv, cwd, dimensions)` 启动持续 shell；
- `read()` 为阻塞调用 → 后台读线程 + 条件变量提供非阻塞 `wait_for/read_available`；
- `write()` 发送输入；`close()` 强制终止并释放。

## 3. 验证结果

| 项 | 结果 |
|---|---|
| pywinpty 版本 | 3.1.2 |
| 最小会话（cmd.exe） | ✅ `echo qc-pty-ok` 回显成功 |
| 进程存活 | ✅ |
| 打包资源收集 | `collect_all("winpty")` 纳入 Datas/Binaries |

验证命令：`python tools/verify_pty.py`。

## 4. 打包

`build.py` 新增 `collect_winpty_assets()`：
- Datas：包内数据；
- Binaries：`winpty.dll` / `winpty-agent.exe` 等；
- 已在 spec 中注入 `binaries=`。

## 5. 后续（集成阶段）

1. `TerminalPanel` 增加「交互模式」标签（PTY），保留单命令模式；
2. 输入框回显由 PTY 驱动；Ctrl+C 发送 `\x03`；
3. 面板尺寸变化 → `setwinsize`；
4. 关闭标签强制 `terminate(force=True)`；
5. 非 Windows/缺少依赖自动回退。

## 6. 风险

- ConPTY 在部分精简系统不可用 → 捕获异常回退；
- 阻塞 read 的读线程需随会话关闭退出（daemon + close）；
- 打包体积增加（DLL/agent，约数百 KB）。
