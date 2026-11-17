# 崩溃根因分析：Windows fatal exception 0x8001010d（v2.22 P1）

> 日期：2026-11-05 · 严重级：P1（启动期崩溃）
> 关联转储：`logs/crash_dump_11256.log`、`logs/crash_dump_1116.log`

## 1. 现象

应用启动后（v2.20.x，2026-11-02）记录到 5 个崩溃转储，其中两个有内容：

### A. 后台线程（crash_dump_11256）
```
Windows fatal exception: code 0x8001010d
Thread 0x1310:
  socket.getaddrinfo
  urllib3 ... requests ...
  core/updater.py line 44 in _check
  threading.Thread.run
Current thread (main): main.py main()
```

### B. 主线程（crash_dump_1116）
```
Windows fatal exception: code 0x8001010d
Current thread:
  ui/main_window.py line 2572 in _show_daily_tip
  main.py main()
```

## 2. 根因判断

0x8001010d = `RPC_E_CANTCALLOUT_ININPUTSYNCCALL`（输入同步调用期间禁止向外 RPC/COM 调用）。

启动时序（修复前）：
1. `main.py` 立即 `UpdateChecker.check_async()` → **后台 threading.Thread** 调 `requests.get` → `getaddrinfo`（Windows 网络栈在解析时可能进入 COM/RPC）；
2. 3 秒后 `QTimer.singleShot(3000, _show_daily_tip)` 弹出**模态**对话框（QMessageBox）；
3. 两者并发 → 模态输入同步上下文中后台解析触发 RPC 限制 → Windows fatal exception，faulthandler 捕获后进程终止。

结论：**不是业务逻辑错误，而是"后台网络 DNS 与模态对话框启动期并发"的时序缺陷**。

## 3. 修复（v2.22）

| 修复 | 说明 |
|---|---|
| 空闲延迟启动 | `UpdateChecker.check_when_idle()`：默认 15s 后启动，若存在模态窗口（`QApplication.activeModalWidget()`）每 3s 重试，最多 20 次 |
| 模态避让 | 更新检查只在无模态框时发起 |
| 取消机制 | `cancel()` + `_cancel` 标记；请求前后检查，退出/关闭可取消 |
| 超时收紧 | `requests.get(..., timeout=(3.05, 10))`；urllib 回退同样 10s |
| 阶段日志 | 记录"开始请求/收到响应/已取消/延后"便于下次定位 |
| 网络审计 | `tools/audit_network_threads.py`（AST）要求所有 requests/urlopen 显式 timeout，0 违规 |

## 4. 验证

- 单元测试：超时参数、异常上报、取消、模态延迟逻辑、审计 0 违规；
- 分片全量回归全绿；
- 启动冒烟：模拟模态窗口存在时更新检查不启动，关闭后延迟启动。

## 5. 残余风险与后续（P2）

- 更新检查仍使用 Python 线程 + requests；根治可迁移到 `QNetworkAccessManager`（主线程异步，无 COM 线程问题）；
- 每日技巧仍为模态对话框；可改为非模态侧边提示；
- 若再出现同类转储，按本文"阶段日志"定位并考虑禁用启动期自动检查。

## 6. 结论

启动期崩溃的**可复现时序已被消除**（后台 DNS 与模态框不再并发），并加入回归测试与超时审计。
