# -*- coding: utf-8 -*-
"""声明式语言包（Notepad++ UDL 等价物）

新增一门语言的语法高亮/折叠/注释规则**不需要写代码**，只需投放一个
JSON 文件：

    data/language_packs/mylang.qingcao-lang.json
    # 或插件目录：plugins/<plugin>/languages/mylang.qingcao-lang.json

格式：

    {
      "name": "MyLang",
      "extensions": [".mylang", ".ml"],
      "keywords": ["if", "else", "for", "return"],
      "case_sensitive": false,
      "line_comment": "//",
      "block_comment": ["/*", "*/"],
      "strings": ["\"", "'"],
      "folding": {"start": "{", "end": "}"}
    }

设计参考 Notepad++ 的 UDL（User Defined Language）：把"用户可扩展
语言支持"从**写插件代码**降级为**写配置**。宿主侧由
`ui/generic_lexer.GenericLexer`（QsciLexerCustom）解释这份配置。

加载顺序（后者覆盖前者）：
    1. 内置 data/language_packs
    2. 各插件的 languages/ 目录
按扩展名索引，便于 `create_lexer_for_extension()` 直接命中。
"""
import glob
import json
import os
from typing import Dict, List, Optional


_PACK_SUFFIX = ".qingcao-lang.json"
_CACHE: Optional[Dict[str, "LanguagePack"]] = None


class LanguagePack:
    """一门声明式语言定义"""

    def __init__(self, data: dict, source: str = ""):
        self.source = source
        self.name = str(data.get("name") or "").strip()
        exts = data.get("extensions") or []
        self.extensions = [str(e).lower() if str(e).startswith(".")
                           else "." + str(e).lower() for e in exts]
        self.keywords = {str(k) for k in (data.get("keywords") or [])}
        self.case_sensitive = bool(data.get("case_sensitive", False))
        self.line_comment = str(data.get("line_comment") or "")
        block = data.get("block_comment") or []
        self.block_comment = (str(block[0]), str(block[1])) \
            if len(block) == 2 else ("", "")
        self.strings = [str(s) for s in (data.get("strings") or []) if s]
        folding = data.get("folding") or {}
        self.fold_start = str(folding.get("start") or "")
        self.fold_end = str(folding.get("end") or "")

    def validate(self) -> List[str]:
        errors = []
        if not self.name:
            errors.append("缺少 name")
        if not self.extensions:
            errors.append("缺少 extensions")
        if not self.keywords and not self.line_comment:
            errors.append("keywords 与 line_comment 不能同时为空")
        for ext in self.extensions:
            if not ext.startswith(".") or len(ext) < 2:
                errors.append("非法扩展名: %r" % ext)
        return errors

    def __repr__(self):
        return "<LanguagePack %s %s>" % (self.name, self.extensions)


def load_pack(path: str) -> LanguagePack:
    """读取并校验一个语言包文件（非法时抛 ValueError）"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("语言包必须是 JSON 对象: %s" % path)
    pack = LanguagePack(data, source=path)
    errors = pack.validate()
    if errors:
        raise ValueError("%s: %s" % (os.path.basename(path),
                                     "；".join(errors)))
    return pack


def _default_pack_dirs() -> List[str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dirs = [os.path.join(root, "data", "language_packs")]
    dirs.extend(sorted(glob.glob(
        os.path.join(root, "plugins", "*", "languages"))))
    return [d for d in dirs if os.path.isdir(d)]


def discover_packs(dirs: Optional[List[str]] = None) -> Dict[str, LanguagePack]:
    """扫描目录，返回 {扩展名: LanguagePack}"""
    mapping: Dict[str, LanguagePack] = {}
    for directory in (dirs if dirs is not None else _default_pack_dirs()):
        if not os.path.isdir(directory):
            continue
        for path in sorted(glob.glob(
                os.path.join(directory, "**", "*" + _PACK_SUFFIX),
                recursive=True)):
            try:
                pack = load_pack(path)
            except (OSError, ValueError) as e:
                print("[LanguagePack] 跳过 %s: %s" % (path, e))
                continue
            for ext in pack.extensions:
                mapping[ext] = pack
    return mapping


def get_packs(refresh: bool = False) -> Dict[str, LanguagePack]:
    """获取全局语言包索引（带缓存）"""
    global _CACHE
    if _CACHE is None or refresh:
        _CACHE = discover_packs()
    return _CACHE


def get_pack_for_extension(ext: str) -> Optional[LanguagePack]:
    """按扩展名取语言包（ext 可带点也可不带点）"""
    if not ext:
        return None
    ext = ext if ext.startswith(".") else "." + ext
    return get_packs().get(ext.lower())


def register_pack(pack: LanguagePack) -> None:
    """运行期注册（主要供测试/插件使用）"""
    packs = get_packs()
    for ext in pack.extensions:
        packs[ext] = pack


def reset_cache() -> None:
    """清空缓存（测试/开发用）"""
    global _CACHE
    _CACHE = None
