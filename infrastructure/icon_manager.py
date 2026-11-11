# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""图标管理器（v2.25 拆分：common/cache/providers/manager）。"""

from infrastructure.icon_manager_cache import *  # noqa: F401,F403
from infrastructure.icon_manager_common import *  # noqa: F401,F403
from infrastructure.icon_manager_providers import *  # noqa: F401,F403


class IconManager(QObject):
    """
    图标管理器（单例）。

    统一管理所有图标，支持:
    - 多提供者回退
    - 图标缓存
    - 动态颜色
    - 多尺寸
    - 别名
    - 热重载

    信号:
        icon_loaded(str): 图标加载完成（名称）
        cache_cleared(): 缓存清空
    """

    icon_loaded = pyqtSignal(str)
    cache_cleared = pyqtSignal()

    _instance: Optional["IconManager"] = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        """单例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, icon_dir: str = DEFAULT_ICON_DIR, parent: Optional[QObject] = None):
        """
        参数:
            icon_dir: 图标目录
            parent: 父 QObject
        """
        if getattr(self, "_initialized", False):
            return

        super().__init__(parent)

        self.icon_dir = icon_dir

        # 图标缓存
        self.cache = IconCache()

        # 提供者列表（按优先级排序）
        self._providers: List[IconProvider] = []

        # 别名映射
        self._aliases: Dict[str, str] = {}

        # 初始化
        self._init_providers()
        self._init_aliases()

        self._initialized = True

    # ========================================================
    # 初始化
    # ========================================================
    def _init_providers(self):
        """初始化图标提供者"""
        providers = [
            SVGIconProvider(self.icon_dir),
            PNGIconProvider(self.icon_dir),
            ThemeIconProvider(),
            EmojiIconProvider(),
            BuiltinIconProvider(),
        ]

        # 按优先级排序
        providers.sort(key=lambda p: p.priority)
        self._providers = providers

    def _init_aliases(self):
        """初始化别名映射"""
        self._aliases = {
            # 文件操作
            "new_file": "file_new",
            "open_file": "file_open",
            "save_file": "file_save",
            # 编辑
            "undo_action": "undo",
            "redo_action": "redo",
            "cut_action": "cut",
            "copy_action": "copy",
            "paste_action": "paste",
            # 查找
            "find_action": "find",
            "replace_action": "replace",
            "search_action": "search",
            # 视图
            "sidebar": "panel",
            "bottom_panel": "panel",
            "minimap": "layout",
            # 文件类型
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "md": "file_md",
            "txt": "file_text",
            "log": "file_log",
            "json": "file_json",
            "xml": "file_xml",
            "html": "file_html",
            "css": "file_css",
            # 状态
            "ok": "success",
            "fail": "error",
            "danger": "error",
            "note": "info",
        }

    # ========================================================
    # 获取图标
    # ========================================================
    def get(self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None) -> QIcon:
        """
        获取图标。

        参数:
            name: 图标名称
            size: 尺寸（像素）
            color: 颜色（十六进制，如 "#7ec850"）

        返回:
            QIcon 实例（永不返回 None，回退到默认图标）
        """
        # 解析别名
        actual_name = self._aliases.get(name, name)

        # 生成缓存键
        cache_key = self._make_cache_key(actual_name, size, color)

        # 检查缓存
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # 遍历提供者
        for provider in self._providers:
            try:
                if provider.can_provide(actual_name):
                    icon = provider.get_icon(actual_name, size, color)
                    if icon and not icon.isNull():
                        self.cache.put(cache_key, icon)
                        self.icon_loaded.emit(actual_name)
                        return icon
            except Exception as e:
                print(f"[IconManager] 提供者失败 ({provider.__class__.__name__}): {e}")
                continue

        # 回退到默认图标
        return self._get_fallback_icon(name, size, color)

    def _get_fallback_icon(self, name: str, size: int, color: Optional[str]) -> QIcon:
        """获取回退图标"""
        cache_key = f"__fallback__::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # 创建一个简单的默认图标
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            # 灰色圆点
            painter.setBrush(QBrush(QColor("#888888")))
            painter.setPen(Qt.NoPen)
            margin = max(2, size // 4)
            painter.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)

            painter.end()

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception:
            return QIcon()

    def get_pixmap(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> QPixmap:
        """获取图标 Pixmap"""
        icon = self.get(name, size, color)
        return icon.pixmap(size, size)

    def _make_cache_key(self, name: str, size: int, color: Optional[str]) -> str:
        """生成缓存键"""
        color_part = color or "default"
        return f"{name}::{size}::{color_part}"

    # ========================================================
    # 别名
    # ========================================================
    def add_alias(self, alias: str, target: str):
        """添加别名"""
        self._aliases[alias] = target

    def remove_alias(self, alias: str):
        """移除别名"""
        self._aliases.pop(alias, None)

    def resolve_alias(self, name: str) -> str:
        """解析别名"""
        return self._aliases.get(name, name)

    # ========================================================
    # 可用性检查
    # ========================================================
    def has_icon(self, name: str) -> bool:
        """检查图标是否可用"""
        actual_name = self._aliases.get(name, name)

        for provider in self._providers:
            try:
                if provider.can_provide(actual_name):
                    return True
            except Exception:
                continue

        return False

    def list_icons(self) -> List[str]:
        """列出所有可用图标名称"""
        names = set()

        for provider in self._providers:
            try:
                names.update(provider.list_icons())
            except Exception:
                continue

        return sorted(names)

    def list_icons_by_provider(self) -> Dict[str, List[str]]:
        """按提供者列出图标"""
        result = {}

        for provider in self._providers:
            provider_name = provider.__class__.__name__
            try:
                result[provider_name] = provider.list_icons()
            except Exception:
                result[provider_name] = []

        return result

    # ========================================================
    # 缓存管理
    # ========================================================
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_cleared.emit()

    def cleanup_cache(self):
        """清理过期缓存"""
        self.cache.cleanup()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return self.cache.stats()

    # ========================================================
    # 热重载
    # ========================================================
    def reload(self):
        """重新加载所有图标"""
        # 清空缓存
        self.clear_cache()

        # 让提供者重新扫描
        for provider in self._providers:
            if hasattr(provider, "reload"):
                try:
                    provider.reload()
                except Exception as e:
                    print(f"[IconManager] 重载失败 ({provider.__class__.__name__}): {e}")

    def set_icon_dir(self, icon_dir: str):
        """设置图标目录"""
        self.icon_dir = icon_dir

        # 重建目录相关的提供者
        self._init_providers()
        self.clear_cache()

    # ========================================================
    # 图标组合
    # ========================================================
    def combine(self, base_name: str, overlay_name: str, size: int = DEFAULT_ICON_SIZE) -> QIcon:
        """
        组合两个图标（叠加）。

        参数:
            base_name: 底层图标
            overlay_name: 叠加图标
            size: 尺寸

        返回:
            组合后的 QIcon
        """
        cache_key = f"__combined__::{base_name}::{overlay_name}::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            base = self.get_pixmap(base_name, size)
            overlay = self.get_pixmap(overlay_name, size // 2)

            if base.isNull():
                return QIcon()

            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            # 绘制底层
            painter.drawPixmap(0, 0, base)

            # 绘制叠加（右下角）
            offset = size - overlay.width()
            painter.drawPixmap(offset, offset, overlay)

            painter.end()

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception as e:
            print(f"[IconManager] 组合失败: {e}")
            return self.get(base_name, size)

    # ========================================================
    # 从颜色生成图标
    # ========================================================
    def colored_circle(self, color: str, size: int = DEFAULT_ICON_SIZE) -> QIcon:
        """
        生成一个纯色圆点图标。

        参数:
            color: 颜色
            size: 尺寸

        返回:
            QIcon
        """
        cache_key = f"__circle__::{color}::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, size - 1, size - 1)

            painter.end()

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception as e:
            print(f"[IconManager] 生成圆点失败: {e}")
            return QIcon()

    def colored_square(self, color: str, size: int = DEFAULT_ICON_SIZE) -> QIcon:
        """生成纯色方块图标"""
        cache_key = f"__square__::{color}::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor(color))

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception as e:
            return QIcon()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出管理器信息"""
        lines = ["IconManager", "=" * 60]
        lines.append(f"图标目录: {self.icon_dir}")
        lines.append(f"提供者数: {len(self._providers)}")
        lines.append(f"别名数: {len(self._aliases)}")

        stats = self.cache.stats()
        lines.append(f"缓存大小: {stats['size']}/{stats['max_size']}")

        lines.append("")
        lines.append("提供者:")
        for provider in self._providers:
            try:
                count = len(provider.list_icons())
                lines.append(
                    f"  [{provider.priority}] {provider.__class__.__name__}: {count} 个图标"
                )
            except Exception:
                lines.append(f"  [{provider.priority}] {provider.__class__.__name__}: 错误")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<IconManager providers={len(self._providers)} cache={self.cache.size()}>"


# ============================================================
# 全局单例访问
# ============================================================
def get_icon_manager(icon_dir: str = DEFAULT_ICON_DIR) -> IconManager:
    """
    获取全局 IconManager 单例。

    参数:
        icon_dir: 图标目录（仅首次创建时有效）

    返回:
        IconManager 实例
    """
    return IconManager(icon_dir=icon_dir)


# 便捷函数
def get_icon(name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None) -> QIcon:
    """
    获取图标的便捷函数。

    参数:
        name: 图标名称
        size: 尺寸
        color: 颜色

    返回:
        QIcon 实例
    """
    manager = get_icon_manager()
    return manager.get(name, size, color)


def get_pixmap(name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None) -> QPixmap:
    """获取 Pixmap 的便捷函数"""
    manager = get_icon_manager()
    return manager.get_pixmap(name, size, color)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("IconManager 测试")
    win.resize(900, 700)

    # 创建临时图标目录
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_icon_test_")

    try:
        # 测试 IconManager
        print("=== 测试 IconManager ===")
        manager = IconManager(icon_dir=tmp_dir)

        print(manager.dump())
        print()

        # 测试系统图标
        print("=== 测试系统标准图标 ===")
        system_icons = ["file", "folder", "undo", "redo", "dialog_ok", "dialog_cancel", "trash"]
        for name in system_icons:
            icon = manager.get(name, 24)
            has = manager.has_icon(name)
            print(f"  {name}: {'✓' if has else '✗'} ({icon.availableSizes()})")
        print()

        # 测试 Emoji 图标
        print("=== 测试 Emoji 图标 ===")
        emoji_icons = ["file_python", "folder", "star", "warning", "success", "seedling"]
        for name in emoji_icons:
            icon = manager.get(name, 32)
            print(f"  {name}: {icon.availableSizes()}")
        print()

        # 测试别名
        print("=== 测试别名 ===")
        alias_tests = ["new_file", "open_file", "py", "ok"]
        for alias in alias_tests:
            resolved = manager.resolve_alias(alias)
            icon = manager.get(alias, 16)
            print(f"  {alias} -> {resolved}: {icon.availableSizes()}")
        print()

        # 测试缓存
        print("=== 测试缓存 ===")
        manager.clear_cache()

        # 第一次获取
        start = time.time()
        for _ in range(100):
            manager.get("file", 24)
        first_time = time.time() - start

        # 第二次获取（应该更快）
        start = time.time()
        for _ in range(100):
            manager.get("file", 24)
        second_time = time.time() - start

        print(f"  首次 100 次: {first_time * 1000:.2f} ms")
        print(f"  缓存后 100 次: {second_time * 1000:.2f} ms")
        print(f"  加速比: {first_time / max(0.0001, second_time):.1f}x")
        print()

        stats = manager.get_cache_stats()
        print(f"  缓存统计: {stats}")
        print()

        # 测试颜色着色
        print("=== 测试颜色着色 ===")
        colors = ["#7ec850", "#f14c4c", "#4dabf7"]
        for color in colors:
            icon = manager.get("file", 24, color)
            print(f"  {color}: {icon.availableSizes()}")
        print()

        # 测试组合图标
        print("=== 测试组合图标 ===")
        combined = manager.combine("folder", "star", 32)
        print(f"  组合图标: {combined.availableSizes()}")
        print()

        # 测试生成的图标
        print("=== 测试生成的图标 ===")
        circle = manager.colored_circle("#7ec850", 16)
        square = manager.colored_square("#f14c4c", 16)
        print(f"  圆点: {circle.availableSizes()}")
        print(f"  方块: {square.availableSizes()}")
        print()

        # 列出所有可用图标
        print("=== 所有可用图标 ===")
        all_icons = manager.list_icons()
        print(f"  总数: {len(all_icons)}")

        by_provider = manager.list_icons_by_provider()
        for provider, icons in by_provider.items():
            print(f"  {provider}: {len(icons)} 个")

        print()
        print(f"  前 20 个图标: {all_icons[:20]}")
        print()

        # 测试单例
        print("=== 测试单例 ===")
        manager2 = get_icon_manager()
        print(f"  同一实例: {manager is manager2}")
        print()

        print("测试完成。")

    finally:
        # 清理
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)

    sys.exit(0)
