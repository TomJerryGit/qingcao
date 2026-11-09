# 性能门禁收紧（v2.24 W3）

## 变更
| 项 | 旧 | 新 |
|---|---|---|
| 有效容差 | 最低 5×，且 `auto` 最高可放大到 20× | 最低 **2×**，最高 **4×** |
| 硬上限 | 无 | mainwindow ≤1.5s、plugin_ready ≤3.0s、open_50mb ≤8.0s、session_save ≤1.0s、theme_notify ≤2.0s |
| CI 参数 | `--auto --factor 3.0` | 不变（实际生效 3–4×） |

## 设计说明
- CI 自托管 Runner 负载波动大：历史 open_50mb 在 1.28–4.97s 间波动，**绝对 3.0s 硬阈值会误报**；
- 采用"2×–4× 容差 + 分级硬上限"：既能拦截 2–4 倍级退化，又不因瞬时负载误报；
- open_50mb 的 3.0s 目标由视口加载原型（`docs/perf_viewport_prototype.md`）逐步达成后再收紧硬上限。

## 自检
```powershell
python tools/bench_optimization.py --check --auto --factor 3.0
```
本地通过（open_50mb 3.09s < 硬上限 8s；各指标阈值内）。
