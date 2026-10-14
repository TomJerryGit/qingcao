#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""配置管理"""
import json
import os
import shutil
import zipfile

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog, QMessageBox


class ConfigManager:
    """配置导入/导出管理器"""

    def __init__(self):
        self.settings = QSettings("QingCao", "Editor")

    def export_config(self, parent=None, filepath=None):
        """导出配置"""
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(
                parent, "导出配置", "qingcao_config.zip",
                "ZIP (*.zip)"
            )
        if not filepath:
            return False

        try:
            data = {
                'preferences': {
                    'font_family': self.settings.value('font_family', ''),
                    'font_size': self.settings.value('font_size', 12),
                    'tab_width': self.settings.value('tab_width', 4),
                },
                'keybindings': {},
                'plugins': [],
            }

            # 读取快捷键
            try:
                if os.path.exists('keybindings.json'):
                    with open('keybindings.json', encoding='utf-8') as f:
                        data['keybindings'] = json.load(f)
            except Exception:
                pass

            # 读取插件列表
            #
            # 用绝对路径：相对路径取决于当前工作目录，从快捷方式/其他目录
            # 启动时会扫描不到插件（实测 cwd=exe 目录能找到、cwd=C:\ 找不到）。
            try:
                from infrastructure.plugin_loader import resolve_plugin_dir
                _pdir = resolve_plugin_dir('plugins')
            except Exception:
                _pdir = 'plugins'
            try:
                if os.path.isdir(_pdir):
                    data['plugins'] = [
                        d for d in os.listdir(_pdir)
                        if os.path.isdir(os.path.join(_pdir, d))
                    ]
            except Exception:
                pass

            with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('config.json',
                            json.dumps(data, indent=2, ensure_ascii=False))

            if parent:
                QMessageBox.information(parent, "成功", "配置已导出")
            return True

        except Exception as e:
            if parent:
                QMessageBox.critical(parent, "导出失败", str(e))
            return False

    def import_config(self, parent=None, filepath=None):
        """导入配置"""
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(
                parent, "导入配置", "", "ZIP (*.zip)"
            )
        if not filepath:
            return False

        try:
            with zipfile.ZipFile(filepath, 'r') as zf:
                data = json.loads(zf.read('config.json'))

            prefs = data.get('preferences', {})
            for k, v in prefs.items():
                if v:
                    self.settings.setValue(k, v)

            if data.get('keybindings'):
                with open('keybindings.json', 'w', encoding='utf-8') as f:
                    json.dump(data['keybindings'], f, indent=2,
                              ensure_ascii=False)

            if parent:
                QMessageBox.information(
                    parent, "成功",
                    "配置已导入，重启编辑器后生效"
                )
            return True

        except Exception as e:
            if parent:
                QMessageBox.critical(parent, "导入失败", str(e))
            return False