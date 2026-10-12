#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 4 语言的完整翻译目录（P1-2）

修复前：
    * locale/ 下只有 zh_CN/qingcao.po，且正文是 GBK 字节却声明
      charset=UTF-8（UTF-8 解析必然失败）；
    * 没有任何 .mo 文件，gettext.translation() 只会抛
      FileNotFoundError，国际化从未生效；
    * core/i18n.py 声明 4 种语言，实际是空壳。

本脚本把内置的翻译表写成规范的 UTF-8 .po，并调用
``tools/compile_locale.py`` 编译出 .mo。

用法::

    python tools/build_translations.py
"""
import io
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_DIR = os.path.join(ROOT, 'locale')
DOMAIN = 'qingcao'

# ============================================================
# 翻译表：msgid -> {lang: msgstr}
# 只收录界面上真实存在的字符串（菜单、按钮、通用提示）。
# ============================================================
CATALOG = {
    # 顶层菜单
    "File": {"zh_CN": "文件", "en_US": "File",
             "ja_JP": "ファイル", "ko_KR": "파일"},
    "Edit": {"zh_CN": "编辑", "en_US": "Edit",
             "ja_JP": "編集", "ko_KR": "편집"},
    "View": {"zh_CN": "视图", "en_US": "View",
             "ja_JP": "表示", "ko_KR": "보기"},
    "Tools": {"zh_CN": "工具", "en_US": "Tools",
              "ja_JP": "ツール", "ko_KR": "도구"},
    "Help": {"zh_CN": "帮助", "en_US": "Help",
             "ja_JP": "ヘルプ", "ko_KR": "도움말"},

    # 文件菜单
    "New File": {"zh_CN": "新建文件", "en_US": "New File",
                 "ja_JP": "新規ファイル", "ko_KR": "새 파일"},
    "Open File": {"zh_CN": "打开文件", "en_US": "Open File",
                  "ja_JP": "ファイルを開く", "ko_KR": "파일 열기"},
    "Open Folder": {"zh_CN": "打开文件夹", "en_US": "Open Folder",
                    "ja_JP": "フォルダーを開く", "ko_KR": "폴더 열기"},
    "Save": {"zh_CN": "保存", "en_US": "Save",
             "ja_JP": "保存", "ko_KR": "저장"},
    "Save As": {"zh_CN": "另存为", "en_US": "Save As",
                "ja_JP": "名前を付けて保存", "ko_KR": "다른 이름으로 저장"},
    "Save All": {"zh_CN": "全部保存", "en_US": "Save All",
                 "ja_JP": "すべて保存", "ko_KR": "모두 저장"},
    "Close Tab": {"zh_CN": "关闭标签", "en_US": "Close Tab",
                  "ja_JP": "タブを閉じる", "ko_KR": "탭 닫기"},
    "Exit": {"zh_CN": "退出", "en_US": "Exit",
             "ja_JP": "終了", "ko_KR": "종료"},

    # 编辑菜单
    "Undo": {"zh_CN": "撤销", "en_US": "Undo",
             "ja_JP": "元に戻す", "ko_KR": "실행 취소"},
    "Redo": {"zh_CN": "重做", "en_US": "Redo",
             "ja_JP": "やり直し", "ko_KR": "다시 실행"},
    "Cut": {"zh_CN": "剪切", "en_US": "Cut",
            "ja_JP": "切り取り", "ko_KR": "잘라내기"},
    "Copy": {"zh_CN": "复制", "en_US": "Copy",
             "ja_JP": "コピー", "ko_KR": "복사"},
    "Paste": {"zh_CN": "粘贴", "en_US": "Paste",
              "ja_JP": "貼り付け", "ko_KR": "붙여넣기"},
    "Select All": {"zh_CN": "全选", "en_US": "Select All",
                   "ja_JP": "すべて選択", "ko_KR": "모두 선택"},
    "Find": {"zh_CN": "查找", "en_US": "Find",
             "ja_JP": "検索", "ko_KR": "찾기"},
    "Replace": {"zh_CN": "替换", "en_US": "Replace",
                "ja_JP": "置換", "ko_KR": "바꾸기"},
    "Find in Files": {"zh_CN": "在文件中查找", "en_US": "Find in Files",
                      "ja_JP": "ファイル内検索",
                      "ko_KR": "파일에서 찾기"},
    "Go to Line": {"zh_CN": "跳转到行", "en_US": "Go to Line",
                   "ja_JP": "行へ移動", "ko_KR": "줄로 이동"},

    # 视图菜单
    "Outline": {"zh_CN": "大纲", "en_US": "Outline",
                "ja_JP": "アウトライン", "ko_KR": "개요"},
    "Directory Tree": {"zh_CN": "目录树", "en_US": "Directory Tree",
                       "ja_JP": "ディレクトリツリー",
                       "ko_KR": "디렉터리 트리"},
    "Minimap": {"zh_CN": "缩略图", "en_US": "Minimap",
                "ja_JP": "ミニマップ", "ko_KR": "미니맵"},
    "Python Console": {"zh_CN": "Python 控制台", "en_US": "Python Console",
                       "ja_JP": "Python コンソール",
                       "ko_KR": "Python 콘솔"},
    "Performance Monitor": {"zh_CN": "性能监控",
                            "en_US": "Performance Monitor",
                            "ja_JP": "パフォーマンスモニター",
                            "ko_KR": "성능 모니터"},
    "Full Screen": {"zh_CN": "全屏", "en_US": "Full Screen",
                    "ja_JP": "全画面", "ko_KR": "전체 화면"},
    "Distraction Free": {"zh_CN": "无干扰模式",
                         "en_US": "Distraction Free",
                         "ja_JP": "集中モード",
                         "ko_KR": "집중 모드"},

    # 工具菜单
    "Command Palette": {"zh_CN": "命令面板", "en_US": "Command Palette",
                        "ja_JP": "コマンドパレット",
                        "ko_KR": "명령 팔레트"},
    "Plugin Manager": {"zh_CN": "插件管理", "en_US": "Plugin Manager",
                       "ja_JP": "プラグイン管理",
                       "ko_KR": "플러그인 관리"},
    "Plugin Store": {"zh_CN": "插件市场", "en_US": "Plugin Store",
                     "ja_JP": "プラグインストア",
                     "ko_KR": "플러그인 스토어"},
    "Preferences": {"zh_CN": "首选项", "en_US": "Preferences",
                    "ja_JP": "環境設定", "ko_KR": "환경 설정"},
    "Keyboard Shortcuts": {"zh_CN": "快捷键参考",
                           "en_US": "Keyboard Shortcuts",
                           "ja_JP": "キーボードショートカット",
                           "ko_KR": "키보드 단축키"},

    # 状态与提示
    "Ready": {"zh_CN": "就绪", "en_US": "Ready",
              "ja_JP": "準備完了", "ko_KR": "준비됨"},
    "Loading...": {"zh_CN": "加载中…", "en_US": "Loading...",
                   "ja_JP": "読み込み中…", "ko_KR": "로딩 중..."},
    "Saving...": {"zh_CN": "保存中…", "en_US": "Saving...",
                  "ja_JP": "保存中…", "ko_KR": "저장 중..."},
    "Saved": {"zh_CN": "已保存", "en_US": "Saved",
              "ja_JP": "保存しました", "ko_KR": "저장됨"},
    "Untitled": {"zh_CN": "未命名", "en_US": "Untitled",
                 "ja_JP": "無題", "ko_KR": "제목 없음"},
    "Modified": {"zh_CN": "已修改", "en_US": "Modified",
                 "ja_JP": "変更済み", "ko_KR": "수정됨"},
    "OK": {"zh_CN": "确定", "en_US": "OK",
           "ja_JP": "OK", "ko_KR": "확인"},
    "Cancel": {"zh_CN": "取消", "en_US": "Cancel",
               "ja_JP": "キャンセル", "ko_KR": "취소"},
    "Yes": {"zh_CN": "是", "en_US": "Yes",
            "ja_JP": "はい", "ko_KR": "예"},
    "No": {"zh_CN": "否", "en_US": "No",
           "ja_JP": "いいえ", "ko_KR": "아니요"},
    "Error": {"zh_CN": "错误", "en_US": "Error",
              "ja_JP": "エラー", "ko_KR": "오류"},
    "Warning": {"zh_CN": "警告", "en_US": "Warning",
                "ja_JP": "警告", "ko_KR": "경고"},
    "Information": {"zh_CN": "信息", "en_US": "Information",
                    "ja_JP": "情報", "ko_KR": "정보"},
    "Language": {"zh_CN": "语言", "en_US": "Language",
                 "ja_JP": "言語", "ko_KR": "언어"},
}

HEADER = '''msgid ""
msgstr ""
"Project-Id-Version: QingCao 2.1\\n"
"Language: {lang}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"X-Generator: tools/build_translations.py\\n"
'''


def escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def write_po(lang: str) -> int:
    """写出某语言的 .po，返回词条数"""
    path = os.path.join(LOCALE_DIR, lang, 'LC_MESSAGES',
                        f'{DOMAIN}.po')
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines = [HEADER.format(lang=lang)]
    count = 0
    for msgid in sorted(CATALOG):
        msgstr = CATALOG[msgid].get(lang, '')
        lines.append('msgid "%s"' % escape(msgid))
        lines.append('msgstr "%s"' % escape(msgstr))
        lines.append('')
        count += 1

    io.open(path, 'w', encoding='utf-8', newline='\n').write(
        '\n'.join(lines)
    )
    return count


def main():
    # 控制台可能是 GBK 代码页，直接 print 韩文/日文会 UnicodeEncodeError。
    # 统一把 stdout 切到 UTF-8（失败则忽略，不影响写文件）。
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    print("[build_translations] 写入 %d 条词条 × 4 语言"
          % len(CATALOG))
    for lang in ('zh_CN', 'en_US', 'ja_JP', 'ko_KR'):
        n = write_po(lang)
        print("  %s: %d 条" % (lang, n))

    # 编译 .mo
    tool = os.path.join(ROOT, 'tools', 'compile_locale.py')
    print("[build_translations] 编译 .mo ...")
    rc = subprocess.call([sys.executable, tool])
    if rc != 0:
        print("[build_translations] 编译失败")
        return rc

    # 校验：真实加载一次
    import gettext
    for lang in ('zh_CN', 'en_US', 'ja_JP', 'ko_KR'):
        try:
            tr = gettext.translation(
                DOMAIN, LOCALE_DIR, languages=[lang]
            )
            got = tr.gettext("Save")
            print("  verify %s: Save -> %s" % (lang, got))
        except Exception as e:
            print("  verify %s FAILED: %s" % (lang, e))
            return 1
    print("[build_translations] 完成")
    return 0


if __name__ == '__main__':
    sys.exit(main())
