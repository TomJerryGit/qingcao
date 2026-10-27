# 测试稳定性说明

## 背景

全量 offscreen 测试曾出现偶发 `0xC0000005` 崩溃（复跑通过），
与 PyQt5 off-screen 平台窗口销毁时序有关；已修复主题事件过滤器
teardown（v2.11.0），并保留防御性 `sip.isdeleted` 检查。

## 检查方法

```powershell
# 核心子集快速重复（开发时）
python tools/verify_test_stability.py --quick --runs 3

# 全量重复（发版前，耗时较长）
python tools/verify_test_stability.py --runs 2
```

- 返回 0：所有轮次通过；
- 返回 1：存在失败或崩溃（CRASH 行会标注）。

## 已知偶发点

| 现象 | 触发条件 | 处理 |
|---|---|---|
| 0xC0000005 崩溃 | offscreen + 多窗口连续创建/销毁 | 重跑；若稳定复现请附 `--runs 3` 输出 |
| Qt 字体警告 | PyQt5 未附带字体目录 | 无害（offscreen） |
| 测试出现 `UnicodeDecodeError` 警告 | 子进程 GBK 解码 | 无害（线程警告） |

## CI 策略

- 主门禁：Python 3.11 全量测试；
- Python 3.12 为**软矩阵**：解释器不可用或测试未过时静默跳过，
  不阻塞主门禁（见 `test.yml` 的 `test-py312` job）。

## 分片 + 重试 + 崩溃定位（v2.11.2 起）

```powershell
# 分 2 片运行，失败自动重试，失败片逐文件定位
python tools/run_tests_sharded.py --shards 2 --retries 1 --localize
```

- 输出在 `data/test_shards/part*.log`，崩溃文件日志为 `crashed_*.log`；
- CI 已改为该方式（见 `test.yml` 的 Full test suite 步骤）。

### 重要：QSettings 隔离

测试会通过 MainWindow 保存布局/面板可见性。`tests/conftest.py` 中的
`_isolated_qsettings`（session 级 autouse）把 QSettings 重定向到临时目录：
- 消除**测试顺序敏感**（分片运行时暴露）；
- 避免污染用户真实配置。
