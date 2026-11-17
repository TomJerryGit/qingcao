# CI Qt 原生崩溃排查手册（v2.17.x）

## 1. 证据采集（已自动化）

| 来源 | 位置 |
|---|---|
| faulthandler（Python 层崩溃栈） | `logs/crash_dump_<pid>.log`（应用启动即启用） |
| Windows 错误报告 WER 本地转储 | `D:\actions-runner\crash_dumps\python.exe\*.dmp` |
| CI 测试日志 | `D:\actions-runner\test.log`、`data/test_shards/part*.log` |

CI 已加 best-effort 步骤（需管理员权限写 HKLM）：

```powershell
python tools/enable_crash_dumps.py --folder D:\actions-runner\crash_dumps
python tools/enable_crash_dumps.py --check
```

应用侧 faulthandler：`main.py::setup_logging()` 写入 `logs/crash_dump_<pid>.log`。

## 2. 复现与定位

1. 确认崩溃点：CI `test.log` 中 `[shard partN] rc=3221225477`（0xC0000005）
   或 faulthandler 栈；
2. 单独重跑对应分片/测试文件（`--retries 1` 排除偶发）；
3. 用 WinDbg/cdb 打开 `.dmp`：

```
cdb -z python.exe\*.dmp
.symfix
.reload
!analyze -v
~*k
```

4. 关键线索：
   - 栈顶是否在 `Qt5*.dll` / `qwindows.dll` / `Qsci*`；
   - 是否由已销毁控件（`deleteLater` 后事件）触发；
   - 是否与字体/主题/高 DPI 相关（对照近期改动）。

## 3. 常见诱因（本项目历史）

- 主题事件过滤器在窗口关闭后仍回调（已修：`closeEvent` 移除 + `sip.isdeleted`）；
- 异步加载 timer 在标签销毁后触发（已修：`abort_loading`）；
- offscreen 平台下真实模态框（测试用 monkeypatch 规避）；
- 广播消息回环导致读取饥饿（已修：ACK 不中继 + 读取上限）。

## 4. 防回归

- CI 全量测试重试 1→2；
- 新增长期运行/关闭路径测试时，显式清理 QTimer/QThread/filter；
- 性能/主题相关改动必须跑 `theme_e2e_screenshots.py --check`。
