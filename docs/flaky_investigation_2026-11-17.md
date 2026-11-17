# 原生崩溃 0xC0000005 根因排查（2026-11-17）

## 现象

- `data/ci_flaky_history.jsonl`：11 起事件，崩溃码 `3221225477`（0xC0000005 访问冲突）；
- 发生在**合并分片**；逐文件复跑全部通过；11-16 后无新增事件。

## 本次排查

1. 启用 Windows WER LocalDumps（python.exe，MiniDumpNormal）→ `data/crash_dumps`；
2. 全量分片 1 次：通过，无 dump；
3. 定向复跑 part1（77 文件，排序轮转分片）**4 次**：全部通过，无 dump；
4. 未复现，未取得崩溃栈；已清理 WER 注册表项，避免长期副作用。

## 结论

- 根因**仍未定位**；更可能依赖**并行分片/资源/析构顺序**而非单文件；
- 现有缓解有效：逐文件复跑门禁、崩溃历史、crash artifact 上传；
- 后续若复现：重新启用 WER dump 并用 `cdb -z <dump> -c "!analyze -v; q"` 分析，或缩小并行度复现。

## 复现脚本（可选）

```powershell
# 启用 dump
New-Item "HKCU:\Software\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe" -Force
# DumpFolder / DumpType=1 / DumpCount=3，然后运行
python tools/run_tests_sharded.py --shards 3 --retries 1 --localize --parallel
```
