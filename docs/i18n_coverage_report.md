# i18n 覆盖率报告（v2.19 P1-2）

| 指标 | 数值 |
|---|---|
| 模板条目（zh_CN） | 5218 |
| 英文映射条目（en_US） | 161 |
| 模板覆盖率 | 1.9% |
| 重点 UI 覆盖率 | 13.6% |

## 重点文件

| 文件 | 中文串 | 已翻译 | 覆盖率 |
|---|---|---|---|
| `ui/preferences_panel.py` | 100 | 43 | 43.0% |
| `ui/welcome_widget.py` | 94 | 12 | 12.8% |
| `ui/mixins/menu_builder_mixin.py` | 187 | 10 | 5.3% |
| `ui/mixins/capability_wiring_mixin.py` | 128 | 4 | 3.1% |

## 说明

- 模板来自 `tools/extract_i18n_strings.py`（全仓 5218 条）；
- 首批优先覆盖：菜单、欢迎页、偏好页与常用动作；
- 未翻译项安全回退中文；长尾继续分批补充。
