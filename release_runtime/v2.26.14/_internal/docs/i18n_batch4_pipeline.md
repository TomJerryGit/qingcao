# ja/ko 批次 4：工作清单 + 自动翻译流水线

## 流程
1. 生成清单（按源码使用频率排序，未翻译语料）：
   ```powershell
   python tools/i18n_batch_worklist.py --limit 180
   ```
   输出 `locale/_batch4_worklist.tsv`：`zh / ja / ko / freq`（ja、ko 留空）。
2. 翻译：逐行填写 ja/ko（人工或翻译模型），保持占位符 `{}` / `%s` / `%d` 数量一致。
3. 校验 + 写入：
   ```powershell
   python tools/i18n_apply_batch.py locale/_batch4_worklist.tsv --check
   python tools/i18n_apply_batch.py locale/_batch4_worklist.tsv
   ```
4. 覆盖率：
   ```powershell
   python tools/i18n_coverage.py --check --min-corpus 25 --lang ja_JP
   python tools/i18n_coverage.py --check --min-corpus 25 --lang ko_KR
   ```
   阶梯：15% → 25% → 50%；每次只提升门禁到实际达成值。

## 质量约束
- 纯 ASCII 术语可保持原样；含中文的 key 严禁 ja/ko 值等于原中文；
- 占位符数量必须一致（工具会拒绝）；
- 不修改 `locale/zh_CN/strings.json`（唯一中文源）。
