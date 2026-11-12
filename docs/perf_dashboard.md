# 性能看板（v3.0 P0）

## 组成

- 数据：`data/perf_history.jsonl`（CI 性能门禁每次运行写入；仓库保留最近 150 条）；
- 生成：`tools/perf_dashboard.py`（零依赖，内联 SVG）；
- 产物：`docs/perf_dashboard.html`（单文件，可直接打开/托管）；
- 首页：`docs/index.html`（入口链接）；
- 部署：`.github/workflows/pages.yml`（每日 05:00 UTC + 手动，GitHub Pages）。

## 指标与阈值

| 指标 | 含义 | 硬上限 |
|---|---|---|
| mainwindow | 主窗口构造 | 1.5s |
| plugin_ready_after | 插件就绪（累计） | 3.0s |
| open_50mb | 打开 50MB 文件 | 8.0s |
| theme_reapply | 主题重复应用 | 0.5s |

## 使用

```powershell
python tools/perf_dashboard.py                     # 用仓库历史生成
python tools/perf_dashboard.py --extra-history D:\actions-runner\perf_history.jsonl --limit 120
```

## Pages 启用（需管理员手工一次）

1. GitHub → Settings → Pages → Source 选择 **GitHub Actions**；
2. 运行 `Perf Dashboard Pages` 工作流（或等待每日定时）；
3. 访问 `https://<owner>.github.io/qingcao/`（性能看板在 `/perf_dashboard.html`）。

## 维护

- 提交/定期更新 `data/perf_history.jsonl`（来自 CI runner 历史 `D:\actions-runner\perf_history.jsonl`）；
- 阈值变更需同步 `tools/perf_dashboard.py` 与 `tools/bench_optimization.py`；
- 看板为静态 HTML，无外部网络依赖。
