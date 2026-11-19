# 崩溃取证使用说明（Sprint 1）

## 自动附加

```powershell
# 启动目标并等待崩溃
python tools/crash_attach.py --dump-dir data/crashes -- python -c "..."

# 附加已运行进程
python tools/crash_attach.py --dump-dir data/crashes --pid 1234
```

- 依赖：`tools/procdump/procdump64.exe`（Sysinternals，已 gitignore）；
- dump 默认 `data/crashes`；
- 受控验证：2026-11-19 生成 35.43MB dump。

## 分析

```powershell
cdb -z <dump> -c "!analyze -v; q"
```

## 边界

- ProcDump 仅取证，不自动上传；
- 用户数据/隐私不入 dump 报告，导出前人工确认。
