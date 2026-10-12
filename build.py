#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为 PyInstaller 打包脚本，包含：
- 环境检查（Python 版本、依赖、PyInstaller）
- 图标处理（自动从 PNG 生成 ICO）
- .spec 文件生成（完整配置）
- Windows 版本信息文件生成
- 资源文件收集（resources/themes/locale/docs）
- 隐藏导入收集（QScintilla、chardet、requests、psutil 等）
- 排除模块（PySide6、PyQt6、numpy、matplotlib 等）
- UPX 压缩支持
- 构建清理与后处理
- 多平台支持（Windows/Linux/macOS）
- 单文件/目录模式
- 调试模式（保留控制台）
- 体积统计报告

用法:
    python build.py                    # 默认目录模式
    python build.py --onefile          # 单文件模式
    python build.py --debug            # 调试模式（保留控制台）
    python build.py --console          # 保留控制台窗口
    python build.py --no-upx           # 禁用 UPX 压缩
    python build.py --clean            # 清理旧构建
    python build.py --no-clean         # 不清理旧构建
    python build.py --icon path.ico    # 指定图标
    python build.py --name MyApp       # 自定义应用名
    python build.py --hidden-import=X  # 追加隐藏导入
    python build.py --exclude=Y        # 追加排除模块

修复记录:
- generate_spec: 从生成的 .spec 模板中删除未使用的
  `from PyInstaller.utils.hooks import collect_submodules`（P3-3）。
  该导入既不被 build.py 使用，也不被生成的 spec 调用。
- 顶层：删除未使用的 `import json`（P3-extra）。
  全文件未发现任何 `json.` 调用。
"""

import argparse
import datetime
import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple


# ============================================================
# 常量
# ============================================================
ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, 'dist')
BUILD_DIR = os.path.join(ROOT, 'build')
SPEC_FILE = os.path.join(ROOT, 'QingCaoEditor.spec')
VERSION_INFO_FILE = os.path.join(ROOT, 'version_info.txt')
ICON_SRC = os.path.join(ROOT, 'resources', 'icons', 'qingcao.png')
ICON_DST = os.path.join(ROOT, 'resources', 'icons', 'qingcao.ico')

APP_NAME = 'QingCaoEditor'
APP_DISPLAY_NAME = '青草编辑器'
# P1-1: 版本号唯一来源 version.py（避免多处硬编码导致版本漂移）
try:
    from version import __version__ as APP_VERSION
except ImportError:  # pragma: no cover
    APP_VERSION = "2.1.0"
APP_AUTHOR = 'hedongwei'
APP_EMAIL = '1265338136@qq.com'
APP_DESCRIPTION = 'Lightweight text editor with LSP and plugin system'
APP_COMPANY = 'hedongwei'
APP_COPYRIGHT = 'Copyright (C) 2024-2025 hedongwei'
APP_URL = 'https://github.com/qingcao-editor/qingcao'

# 需要打包的数据目录
DATA_DIRS = [
    'resources',
    'themes',
    'locale',
    'docs',
    'plugins',
]

# 需要排除的目录（不打包进 exe）
EXCLUDE_DIRS = {
    '__pycache__', '.git', '.github', '.idea', '.vscode',
    'build', 'dist', 'data', 'logs', 'backup', 'installer',
    'tests', '_archived_tools', 'tools', 'QingCaoEditor_RCWJ',
    'venv', '.venv', 'env', '.env', 'node_modules',
}

# 需要排除的模块（减小体积）
DEFAULT_EXCLUDES = [
    # 其他 Qt 绑定
    'PySide2', 'PySide6', 'PyQt6', 'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebEngine', 'PyQt5.QtQuick', 'PyQt5.QtQml',
    'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtPositioning',
    'PyQt5.QtSensors', 'PyQt5.QtSerialPort', 'PyQt5.QtWebSockets',
    'PyQt5.QtWebChannel', 'PyQt5.QtXmlPatterns',
    # 科学计算（不用）
    'numpy', 'scipy', 'pandas', 'matplotlib', 'sklearn',
    'skimage', 'cv2', 'PIL.ImageQt',
    # 测试
    'test', 'unittest', 'doctest', 'pydoc_data', 'pytest',
    'nose', 'coverage',
    # 开发工具
    'IPython', 'jupyter', 'notebook', 'ipykernel',
    # 其他
    'tkinter', 'turtle', 'sqlite3.dbapi2',
    'setuptools', 'pip', 'wheel', 'pkg_resources',
]


# ============================================================
# 工具函数
# ============================================================
def print_header(title: str):
    """打印标题"""
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_step(msg: str):
    """打印步骤"""
    print(f"[STEP] {msg}")


def print_ok(msg: str):
    """打印成功"""
    print(f"[OK]   {msg}")


def print_warn(msg: str):
    """打印警告"""
    print(f"[WARN] {msg}")


def print_error(msg: str):
    """打印错误"""
    print(f"[FAIL] {msg}")


# ============================================================
# 环境检查
# ============================================================
def check_python_version() -> bool:
    """检查 Python 版本"""
    version = sys.version_info
    print_step(f"Python 版本: {sys.version.split()[0]}")

    if version < (3, 8):
        print_error("需要 Python 3.8+")
        return False

    if version >= (3, 13):
        print_warn("Python 3.13+ 可能缺少 PyQt5 wheel，建议使用 3.8-3.12")

    return True


def check_pyinstaller() -> bool:
    """检查 PyInstaller"""
    try:
        import PyInstaller
        version = getattr(PyInstaller, '__version__', '未知')
        print_ok(f"PyInstaller {version}")
        return True
    except ImportError:
        print_error("PyInstaller 未安装")
        print()
        print("请运行:")
        print("  pip install pyinstaller")
        return False


def check_core_dependencies() -> Tuple[bool, List[str]]:
    """检查核心依赖"""
    required = [
        ('PyQt5', 'PyQt5.QtCore'),
        ('PyQt5-Qsci', 'PyQt5.Qsci'),
    ]

    optional = [
        ('chardet', 'chardet'),
        ('requests', 'requests'),
        ('psutil', 'psutil'),
        ('keyring', 'keyring'),
    ]

    missing = []

    print()
    print_step("核心依赖检查:")
    for name, module in required:
        try:
            __import__(module)
            print_ok(f"  {name}")
        except ImportError:
            print_error(f"  {name} 未安装")
            missing.append(name)

    print()
    print_step("可选依赖检查:")
    for name, module in optional:
        try:
            __import__(module)
            print_ok(f"  {name}")
        except ImportError:
            print_warn(f"  {name} 未安装（功能受限）")

    return (len(missing) == 0, missing)


# ============================================================
# 图标处理
# ============================================================
def generate_icon() -> Optional[str]:
    """
    生成图标文件。

    优先使用已有的 .ico；如果只有 .png，尝试转换为 .ico。
    """
    # 已有 ico
    if os.path.exists(ICON_DST):
        print_ok(f"图标: {ICON_DST}")
        return ICON_DST

    # 只有 png，尝试转换
    if os.path.exists(ICON_SRC):
        print_step(f"从 PNG 转换图标: {ICON_SRC}")

        # 方法 1: PIL
        try:
            from PIL import Image
            img = Image.open(ICON_SRC)
            sizes = [(16, 16), (24, 24), (32, 32), (48, 48),
                     (64, 64), (128, 128), (256, 256)]
            img.save(ICON_DST, format='ICO', sizes=sizes)
            print_ok(f"已生成: {ICON_DST}")
            return ICON_DST
        except ImportError:
            pass
        except Exception as e:
            print_warn(f"PIL 转换失败: {e}")

        # 方法 2: ImageMagick
        try:
            result = subprocess.run(
                ['magick', 'convert', ICON_SRC, '-define',
                 'icon:auto-resize=256,128,64,48,32,16', ICON_DST],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(ICON_DST):
                print_ok(f"已生成 (ImageMagick): {ICON_DST}")
                return ICON_DST
        except Exception:
            pass

        print_warn("无法生成图标，将使用 PyInstaller 默认图标")
        print("  提示: pip install Pillow")

    print_warn("未找到图标文件")
    return None


# ============================================================
# 版本信息文件（Windows 专用）
# ============================================================
def generate_version_info() -> Optional[str]:
    """生成 Windows 版本信息文件"""
    if platform.system() != 'Windows':
        return None

    # 解析版本号
    try:
        parts = APP_VERSION.split('.')
        while len(parts) < 4:
            parts.append('0')
        version_tuple = tuple(int(p) for p in parts[:4])
    except Exception:
        version_tuple = (2, 0, 0, 0)

    content = f"""# UTF-8
#
# 青草编辑器版本信息
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'080404B0',
          [StringStruct(u'CompanyName', u'{APP_COMPANY}'),
           StringStruct(u'FileDescription', u'{APP_DESCRIPTION}'),
           StringStruct(u'FileVersion', u'{APP_VERSION}'),
           StringStruct(u'InternalName', u'{APP_NAME}'),
           StringStruct(u'LegalCopyright', u'{APP_COPYRIGHT}'),
           StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
           StringStruct(u'ProductName', u'{APP_DISPLAY_NAME}'),
           StringStruct(u'ProductVersion', u'{APP_VERSION}'),
           StringStruct(u'Comments', u'青草枯荣，野火重生。'),
           StringStruct(u'Author', u'{APP_AUTHOR}'),
           StringStruct(u'Email', u'{APP_EMAIL}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""

    try:
        with open(VERSION_INFO_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        print_ok(f"版本信息: {VERSION_INFO_FILE}")
        return VERSION_INFO_FILE
    except Exception as e:
        print_warn(f"生成版本信息失败: {e}")
        return None


# ============================================================
# 资源收集
# ============================================================
def collect_datas() -> List[Tuple[str, str]]:
    """收集需要打包的数据文件"""
    datas = []
    for d in DATA_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            datas.append((src, d))
    return datas


def collect_hidden_imports() -> List[str]:
    """收集隐藏导入"""
    imports = []

    # QScintilla
    try:
        import PyQt5.Qsci
        imports.append('PyQt5.Qsci')
    except ImportError:
        pass

    # 可选依赖（按存在性收集）
    for mod in ['chardet', 'requests', 'psutil', 'keyring',
                'urllib3', 'certifi', 'idna', 'charset_normalizer',
                'reportlab', 'pypinyin']:
        try:
            __import__(mod)
            imports.append(mod)
        except ImportError:
            pass

    # Qt 模块（PyInstaller 有时会漏掉）
    qt_modules = [
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.QtNetwork',
        'PyQt5.QtPrintSupport',
        'PyQt5.QtSvg',
        'PyQt5.QtXml',
    ]
    for m in qt_modules:
        try:
            __import__(m)
            imports.append(m)
        except ImportError:
            pass

    # QtMultimedia（可选，用于音效）
    try:
        import PyQt5.QtMultimedia
        imports.append('PyQt5.QtMultimedia')
    except ImportError:
        pass

    # 项目内部模块
    project_modules = [
        'app', 'core', 'ui', 'infrastructure',
        'app.actions', 'app.event_bus', 'app.menus', 'app.plugins',
        'app.preferences', 'app.session', 'app.tabs', 'app.sync',
        'app.config_manager', 'app.plugin_manager',
        'core.commands', 'core.content_provider', 'core.document',
        'core.editor', 'core.events', 'core.log_lexer',
        'core.lsp_client', 'core.lsp_installer', 'core.macro',
        'core.project', 'core.search',
        'core.undo', 'core.ai_client', 'core.benchmark',
        'core.code_metrics', 'core.code_smell', 'core.code_templates',
        'core.collab', 'core.crash_reporter', 'core.exporter',
        'core.file_merge', 'core.formatter', 'core.git_client',
        'core.i18n', 'core.key_sequence_manager',
        'core.keymap_profiles', 'core.local_completer',
        'core.problems', 'core.profiler', 'core.project_config',
        'core.project_tasks', 'core.refactor_session',
        'core.snippet_market', 'core.snippets', 'core.snapshot',
        'core.telemetry', 'core.theme_pack', 'core.updater',
        'core.vim_mode', 'core.workspace',
        'infrastructure.file_access', 'infrastructure.icon_manager',
        'infrastructure.plugin_loader', 'infrastructure.plugin_sandbox',
        'infrastructure.plugin_updater', 'infrastructure.sound_manager',
        'infrastructure.theme_loader',
    ]
    for m in project_modules:
        try:
            __import__(m)
            imports.append(m)
        except ImportError:
            pass

    return sorted(set(imports))


def collect_excludes(extra_excludes: Optional[List[str]] = None
                      ) -> List[str]:
    """收集排除模块"""
    excludes = list(DEFAULT_EXCLUDES)
    if extra_excludes:
        excludes.extend(extra_excludes)
    return sorted(set(excludes))


# ============================================================
# spec 文件生成
# ============================================================
def generate_spec(
    onefile: bool = False,
    console: bool = False,
    icon_path: Optional[str] = None,
    app_name: str = APP_NAME,
    extra_hidden: Optional[List[str]] = None,
    extra_excludes: Optional[List[str]] = None,
    upx: bool = True,
):
    """
    生成 .spec 文件。

    修复说明（P3-3）:
        - 原模板中包含了未使用的
          `from PyInstaller.utils.hooks import collect_submodules`，
          既不被 build.py 使用，也不被生成的 spec 调用。
        - 已从模板中删除该行，保持模板干净。
    """
    datas = collect_datas()
    hiddenimports = collect_hidden_imports()
    if extra_hidden:
        hiddenimports.extend(extra_hidden)
    hiddenimports = sorted(set(hiddenimports))

    excludes = collect_excludes(extra_excludes)

    # 版本信息
    version_info = generate_version_info()

    # 格式化
    def fmt_list(items, indent='    '):
        if not items:
            return '[]'
        lines = ['[']
        for item in items:
            lines.append(f'{indent}{repr(item)},')
        lines.append(']')
        return '\n'.join(lines)

    datas_repr = fmt_list(datas)
    hidden_repr = fmt_list(hiddenimports)
    excludes_repr = fmt_list(excludes)

    icon_repr = repr(icon_path) if icon_path else 'None'
    version_repr = repr(version_info) if version_info else 'None'
    console_repr = 'True' if console else 'False'
    upx_repr = 'True' if upx else 'False'

    # UPX 路径检测
    upx_dir = ''
    if upx:
        upx_exe = shutil.which('upx')
        if upx_exe:
            upx_dir = os.path.dirname(upx_exe)

    if onefile:
        exe_block = f"""
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name={repr(app_name)},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx={upx_repr},
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console_repr},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_repr},
    version={version_repr},
)
"""
    else:
        exe_block = f"""
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name={repr(app_name)},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx={upx_repr},
    console={console_repr},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_repr},
    version={version_repr},
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx={upx_repr},
    upx_exclude=[],
    name={repr(app_name)},
)
"""

    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
# ============================================================
# 青草编辑器 PyInstaller spec
# 由 build.py 自动生成于 {datetime.datetime.now().isoformat()}
# 请勿手动编辑
# ============================================================

import os
import sys

block_cipher = None

# 工作目录
ROOT = {repr(ROOT)}

# 数据文件
datas = {datas_repr}

# 隐藏导入
hiddenimports = {hidden_repr}

# 排除模块
excludes = {excludes_repr}

# UPX 路径
upx_dir = {repr(upx_dir)}

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

{exe_block}
"""

    try:
        with open(SPEC_FILE, 'w', encoding='utf-8') as f:
            f.write(spec_content)
        print_ok(f"spec 文件已生成: {SPEC_FILE}")
        return True
    except Exception as e:
        print_error(f"生成 spec 失败: {e}")
        return False


# ============================================================
# 清理
# ============================================================
def clean_build(quiet: bool = False, clean_spec: bool = False):
    """
    清理旧的构建。

    修复说明（P2-新-3）: 默认保留 .spec 文件，避免用户手动
    定制的内容被误删；只有 --clean-spec 时才删除。
    """
    if not quiet:
        print_step("清理旧构建...")

    # 删除 dist / build
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            if not quiet:
                print(f"  移除: {d}")
            shutil.rmtree(d, ignore_errors=True)

    # 删除 spec（仅在显式指定时）
    if clean_spec and os.path.exists(SPEC_FILE):
        try:
            os.remove(SPEC_FILE)
            if not quiet:
                print(f"  移除: {SPEC_FILE}")
        except Exception:
            pass

    # 删除版本信息
    if os.path.exists(VERSION_INFO_FILE):
        try:
            os.remove(VERSION_INFO_FILE)
        except Exception:
            pass

    # 删除 __pycache__（但保留 venv 等）
    if not quiet:
        print("  清理 __pycache__...")

    for root, dirs, files in os.walk(ROOT):
        # 跳过不需要清理的目录
        dirs[:] = [
            d for d in dirs
            if d not in ('venv', '.venv', 'env', '.env',
                          'node_modules', 'QingCaoEditor_RCWJ')
        ]

        if '__pycache__' in dirs:
            path = os.path.join(root, '__pycache__')
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass


# ============================================================
# 构建
# ============================================================
def run_pyinstaller(clean: bool = False) -> bool:
    """运行 PyInstaller"""
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        SPEC_FILE,
        '--noconfirm',
    ]

    if clean:
        cmd.append('--clean')

    print_step("执行 PyInstaller...")
    print("  命令: " + ' '.join(cmd))
    print()

    try:
        result = subprocess.run(cmd, cwd=ROOT)
        return result.returncode == 0
    except Exception as e:
        print_error(f"PyInstaller 执行失败: {e}")
        return False


# ============================================================
# 后处理
# ============================================================
def post_build(app_name: str = APP_NAME, onefile: bool = False):
    """构建后处理"""
    if onefile:
        # 单文件模式：只需处理 exe
        exe_path = os.path.join(DIST_DIR, app_name + '.exe')
        if platform.system() != 'Windows':
            exe_path = os.path.join(DIST_DIR, app_name)
        if os.path.exists(exe_path):
            print_ok(f"可执行文件: {exe_path}")
        return

    exe_dir = os.path.join(DIST_DIR, app_name)
    if not os.path.isdir(exe_dir):
        print_warn(f"未找到构建目录: {exe_dir}")
        return

    print_step("后处理...")

    # 创建运行时目录
    for d in ['data', 'logs', 'backup', 'plugins', 'themes']:
        path = os.path.join(exe_dir, d)
        os.makedirs(path, exist_ok=True)
        # 保留目录（.gitkeep）
        gitkeep = os.path.join(path, '.gitkeep')
        if not os.path.exists(gitkeep):
            try:
                open(gitkeep, 'w').close()
            except Exception:
                pass

    print_ok("运行时目录已创建")

    # 复制 README
    for fname in ['README.md', 'LICENSE', 'CHANGELOG.md',
                   'VERSION', 'portable.txt.example']:
        src = os.path.join(ROOT, fname)
        if os.path.exists(src):
            try:
                shutil.copy2(src, exe_dir)
                print_ok(f"已复制: {fname}")
            except Exception as e:
                print_warn(f"复制 {fname} 失败: {e}")

    # 创建启动脚本（便于调试）
    if platform.system() == 'Windows':
        # 创建 .bat 便于从命令行启动（保留控制台）
        bat_path = os.path.join(exe_dir, 'debug.bat')
        try:
            with open(bat_path, 'w', encoding='gbk') as f:
                f.write('@echo off\n')
                f.write('chcp 65001 >nul\n')
                f.write(f'"{app_name}.exe" %*\n')
                f.write('pause\n')
            print_ok(f"调试脚本: {bat_path}")
        except Exception:
            pass


# ============================================================
# 体积报告
# ============================================================
def report_size(app_name: str = APP_NAME, onefile: bool = False):
    """报告构建体积"""
    print()
    print("=" * 60)
    print("[OK] 打包完成！")
    print("=" * 60)

    if onefile:
        exe_path = os.path.join(DIST_DIR, app_name + '.exe')
        if platform.system() != 'Windows':
            exe_path = os.path.join(DIST_DIR, app_name)

        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / 1024 / 1024
            print(f"  可执行文件: {exe_path}")
            print(f"  文件大小:   {size_mb:.1f} MB")
        else:
            print_warn("未找到可执行文件")
        print("=" * 60)
        return

    exe_dir = os.path.join(DIST_DIR, app_name)
    if not os.path.isdir(exe_dir):
        print_warn("未找到构建目录")
        print("=" * 60)
        return

    # 统计
    total_size = 0
    file_count = 0
    dir_count = 0

    # 按文件类型统计
    type_stats = {}

    for root, dirs, files in os.walk(exe_dir):
        dir_count += len(dirs)
        for f in files:
            fp = os.path.join(root, f)
            try:
                size = os.path.getsize(fp)
                total_size += size
                file_count += 1

                # 按扩展名归类
                ext = os.path.splitext(f)[1].lower() or '(无扩展名)'
                type_stats[ext] = type_stats.get(ext, 0) + size
            except Exception:
                pass

    size_mb = total_size / 1024 / 1024

    print(f"  输出目录: {exe_dir}")
    print(f"  文件数量: {file_count}")
    print(f"  目录数量: {dir_count}")
    print(f"  总体积:   {size_mb:.1f} MB")

    # 主 exe
    exe_path = os.path.join(exe_dir, app_name + '.exe')
    if not os.path.exists(exe_path):
        exe_path = os.path.join(exe_dir, app_name)
    if os.path.exists(exe_path):
        exe_size = os.path.getsize(exe_path) / 1024 / 1024
        print(f"  主程序:   {exe_size:.1f} MB")

    # 体积 Top 5
    if type_stats:
        print()
        print("  体积构成 (Top 5):")
        sorted_types = sorted(
            type_stats.items(), key=lambda x: x[1], reverse=True
        )[:5]
        for ext, size in sorted_types:
            pct = size / total_size * 100
            print(f"    {ext:15s} {size / 1024 / 1024:7.1f} MB "
                  f"({pct:5.1f}%)")

    print("=" * 60)
    print()
    print("下一步:")
    print(f"  1. 测试运行: {os.path.join(exe_dir, app_name)}")
    print("  2. 制作安装包: python build_installer.py")
    print()


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description='青草编辑器打包脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build.py                     # 默认打包
  python build.py --onefile           # 单文件模式
  python build.py --debug --console   # 调试模式
  python build.py --clean             # 打包前清理
  python build.py --no-upx            # 禁用 UPX
  python build.py --name MyEditor     # 自定义应用名
  python build.py --icon my.ico       # 自定义图标
  python build.py --hidden-import=foo --hidden-import=bar
  python build.py --exclude=big_module
        """,
    )

    parser.add_argument('--onefile', action='store_true',
                        help='单文件模式（启动慢，方便分发）')
    parser.add_argument('--debug', action='store_true',
                        help='调试模式（等于 --console）')
    parser.add_argument('--console', action='store_true',
                        help='保留控制台窗口')
    parser.add_argument('--no-upx', action='store_true',
                        help='禁用 UPX 压缩')
    parser.add_argument('--clean', action='store_true',
                        help='打包前清理旧构建（保留 .spec）')
    parser.add_argument('--clean-spec', action='store_true',
                        help='同时删除生成的 .spec 文件')
    parser.add_argument('--no-clean', action='store_true',
                        help='不清理旧构建')
    parser.add_argument('--icon', type=str, default=None,
                        help='自定义图标路径')
    parser.add_argument('--name', type=str, default=APP_NAME,
                        help='自定义应用名')
    parser.add_argument('--hidden-import', action='append',
                        default=[], dest='hidden_imports',
                        help='追加隐藏导入（可多次）')
    parser.add_argument('--exclude', action='append',
                        default=[], dest='excludes',
                        help='追加排除模块（可多次）')
    parser.add_argument('--quiet', action='store_true',
                        help='安静模式')

    args = parser.parse_args()

    # 调试模式自动启用控制台
    if args.debug:
        args.console = True

    # 开始
    print_header("青草编辑器 - 打包")
    print(f"平台:    {platform.system()} {platform.release()}")
    print(f"架构:    {platform.machine()}")
    print(f"Python:  {sys.version.split()[0]}")
    print(f"项目:    {ROOT}")
    print(f"应用名:  {args.name}")
    print(f"版本:    {APP_VERSION}")
    print(f"模式:    {'单文件' if args.onefile else '目录'}")
    print(f"控制台:  {'是' if args.console else '否'}")
    print(f"UPX:     {'否' if args.no_upx else '是'}")

    # 1. 环境检查
    print_header("环境检查")
    if not check_python_version():
        return 1

    if not check_pyinstaller():
        return 1

    ok, missing = check_core_dependencies()
    if not ok:
        print()
        print_error("缺少核心依赖，无法继续")
        print("请运行:")
        print("  pip install -r requirements.txt")
        return 1

    # 2. 清理
    if args.clean or not args.no_clean:
        print_header("清理")
        clean_build(quiet=args.quiet, clean_spec=args.clean_spec)
        print_ok("已清理")

    # 3. 图标
    print_header("图标")
    icon_path = args.icon
    if icon_path:
        if not os.path.exists(icon_path):
            print_warn(f"指定的图标不存在: {icon_path}")
            icon_path = generate_icon()
    else:
        icon_path = generate_icon()

    if icon_path:
        print_ok(f"使用图标: {icon_path}")
    else:
        print_warn("不使用自定义图标")

    # 4. 生成 spec
    print_header("生成 spec")
    if not generate_spec(
        onefile=args.onefile,
        console=args.console,
        icon_path=icon_path,
        app_name=args.name,
        extra_hidden=args.hidden_imports,
        extra_excludes=args.excludes,
        upx=not args.no_upx,
    ):
        return 1

    # 5. 打包
    print_header("打包")
    if not run_pyinstaller(clean=args.clean):
        print_error("打包失败")
        return 1

    # 6. 后处理
    print_header("后处理")
    post_build(app_name=args.name, onefile=args.onefile)

    # 7. 报告
    report_size(app_name=args.name, onefile=args.onefile)

    return 0


# ============================================================
# 入口
# ============================================================
if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print_warn("用户中断")
        sys.exit(130)
    except Exception as e:
        print()
        print_error(f"打包异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)