# 声明式语言包（Notepad++ UDL 等价物）

给编辑器**新增一门语言**的语法高亮 / 注释 / 折叠规则，**不需要写代码**，
投放一个 JSON 文件即可。设计参考 Notepad++ 的 UDL（User Defined Language）。

## 放置位置（自动扫描）

| 位置 | 用途 |
|---|---|
| `data/language_packs/*.qingcao-lang.json` | 用户/本机全局语言包 |
| `plugins/<插件名>/languages/*.qingcao-lang.json` | 插件随包携带的语言 |

按扩展名建立索引；**语言包优先于内置映射表**（内置映射见
`ui/editor_view.py::LEXER_BY_EXTENSION`）。

## 格式

```json
{
  "name": "MyLang",
  "extensions": [".mylang", ".ml"],
  "keywords": ["if", "else", "func", "return"],
  "case_sensitive": false,
  "line_comment": "//",
  "block_comment": ["/*", "*/"],
  "strings": ["\"", "'"],
  "folding": {"start": "{", "end": "}"}
}
```

字段说明：

| 字段 | 必填 | 含义 |
|---|---|---|
| `name` | ✅ | 显示名 |
| `extensions` | ✅ | 扩展名列表（带点，大小写不敏感） |
| `keywords` / `line_comment` | 至少一个 | 关键字集合；行注释前缀 |
| `block_comment` | 否 | `[开始, 结束]` |
| `strings` | 否 | 字符串定界符列表 |
| `folding` | 否 | 折叠括号（预留） |
| `case_sensitive` | 否 | 默认 false |

高亮样式：关键字/注释/字符串/数字/标识符/默认，共 6 种，颜色跟随当前主题
（`ThemeColors.keyword/comment/string/number/identifier`）。

## 性能说明

* 文档超过 **1MB** 时语言包高亮自动退化为默认样式（与「大文档模式」一致）；
* 逐字节扫描只在可视/需要重排时发生，普通文件开销可忽略。

## 示例

[`docs/examples/mylang.qingcao-lang.json`](examples/mylang.qingcao-lang.json)
—— 复制到 `data/language_packs/` 后，打开 `.mylang` 文件即可看到高亮。

## 测试

`tests/test_language_pack.py` 覆盖：格式校验、目录发现、注册/查找、
`create_lexer_for_extension()` 命中、样式分类（关键字/数字/注释/字符串）。
