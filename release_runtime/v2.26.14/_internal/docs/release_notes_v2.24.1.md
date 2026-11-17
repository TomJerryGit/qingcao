# QingCao Editor v2.24.1 发布说明

> 2026-11-10 · 上一版本：v2.24.0

## UX
- **首启向导**：3 步（语言 / 主题 / 插件市场），首次启动展示一次；
- **菜单默认快捷键兜底**：覆盖率 30.9% → **53.9%**（不覆盖已有快捷键）；
- **设置基础/高级分层**：默认隐藏“高级”分类，勾选「显示高级设置」后显示并持久化。

## i18n（ja/ko）
- 批次 4 完成 180 条翻译：覆盖率 22.4% → **51.6%**，CI 门禁 15% → **50%**；
- 工作清单与应用流水线：`tools/i18n_batch_worklist.py` / `tools/i18n_apply_batch.py`。

## 性能
- **视口加载默认开启**：>32MB 文件自动视口优先（首次可视 16×），`QINGCAO_VIEWPORT_LOAD=0` 可禁用；
- 搜索/撤销/脏标记回归通过。

## 文档
- `docs/ux_shortcuts.md`、`docs/i18n_batch4_pipeline.md`、`docs/perf_viewport_prototype.md`。
