# 评分运营与插件模板采用（P4）

## 评分运营

1. **收集**：Issue 标签 `plugin-rating`（模板见 `.github/ISSUE_TEMPLATE/`），由 `tools/collect_issue_ratings.py` 幂等合并；
2. **汇总**：`python tools/ratings_report.py` → `docs/ratings_report.md`（本地星级 + 社区人数/均分）；
3. **展示**：市场卡片/详情显示平均分与人数；评分筛选支持 `4★+`/`3★+`/无评分；
4. **目标**：3 个月内社区评分样本 ≥50、≥3 位真实用户；当前本地 16 条（种子），社区 0。

## 插件模板采用

```powershell
python tools/new_plugin.py --name hello_tool --display-name "Hello" \
  --permissions editor_read,dialog --points settings,status
```

- 生成 `plugins/<name>/plugin.json` + `__init__.py`，默认通过 conformance 清单契约；
- 采用验证：`tests/test_v226_ecosystem.py::test_plugin_scaffold_generates_importable_plugin`；
- 新插件建议以 `demo` 为模板、`my_plugin` 仅作脚手架占位（默认禁用）。

## 后续

- 种子评分需标注“维护者种子”以免误导用户；
- 社区评分并入 registry 后由 `publish_registry` 发布。
