# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""提供者工厂（v2.24 拆出）。"""
from core.content_provider_base import ContentProvider
from core.content_provider_common import *  # noqa: F401,F403,F405
from core.content_provider_local import LocalFileProvider
from core.content_provider_memory import MemoryProvider
from core.content_provider_stream import StreamProvider


class ProviderFactory:
    """
    内容提供者工厂。

    根据源类型自动选择合适的提供者。
    """

    _registry: Dict[str, type] = {
        'local': LocalFileProvider,
        'memory': MemoryProvider,
        'stream': StreamProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class: type):
        """注册自定义提供者"""
        cls._registry[name] = provider_class

    @classmethod
    def create(cls, kind: str = 'local', **kwargs) -> ContentProvider:
        """
        根据类型创建提供者。

        参数:
            kind: 提供者类型（local / memory / stream）
            **kwargs: 传递给构造函数的参数

        返回:
            ContentProvider 实例
        """
        provider_class = cls._registry.get(kind)
        if provider_class is None:
            raise ValueError(f"未知的提供者类型: {kind}")
        return provider_class(**kwargs)

    @classmethod
    def create_for_file(cls, filepath: str, **kwargs) -> ContentProvider:
        """
        根据文件自动创建提供者。

        参数:
            filepath: 文件路径
            **kwargs: 额外参数

        返回:
            ContentProvider 实例
        """
        provider = LocalFileProvider()
        provider.open(filepath, **kwargs)
        return provider

    @classmethod
    def list_types(cls) -> List[str]:
        """列出所有已注册的提供者类型"""
        return list(cls._registry.keys())


# ============================================================
# 辅助函数
# ============================================================
def detect_file_encoding(filepath: str, sample_size: int = 4096) -> str:
    """
    检测文件编码（无需打开完整文件）。

    参数:
        filepath: 文件路径
        sample_size: 采样字节数

    返回:
        编码名称
    """
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)

        # BOM 检测
        for bom, enc in BOMS.items():
            if sample.startswith(bom):
                return enc

        # chardet 检测
        try:
            import chardet
            result = chardet.detect(sample)
            if result and result.get('confidence', 0) > 0.7:
                return result['encoding'].lower()
        except ImportError:
            pass

        # 简单启发式
        try:
            sample.decode('utf-8')
            return ENCODING_UTF8
        except UnicodeDecodeError:
            pass

        try:
            sample.decode('gbk')
            return ENCODING_GBK
        except UnicodeDecodeError:
            pass

        return ENCODING_LATIN1
    except Exception:
        return ENCODING_UTF8


def detect_file_eol(filepath: str, sample_size: int = 4096) -> str:
    """检测文件行尾符"""
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)
        crlf = sample.count(b'\r\n')
        lf = sample.count(b'\n') - crlf
        cr = sample.count(b'\r') - crlf
        if crlf >= lf and crlf >= cr:
            return EOL_CRLF
        elif cr > lf:
            return EOL_CR
        return EOL_LF
    except Exception:
        return EOL_LF


def is_binary_file(filepath: str, sample_size: int = 1024) -> bool:
    """
    检测文件是否为二进制。

    ★ 修复（混合场景压测实测发现）：原实现是"样本里有 NUL 字节 → 二进制"，
    于是**所有 UTF-16 / UTF-32 文本都被判成二进制**：
    ASCII 字符在 UTF-16 里就是 `61 00 62 00 ...`，换行 `0A 00` 也是 NUL 满布。

    实测后果（`app/tabs.py` 的打开路径会用它做拦截）：

        打开一个正常的 UTF-16 文本 → 弹「文件可能包含二进制内容，确定要打开吗？」
        → 用户选「否」→ **文件打不开**。

    现在改为 `is_binary_sample()` 的多级判断：
      1. 有文本 BOM → 一定是文本；
      2. 能按 UTF-8 严格解码 → 文本；
      3. 能按 UTF-16 LE/BE 解码且可打印比例高 → 文本；
      4. 否则看 NUL 比例（>5% 判二进制）。
    """
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)
        return is_binary_sample(sample)
    except Exception:
        return False


def is_binary_sample(sample: bytes, sample_limit: int = 1024) -> bool:
    """根据内容样本判断是否二进制（`is_binary_file` 的实现，便于单测）"""
    if not sample:
        return False
    sample = sample[:sample_limit]

    # 1) 文本 BOM → 明确是文本（UTF-16/32 的 NUL 是正常现象）
    for bom in BOMS:
        if sample.startswith(bom):
            return False

    # 2) 严格 UTF-8 可解码 → 文本（注意样本可能截断多字节字符，
    #    因此末尾最多回退 3 字节再试）
    for trim in range(0, 4):
        chunk = sample[:len(sample) - trim] if trim else sample
        try:
            chunk.decode(ENCODING_UTF8, errors='strict')
            return False
        except UnicodeDecodeError:
            continue

    # 3) 无 BOM 的 UTF-16：NUL 集中在同一奇偶位，且能解码出可打印文本
    if _looks_like_utf16(sample):
        return False

    # 4) 否则看 NUL 比例（二进制里 NUL 通常很多）
    nul = sample.count(b'\x00')
    return bool(nul) and (nul / len(sample)) > 0.05


def _looks_like_utf16(sample: bytes) -> bool:
    """判断样本是否像（无 BOM 的）UTF-16 文本"""
    if len(sample) < 4:
        return False
    even_nul = sum(1 for i in range(0, len(sample), 2) if sample[i] == 0)
    odd_nul = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
    half = max(1, len(sample) // 2)
    ratio = max(even_nul, odd_nul) / half
    if ratio < 0.3:
        return False
    # NUL 集中在一侧 → 尝试用对应端序解码，并要求可打印比例够高
    enc = ENCODING_UTF16_BE if even_nul > odd_nul else ENCODING_UTF16_LE
    if len(sample) % 2:
        sample = sample[:-1]
    try:
        text = sample.decode(enc, errors='strict')
    except (UnicodeDecodeError, LookupError):
        return False
    if not text:
        return False
    printable = sum(1 for ch in text
                    if ch.isprintable() or ch in '\r\n\t')
    return printable / len(text) > 0.9


def get_file_hash(filepath: str, algorithm: str = 'sha256',
                  chunk_size: int = 8192) -> Optional[str]:
    """
    计算文件哈希。

    参数:
        filepath: 文件路径
        algorithm: 哈希算法
        chunk_size: 分块读取大小

    返回:
        十六进制哈希值或 None
    """
    try:
        h = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    print("=== 测试 LocalFileProvider ===")

    # 创建临时测试文件
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_provider_test_")
    test_file = os.path.join(tmp_dir, "test.txt")

    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("Hello, 青草编辑器!\n")
        f.write("测试内容，包含中文。\n")
        f.write("Line 3: 继续测试。\n")

    provider = LocalFileProvider()
    provider.open(test_file)

    print(f"提供者: {provider}")
    print(f"文件信息: {provider.get_file_info()}")
    print(f"编码: {provider.encoding}")
    print(f"行尾符: {repr(provider.eol)}")
    print(f"总块数: {provider.total_blocks}")
    print(f"大小: {provider.size} 字节")
    print()

    # 读取全部内容
    text = provider.read_text()
    print(f"内容:\n{text}")

    # 修改块 0
    print("=== 测试写入 ===")
    original = provider.read_block(0)
    new_data = "修改后的内容!\n".encode('utf-8')
    provider.write_block(0, new_data)
    print(f"脏块数: {provider.dirty_block_count}")
    print(f"状态: {provider.state.name}")

    # 保存
    print(f"保存: {provider.save()}")
    print(f"状态: {provider.state.name}")

    # 重新读取验证
    with open(test_file, encoding='utf-8') as f:
        print(f"保存后文件内容: {f.read()}")

    # 测试外部变更检测
    print(f"外部变更检测: {provider.check_external_change()}")

    provider.close()
    print()

    print("=== 测试 MemoryProvider ===")
    mem = MemoryProvider()
    mem.open(initial_text="内存中的文本\n第二行\n")
    print(f"提供者: {mem}")
    print(f"文本: {mem.get_text()}")
    print(f"大小: {mem.size} 字节")
    # 关键：验证基类默认方法
    print(f"check_external_change: {mem.check_external_change()}")
    print(f"reload: {mem.reload()}")

    mem.write_block(0, "新内容".encode('utf-8'))
    print(f"修改后文本: {mem.get_text()}")

    # 另存为
    memory_file = os.path.join(tmp_dir, "from_memory.txt")
    print(f"另存为: {mem.save(memory_file)}")
    print(f"文件存在: {os.path.exists(memory_file)}")
    mem.close()
    print()

    print("=== 测试辅助函数 ===")
    print(f"检测编码: {detect_file_encoding(test_file)}")
    print(f"检测行尾: {repr(detect_file_eol(test_file))}")
    print(f"是否二进制: {is_binary_file(test_file)}")
    print(f"文件哈希: {get_file_hash(test_file)}")

    print()
    print(f"已注册的提供者: {ProviderFactory.list_types()}")

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("测试完成。")
