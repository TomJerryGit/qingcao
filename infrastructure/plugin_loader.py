# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""插件加载器（v2.24 拆分：common/loader）。"""

from infrastructure.plugin_loader_common import *  # noqa: F401,F403


class PluginLoader(QObject):
    """
    插件加载器。

    负责:
    - 发现插件目录
    - 解析 manifest
    - 校验依赖与版本
    - 动态导入模块
    - 实例化并激活插件
    - 卸载与清理
    - 异常隔离

    信号:
        plugin_discovered(str): 发现插件（名称）
        plugin_loaded(str): 加载成功（名称）
        plugin_activated(str): 激活成功（名称）
        plugin_unloaded(str): 卸载完成（名称）
        plugin_error(str, str): 加载错误（名称, 错误信息）
        load_finished(object): 加载完成（LoadResult）
    """

    plugin_discovered = pyqtSignal(str)
    plugin_loaded = pyqtSignal(str)
    plugin_activated = pyqtSignal(str)
    plugin_unloaded = pyqtSignal(str)
    plugin_error = pyqtSignal(str, str)
    load_finished = pyqtSignal(object)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        plugin_dir: str = DEFAULT_PLUGIN_DIR,
        enable_watcher: bool = False,
        hot_reload_enabled: bool = True,
    ):
        """
        参数:
            parent: 父 QObject
            plugin_dir: 插件目录
            enable_watcher: 是否启用目录监控
            hot_reload_enabled: P1-2 监控到变更时是否自动重载
                （enable_watcher 必须为 True 才有意义）
        """
        super().__init__(parent)

        # 解析成绝对路径：相对路径会随工作目录变化，导致插件发现为 0
        self.plugin_dir = resolve_plugin_dir(plugin_dir)
        self.enable_watcher = enable_watcher
        self.hot_reload_enabled = hot_reload_enabled

        # 已加载的插件规格
        self.specs: Dict[str, PluginSpec] = {}

        # 加载顺序（用于控制依赖）
        self._load_order: List[str] = []

        # 目录监控
        self._watcher: Optional[QFileSystemWatcher] = None
        self._watch_timer: Optional[QTimer] = None
        self._watch_paths: set = set()
        # P1-2: 每个插件目录的最新 mtime，用于判断哪些插件变了
        self._plugin_mtimes: Dict[str, float] = {}

        # 线程锁（保护 specs 操作）
        self._lock = threading.RLock()

        # 全局 API 工厂（由外部注入）
        self._api_factory: Optional[Callable] = None

    # ========================================================
    # 发现插件
    # ========================================================
    def discover(
        self, plugin_dir: Optional[str] = None, exclude_names: Optional[set] = None
    ) -> List[PluginSpec]:
        """
        扫描插件目录，发现所有插件。

        参数:
            plugin_dir: 插件目录（None 则使用默认）

        返回:
            PluginSpec 列表
        """
        if plugin_dir:
            self.plugin_dir = resolve_plugin_dir(plugin_dir)

        specs = []

        if not os.path.isdir(self.plugin_dir):
            return specs

        try:
            for name in sorted(os.listdir(self.plugin_dir)):
                # 跳过隐藏目录
                if name.startswith("."):
                    continue

                plugin_path = os.path.join(self.plugin_dir, name)

                # 只处理目录
                if not os.path.isdir(plugin_path):
                    continue

                # 跳过模板目录
                if name.startswith("_"):
                    continue

                # B-3c：导入级排除（沙箱插件由子进程加载，主进程不 import）
                if exclude_names and name in exclude_names:
                    continue

                # 解析插件
                spec = self._parse_plugin(plugin_path, name)
                if spec:
                    specs.append(spec)
                    self.plugin_discovered.emit(spec.name)

        except Exception as e:
            print(f"[PluginLoader] 扫描目录失败: {e}")
            traceback.print_exc()

        return specs

    def _parse_plugin(self, plugin_path: str, dir_name: str) -> Optional[PluginSpec]:
        """
        解析单个插件。

        参数:
            plugin_path: 插件目录
            dir_name: 目录名

        返回:
            PluginSpec 或 None
        """
        spec = PluginSpec()
        spec.directory = plugin_path

        # 检查 manifest
        manifest_path = os.path.join(plugin_path, PLUGIN_MANIFEST)

        if not os.path.exists(manifest_path):
            # 无 manifest，使用目录名作为插件名
            meta = PluginMeta(name=dir_name)
            meta.display_name = dir_name
            meta.valid = False
            meta.errors.append("缺少 plugin.json")
            spec.meta = meta
            spec.state = PluginState.ERROR
            spec.error = "缺少 plugin.json"
            return spec

        spec.manifest_path = manifest_path

        # 解析 manifest
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            if not isinstance(manifest, dict):
                raise ValueError("manifest 必须是 JSON 对象")

            meta = PluginMeta.from_dict(manifest)

            # 名称校验：如果不匹配则使用目录名
            if not meta.name:
                meta.name = dir_name

            # 校验
            meta.validate()
            meta.check_app_version()

            spec.meta = meta

            # 检查入口
            entry_path = os.path.join(plugin_path, meta.entry_point)
            if not os.path.exists(entry_path):
                entry_path = os.path.join(plugin_path, PLUGIN_ENTRY)

            if not os.path.exists(entry_path):
                spec.state = PluginState.ERROR
                spec.error = "缺少入口文件"
                meta.valid = False
                meta.errors.append("缺少入口文件")
                return spec

            spec.entry_path = entry_path

            # 检查启用状态
            if not meta.enabled:
                spec.state = PluginState.DISABLED
            elif not meta.valid:
                spec.state = PluginState.ERROR
                spec.error = "; ".join(meta.errors)
            else:
                spec.state = PluginState.DISCOVERED

        except json.JSONDecodeError as e:
            spec.state = PluginState.ERROR
            spec.error = f"plugin.json 解析失败: {e}"
        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = str(e)

        return spec

    # ========================================================
    # 加载插件
    # ========================================================
    def load_all(
        self,
        plugin_dir: Optional[str] = None,
        api_factory: Optional[Callable] = None,
        auto_activate: bool = True,
        defer_names: Optional[set] = None,
        exclude_names: Optional[set] = None,
    ) -> LoadResult:
        """
        加载所有插件。

        参数:
            plugin_dir: 插件目录
            api_factory: 创建插件 API 的工厂函数，接收 PluginSpec 返回 api 对象
            auto_activate: 是否自动激活

        返回:
            LoadResult

        修复说明（P1-6）:
            - 原实现在加载循环结束后才填充 self.specs，导致
              _load_plugin → _check_plugin_dependencies 在遍历
              self.specs 时找不到任何依赖项，任何声明了
              plugin_dependencies 的插件都会失败。
            - 修复：在加载循环之前先用 discover 的结果填充
              self.specs（同时 clear 旧的条目），确保依赖检查
              能正确找到依赖插件。
            - 移除了原末尾的填充逻辑，避免重复赋值。
        """
        start_time = time.time()

        result = LoadResult()

        # 保存 API 工厂
        if api_factory:
            self._api_factory = api_factory

        # 发现插件（exclude_names：沙箱插件不在这里导入）
        specs = self.discover(plugin_dir, exclude_names=exclude_names)
        result.total = len(specs)
        result.specs = specs

        # ====================================================
        # 关键修复（P1-6）：在加载循环之前填充 self.specs
        # ====================================================
        # 说明：
        #   _load_plugin 会调用 _check_plugin_dependencies，
        #   后者遍历 self.specs 检查依赖插件的激活状态。
        #   若此时 self.specs 为空，则所有带依赖的插件都会
        #   因"缺少插件依赖"而失败。
        with self._lock:
            self.specs.clear()
            for spec in specs:
                self.specs[spec.name] = spec

        # 过滤出可加载的插件
        # 修复：DISABLED 状态的插件不进入加载队列
        loadable = [s for s in specs if s.state == PluginState.DISCOVERED]

        # 按 load_order 和依赖排序
        sorted_specs = self._sort_by_dependencies(loadable)

        # ---- 重量级插件延后加载 ----
        # 实测（v2.2 性能）：10 个插件 load_all 共 0.61s，其中
        # `import:ai_assistant` 独占 **0.535s**（模块导入），
        # 而 10 个插件的 activate 合计只有 ~0.09s。
        # 把这类插件从首轮移出，启动后 0.6s 再加载，窗口出现即响应。
        deferred_specs: List[PluginSpec] = []
        if defer_names:
            deferred_specs = [s for s in sorted_specs if s.name in defer_names]
            sorted_specs = [s for s in sorted_specs if s.name not in defer_names]

        # 加载每个插件
        for spec in sorted_specs:
            try:
                success = self._load_plugin(spec)

                if success:
                    result.loaded += 1

                    if auto_activate and spec.meta.auto_load:
                        if self._activate_plugin(spec):
                            result.activated += 1
                        else:
                            result.failed += 1
                            result.errors.append((spec.name, spec.error or "激活失败"))
                else:
                    result.failed += 1
                    result.errors.append((spec.name, spec.error or "加载失败"))

            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = str(e)
                result.failed += 1
                result.errors.append((spec.name, str(e)))

                self.plugin_error.emit(spec.name, str(e))

                traceback.print_exc()

        # 统计（去重）
        for spec in specs:
            if spec.state == PluginState.DISABLED:
                result.disabled += 1
            elif spec.state == PluginState.ERROR:
                if (spec.name, spec.error) not in result.errors:
                    result.failed += 1
                    result.errors.append((spec.name, spec.error))

        result.deferred = deferred_specs
        result.elapsed_ms = (time.time() - start_time) * 1000

        # 更新加载顺序
        self._update_load_order()

        # 发射信号
        self.load_finished.emit(result)

        return result

    def _load_plugin(self, spec: PluginSpec) -> bool:
        """
        加载单个插件（导入模块）。

        参数:
            spec: 插件规格

        返回:
            是否成功
        """
        # 修复：只有 DISCOVERED 状态才能加载
        if spec.state != PluginState.DISCOVERED:
            return False

        if not spec.meta.valid:
            spec.state = PluginState.ERROR
            spec.error = "; ".join(spec.meta.errors)
            return False

        # 检查插件依赖
        if not self._check_plugin_dependencies(spec):
            spec.state = PluginState.ERROR
            spec.error = spec.error or "缺少插件依赖"
            return False

        start_time = time.time()

        try:
            spec.state = PluginState.LOADING

            # 动态导入模块
            module = self._import_module(spec)

            if module is None:
                spec.state = PluginState.ERROR
                spec.error = "模块导入失败"
                return False

            spec.module = module

            spec.state = PluginState.LOADED
            spec.load_time_ms = (time.time() - start_time) * 1000

            self.plugin_loaded.emit(spec.name)

            return True

        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = str(e)
            spec.load_time_ms = (time.time() - start_time) * 1000

            self.plugin_error.emit(spec.name, str(e))

            # 打印堆栈
            traceback.print_exc()

            return False

    def _import_module(self, spec: PluginSpec):
        """
        动态导入插件模块。

        参数:
            spec: 插件规格

        返回:
            模块对象或 None
        """
        try:
            # 生成唯一的模块名
            module_name = f"qingcao_plugin_{spec.name}"

            # 加载入口文件（v2.24：包式插件支持相对导入）
            entry_path = spec.entry_path
            is_package = os.path.basename(entry_path) == "__init__.py"
            loader = importlib.util.spec_from_file_location(
                module_name,
                entry_path,
                submodule_search_locations=([os.path.dirname(entry_path)] if is_package else None),
            )

            if loader is None:
                print(f"[PluginLoader] 无法创建模块加载器: {spec.entry_path}")
                return None

            module = importlib.util.module_from_spec(loader)

            # 将模块添加到 sys.modules（供内部 import 使用）
            sys.modules[module_name] = module

            # 执行模块
            try:
                loader.loader.exec_module(module)
            except SyntaxError as e:
                # 修复：为 GBK 编码错误提供更清晰的提示
                error_msg = str(e)
                if "invalid character" in error_msg or "unicode error" in error_msg.lower():
                    error_msg += (
                        "\n提示：插件源文件可能不是 UTF-8 编码。"
                        "\n请运行 python fix_gbk.py 转换编码，"
                        "或用 VSCode 将文件另存为 UTF-8。"
                    )
                print(f"[PluginLoader] 语法/编码错误 ({spec.name}): {error_msg}")
                # 清理 sys.modules 中的残留
                sys.modules.pop(module_name, None)
                spec.error = error_msg
                return None

            return module

        except Exception as e:
            print(f"[PluginLoader] 导入模块失败 ({spec.name}): {e}")
            traceback.print_exc()
            spec.error = str(e)
            return None

    # ========================================================
    # 激活插件
    # ========================================================
    def load_deferred(self, specs: List[PluginSpec]) -> int:
        """加载并激活"被延后"的插件（启动完成后再执行）

        `load_all(defer_names=...)` 把这些插件留在 DISCOVERED 状态，
        由调用方在窗口显示后用 QTimer 调到这里。返回成功激活数。

        设计约束：
          * 只处理 DISCOVERED 状态，避免重复加载；
          * 单个插件失败不影响其它插件（异常隔离，与 load_all 一致）；
          * 结束时发 `load_finished`，让插件管理面板刷新。
        """
        if not specs:
            return 0
        started = time.time()
        result = LoadResult(total=len(specs), specs=list(specs))
        for spec in specs:
            try:
                if spec.state != PluginState.DISCOVERED:
                    continue
                if not self._load_plugin(spec):
                    result.failed += 1
                    result.errors.append((spec.name, spec.error or "加载失败"))
                    self.plugin_error.emit(spec.name, spec.error or "加载失败")
                    continue
                result.loaded += 1
                if spec.meta.auto_load and self._activate_plugin(spec):
                    result.activated += 1
                else:
                    result.failed += 1
                    result.errors.append((spec.name, spec.error or "激活失败"))
            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = str(e)
                result.failed += 1
                result.errors.append((spec.name, str(e)))
                self.plugin_error.emit(spec.name, str(e))
                traceback.print_exc()
        result.elapsed_ms = (time.time() - started) * 1000
        self._update_load_order()
        self.load_finished.emit(result)
        print("[PluginLoader] 延后加载完成: %s" % result.get_summary())
        return result.activated

    def _activate_plugin(self, spec: PluginSpec) -> bool:
        """
        激活插件。

        参数:
            spec: 插件规格

        返回:
            是否成功

        修复说明:
            - 显式检查 api 是否为 None
            - 使用 try/except 包裹 activate() 调用
            - 失败时给出完整堆栈
        """
        # 修复：只允许 LOADED 状态进入
        if spec.state != PluginState.LOADED:
            return False

        if not spec.module:
            spec.state = PluginState.ERROR
            spec.error = "模块未加载"
            return False

        try:
            # 获取 Plugin 类
            plugin_class = getattr(spec.module, spec.meta.main_class, None)

            if plugin_class is None:
                spec.state = PluginState.ERROR
                spec.error = f"未找到 {spec.meta.main_class} 类"
                self.plugin_error.emit(spec.name, spec.error)
                return False

            # 创建插件 API
            api = self._create_api(spec)

            # 修复：显式检查 api
            if api is None:
                spec.state = PluginState.ERROR
                spec.error = "无法创建插件 API（api_factory 返回 None）"
                self.plugin_error.emit(spec.name, spec.error)
                return False

            spec.api = api

            # 实例化插件
            try:
                plugin_instance = plugin_class()
            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = f"实例化插件类失败: {e}"
                self.plugin_error.emit(spec.name, str(e))
                traceback.print_exc()
                return False

            spec.instance = plugin_instance

            # 调用 activate
            try:
                plugin_instance.activate(api)
            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = f"activate() 失败: {e}"
                self.plugin_error.emit(spec.name, str(e))
                traceback.print_exc()

                # 尝试回滚
                try:
                    if hasattr(plugin_instance, "deactivate"):
                        plugin_instance.deactivate()
                except Exception:
                    pass

                return False

            # 成功
            spec.state = PluginState.ACTIVATED
            spec.activated_at = time.time()

            self.plugin_activated.emit(spec.name)

            # 发布事件
            try:
                from app.event_bus import PluginLoadedEvent, bus

                bus.emit_event(
                    PluginLoadedEvent(
                        plugin_name=spec.name,
                        version=spec.version,
                        load_time_ms=spec.load_time_ms,
                    )
                )
            except Exception:
                pass

            return True

        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = f"激活异常: {e}"

            self.plugin_error.emit(spec.name, str(e))

            # 打印堆栈
            traceback.print_exc()

            return False

    def _create_api(self, spec: PluginSpec):
        """
        创建插件 API。

        修复说明:
            - 检查工厂函数的返回值是否为 None
            - 捕获工厂函数内部的异常
        """
        if self._api_factory:
            try:
                api = self._api_factory(spec)
                if api is None:
                    print(f"[PluginLoader] api_factory 返回 None ({spec.name})")
                return api
            except Exception as e:
                print(f"[PluginLoader] 创建 API 失败 ({spec.name}): {e}")
                traceback.print_exc()

        # 回退：返回 None
        return None

    # ========================================================
    # 依赖检查与排序
    # ========================================================
    def _check_plugin_dependencies(self, spec: PluginSpec) -> bool:
        """
        检查插件依赖是否已加载。

        修复说明（P1-6）:
            - 本方法依赖 self.specs 已被 load_all 提前填充。
              若 load_all 在循环结束才填充，则此处的查找会
              永远失败。
        """
        if not spec.meta.plugin_dependencies:
            return True

        with self._lock:
            for dep_name in spec.meta.plugin_dependencies:
                dep_spec = self.specs.get(dep_name)
                if dep_spec is None or not dep_spec.is_active:
                    # 依赖未激活
                    if dep_spec is None:
                        spec.error = f"缺少插件依赖: {dep_name}"
                    else:
                        spec.error = f"依赖插件 {dep_name} 未激活"
                    return False

        return True

    def _sort_by_dependencies(self, specs: List[PluginSpec]) -> List[PluginSpec]:
        """
        按依赖关系拓扑排序。

        参数:
            specs: 插件规格列表

        返回:
            排序后的列表
        """
        # 构建依赖图
        name_to_spec = {s.name: s for s in specs}

        # 计算加载顺序
        visited: Set[str] = set()
        result: List[PluginSpec] = []
        visiting: Set[str] = set()

        def visit(spec: PluginSpec):
            if spec.name in visited:
                return

            if spec.name in visiting:
                # 检测到循环依赖
                print(f"[PluginLoader] 检测到循环依赖: {spec.name}")
                return

            visiting.add(spec.name)

            # 先访问依赖
            for dep_name in spec.meta.plugin_dependencies:
                dep_spec = name_to_spec.get(dep_name)
                if dep_spec:
                    visit(dep_spec)

            visiting.discard(spec.name)

            if spec.name not in visited:
                visited.add(spec.name)
                result.append(spec)

        # 按 load_order 排序
        sorted_specs = sorted(specs, key=lambda s: s.meta.load_order)

        for spec in sorted_specs:
            visit(spec)

        return result

    def _update_load_order(self):
        """更新加载顺序列表"""
        with self._lock:
            activated = [name for name, spec in self.specs.items() if spec.is_active]
            self._load_order = activated

    # ========================================================
    # 卸载插件
    # ========================================================
    def unload_plugin(self, name: str) -> bool:
        """
        卸载单个插件。

        参数:
            name: 插件名

        返回:
            是否成功
        """
        with self._lock:
            spec = self.specs.get(name)

        if not spec:
            return False

        try:
            # 调用 deactivate
            if spec.instance and hasattr(spec.instance, "deactivate"):
                try:
                    spec.instance.deactivate()
                except Exception as e:
                    print(f"[PluginLoader] deactivate 失败 ({name}): {e}")

            # 清理 API 资源
            if spec.api and hasattr(spec.api, "cleanup"):
                try:
                    spec.api.cleanup()
                except Exception as e:
                    print(f"[PluginLoader] API cleanup 失败: {e}")

            # 从 sys.modules 中移除
            module_name = f"qingcao_plugin_{name}"
            if module_name in sys.modules:
                try:
                    del sys.modules[module_name]
                except Exception:
                    pass

            spec.state = PluginState.UNLOADED

            self.plugin_unloaded.emit(name)

            # 发布事件
            try:
                from app.event_bus import PluginUnloadedEvent, bus

                bus.emit_event(
                    PluginUnloadedEvent(
                        plugin_name=name,
                        version=spec.version,
                    )
                )
            except Exception:
                pass

            return True

        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = f"卸载失败: {e}"
            traceback.print_exc()
            return False

    def unload_all(self) -> int:
        """
        卸载所有插件。

        返回:
            卸载数量
        """
        count = 0

        # 逆序卸载（先加载的后卸载）
        names = list(reversed(self._load_order))

        for name in names:
            if self.unload_plugin(name):
                count += 1

        return count

    def reload_plugin(self, name: str) -> bool:
        """
        重新加载单个插件。

        参数:
            name: 插件名

        返回:
            是否成功
        """
        with self._lock:
            spec = self.specs.get(name)

        if not spec:
            return False

        # 保存路径
        directory = spec.directory

        # 卸载
        self.unload_plugin(name)

        # 重新解析
        dir_name = os.path.basename(directory)
        new_spec = self._parse_plugin(directory, dir_name)

        if not new_spec:
            return False

        # 加载
        if self._load_plugin(new_spec):
            if self._activate_plugin(new_spec):
                with self._lock:
                    self.specs[name] = new_spec
                return True

        return False

    # ========================================================
    # 查询
    # ========================================================
    def get_plugin(self, name: str) -> Optional[PluginSpec]:
        """获取插件规格"""
        with self._lock:
            return self.specs.get(name)

    def get_all_plugins(self) -> List[PluginSpec]:
        """获取所有插件"""
        with self._lock:
            return list(self.specs.values())

    def get_activated_plugins(self) -> List[PluginSpec]:
        """获取所有已激活的插件"""
        with self._lock:
            return [s for s in self.specs.values() if s.is_active]

    def get_plugin_names(self) -> List[str]:
        """获取所有插件名称"""
        with self._lock:
            return list(self.specs.keys())

    def is_loaded(self, name: str) -> bool:
        """检查插件是否已加载"""
        with self._lock:
            spec = self.specs.get(name)
            return spec is not None and spec.is_loaded

    def is_active(self, name: str) -> bool:
        """检查插件是否已激活"""
        with self._lock:
            spec = self.specs.get(name)
            return spec is not None and spec.is_active

    def get_plugin_count(self) -> int:
        """获取插件总数"""
        with self._lock:
            return len(self.specs)

    def get_load_order(self) -> List[str]:
        """获取加载顺序"""
        return list(self._load_order)

    # ========================================================
    # 目录监控（热重载）
    # ========================================================
    def start_watching(self):
        """启动目录监控（P1-2: 支持真正的热重载）"""
        if not self.enable_watcher:
            return

        if self._watcher is not None:
            return

        try:
            self._watcher = QFileSystemWatcher(self)
            # 监控插件根目录，以及每个已发现插件目录内的文件
            self._watch_paths = set()
            self._add_watch_path(self.plugin_dir)
            # P1-2: 递归登记插件子目录与源文件，
            # 否则 QFileSystemWatcher 只会报告根目录变化，
            # 修改某个插件的 __init__.py 不会触发重载。
            self._refresh_watch_paths()

            # 延迟重载定时器（防抖）
            self._watch_timer = QTimer(self)
            self._watch_timer.setSingleShot(True)
            self._watch_timer.setInterval(RELOAD_DEBOUNCE_MS)
            self._watch_timer.timeout.connect(self._on_directory_changed)

            self._watcher.directoryChanged.connect(lambda p: self._watch_timer.start())
            self._watcher.fileChanged.connect(lambda p: self._watch_timer.start())

        except Exception as e:
            print(f"[PluginLoader] 启动监控失败: {e}")

    def _add_watch_path(self, path: str):
        """把路径加入 QFileSystemWatcher（去重，统一绝对路径）"""
        if not self._watcher or not path:
            return
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return
        if not hasattr(self, "_watch_paths"):
            self._watch_paths = set()
        if path in self._watch_paths:
            return
        try:
            if self._watcher.addPath(path):
                self._watch_paths.add(path)
        except Exception:
            pass

    def _refresh_watch_paths(self):
        """重新扫描插件目录，把变更的文件纳入监控"""
        if not self._watcher:
            return
        self._add_watch_path(self.plugin_dir)
        try:
            for name in os.listdir(self.plugin_dir):
                d = os.path.join(self.plugin_dir, name)
                if not os.path.isdir(d):
                    continue
                self._add_watch_path(d)
                for fname in os.listdir(d):
                    # 只监控源码与清单，避免 __pycache__ 噪声
                    if fname.endswith((".py", ".json")):
                        self._add_watch_path(os.path.join(d, fname))
        except Exception as e:
            print(f"[PluginLoader] 刷新监控路径失败: {e}")

    def stop_watching(self):
        """停止目录监控"""
        if self._watcher:
            try:
                self._watcher.deleteLater()
            except Exception:
                pass
            self._watcher = None

        if self._watch_timer:
            self._watch_timer.stop()

    def _on_directory_changed(self):
        """目录/文件变化回调（P1-2: 真正的热重载）

        P1-2 修复：原实现只有一句
            print("[PluginLoader] 插件目录已变化，可能需要重启编辑器")
        即 README 宣称的"修改插件代码后无需重启"实际不成立。

        现在：默认对变化的插件执行 unload + load + activate；
        可在 plugin.json 中设置 "hot_reload": false 让单个插件
        退出热重载（例如需要保持长连接的插件）。
        """
        changed = self._detect_changed_plugins()
        self._refresh_watch_paths()

        if not changed:
            return

        if not self.hot_reload_enabled:
            print(
                "[PluginLoader] 检测到插件变更: %s"
                "（热重载已关闭，请手动重载）" % ", ".join(sorted(changed))
            )
            return

        for name in sorted(changed):
            spec = self.specs.get(name)
            if spec is None:
                # 新出现的插件目录：重新发现一次
                print(f"[PluginLoader] 发现新插件目录: {name}")
                self.discover()
                self._refresh_watch_paths()
                continue

            if not self._is_hot_reload_allowed(spec):
                print(f"[PluginLoader] {name} 声明 hot_reload=false，跳过")
                continue

            print(f"[PluginLoader] 热重载插件: {name}")
            try:
                self.reload_plugin(name)
            except Exception as e:
                print(f"[PluginLoader] 热重载 {name} 失败: {e}")
                self.plugin_error.emit(name, str(e))

    def _detect_changed_plugins(self) -> set:
        """通过 mtime 判断哪些插件目录内容发生了变化"""
        changed = set()
        try:
            for name in os.listdir(self.plugin_dir):
                d = os.path.join(self.plugin_dir, name)
                if not os.path.isdir(d):
                    continue
                latest = 0.0
                for fname in os.listdir(d):
                    if not fname.endswith((".py", ".json")):
                        continue
                    try:
                        latest = max(latest, os.path.getmtime(os.path.join(d, fname)))
                    except OSError:
                        continue
                prev = self._plugin_mtimes.get(name)
                if prev is None:
                    self._plugin_mtimes[name] = latest
                elif latest > prev:
                    self._plugin_mtimes[name] = latest
                    changed.add(name)
        except Exception as e:
            print(f"[PluginLoader] 检测插件变更失败: {e}")
        return changed

    def _is_hot_reload_allowed(self, spec) -> bool:
        """插件是否允许热重载（plugin.json 的 hot_reload 字段）"""
        try:
            raw = getattr(spec.meta, "raw", None) or {}
            return bool(raw.get("hot_reload", True))
        except Exception:
            return True

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出加载器信息"""
        lines = ["PluginLoader", "=" * 60]
        lines.append(f"插件目录: {self.plugin_dir}")
        lines.append(f"插件数量: {len(self.specs)}")
        lines.append(f"激活数量: {len(self.get_activated_plugins())}")
        lines.append(f"加载顺序: {self._load_order}")
        lines.append("")

        if self.specs:
            lines.append("插件列表:")
            for name, spec in sorted(self.specs.items()):
                state_marker = {
                    PluginState.ACTIVATED: "✓",
                    PluginState.LOADED: "◐",
                    PluginState.DISABLED: "⊘",
                    PluginState.ERROR: "✗",
                    PluginState.UNLOADED: "−",
                }.get(spec.state, "?")

                lines.append(f"  {state_marker} {name:25s} v{spec.version:10s} {spec.state.name}")

                if spec.error:
                    lines.append(f"      错误: {spec.error}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<PluginLoader plugins={len(self.specs)} "
            f"activated={len(self.get_activated_plugins())}>"
        )


# ============================================================
# 便捷函数
# ============================================================


def create_loader(plugin_dir: str = DEFAULT_PLUGIN_DIR) -> PluginLoader:
    """创建插件加载器"""
    return PluginLoader(plugin_dir=plugin_dir)


def discover_plugins(plugin_dir: str = DEFAULT_PLUGIN_DIR) -> List[PluginSpec]:
    """
    快速发现插件（无需加载）。

    参数:
        plugin_dir: 插件目录

    返回:
        PluginSpec 列表
    """
    loader = PluginLoader(plugin_dir=plugin_dir)
    return loader.discover()


def load_plugins(
    plugin_dir: str = DEFAULT_PLUGIN_DIR, api_factory: Optional[Callable] = None
) -> LoadResult:
    """
    快速加载所有插件。

    参数:
        plugin_dir: 插件目录
        api_factory: API 工厂函数

    返回:
        LoadResult
    """
    loader = PluginLoader(plugin_dir=plugin_dir)
    return loader.load_all(plugin_dir, api_factory=api_factory)


# ============================================================
# 模块测试
# ============================================================
