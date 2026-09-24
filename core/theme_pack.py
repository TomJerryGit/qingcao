# -*- coding: utf-8 -*-
"""主题包导入/导出"""
import os
import json
import zipfile
import shutil
from typing import Optional, Dict, Any


class ThemePack:
    """主题包"""

    @staticmethod
    def export_theme(theme_path, output_path):
        """
        导出主题为 zip 包

        参数:
            theme_path: 主题 json 文件路径
            output_path: 输出 zip 路径
        """
        try:
            if not os.path.exists(theme_path):
                return False, "主题文件不存在"

            with open(theme_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 元数据
            meta = {
                'name': data.get('name', ''),
                'display_name': data.get('display_name', ''),
                'author': data.get('author', ''),
                'version': data.get('version', '1.0.0'),
                'description': data.get('description', ''),
                'type': 'qingcao-theme',
                'format_version': 1,
            }

            with zipfile.ZipFile(output_path, 'w',
                                  zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('theme.json',
                            json.dumps(data, indent=2,
                                       ensure_ascii=False))
                zf.writestr('meta.json',
                            json.dumps(meta, indent=2,
                                       ensure_ascii=False))

            return True, "已导出到: " + output_path
        except Exception as e:
            return False, str(e)

    @staticmethod
    def import_theme(zip_path, themes_dir="themes"):
        """
        导入主题包

        参数:
            zip_path: 主题包路径
            themes_dir: 主题目录

        返回:
            (成功, 消息)
        """
        try:
            if not os.path.exists(zip_path):
                return False, "文件不存在"

            with zipfile.ZipFile(zip_path, 'r') as zf:
                names = zf.namelist()
                if 'theme.json' not in names:
                    return False, "无效的主题包（缺少 theme.json）"

                data = json.loads(zf.read('theme.json'))

                name = data.get('name', '')
                if not name:
                    return False, "主题缺少 name 字段"

                # 清理文件名
                safe_name = "".join(
                    c if c.isalnum() or c in '_-' else '_'
                    for c in name
                )

                os.makedirs(themes_dir, exist_ok=True)
                target = os.path.join(themes_dir, safe_name + '.json')

                with open(target, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                return True, "已导入: " + name
        except zipfile.BadZipFile:
            return False, "文件格式错误"
        except Exception as e:
            return False, str(e)