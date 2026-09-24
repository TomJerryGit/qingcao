#-*- coding: utf-8 -*-
"""青草编辑器导出模块"""
import os
import datetime


class Exporter:
    """导出器"""

    @staticmethod
    def to_html(text, title="Untitled", language="text"):
        """导出为 HTML"""
        import html as html_mod
        escaped = html_mod.escape(text)
        esc_title = html_mod.escape(title)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        char_count = len(text)

        lines = []
        lines.append('<!DOCTYPE html>')
        lines.append('<html lang="zh-CN">')
        lines.append('<head>')
        lines.append('<meta charset="UTF-8">')
        lines.append('<title>' + esc_title + '</title>')
        lines.append('<style>')
        lines.append('body {')
        lines.append('  font-family: Consolas, Microsoft YaHei, monospace;')
        lines.append('  background: #1e1e1e; color: #d4d4d4;')
        lines.append('  padding: 20px; line-height: 1.6;')
        lines.append('}')
        lines.append('pre {')
        lines.append('  background: #252526; padding: 15px;')
        lines.append('  border-radius: 5px; overflow-x: auto;')
        lines.append('  border-left: 3px solid #7ec850;')
        lines.append('}')
        lines.append('h1 { color: #7ec850; border-bottom: 2px solid #7ec850;')
        lines.append('     padding-bottom: 10px; }')
        lines.append('.meta { color: #888; font-size: 12px;')
        lines.append('        margin-bottom: 20px; }')
        lines.append('</style>')
        lines.append('</head>')
        lines.append('<body>')
        lines.append('<h1>' + esc_title + '</h1>')
        lines.append('<div class="meta">')
        lines.append('导出时间: ' + now + ' | 语言: ' + language)
        lines.append(' | 字符数: ' + str(char_count))
        lines.append('</div>')
        lines.append('<pre>' + escaped + '</pre>')
        lines.append('</body>')
        lines.append('</html>')
        return '\n'.join(lines)

    @staticmethod
    def to_markdown(text, title="Untitled", language="text"):
        """导出为 Markdown"""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        char_count = len(text)

        lines = []
        lines.append('# ' + title)
        lines.append('')
        lines.append('> 导出时间: ' + now)
        lines.append('> 语言: ' + language)
        lines.append('> 字符数: ' + str(char_count))
        lines.append('')
        lines.append('```' + language)
        lines.append(text)
        lines.append('```')
        lines.append('')
        return '\n'.join(lines)

    @staticmethod
    def session_to_markdown(tabs_data):
        """把打开的标签导出为 Markdown 报告"""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = []
        lines.append('# 青草编辑器 - 会话报告')
        lines.append('')
        lines.append('> 导出时间: ' + now)
        lines.append('> 文件数: ' + str(len(tabs_data)))
        lines.append('')
        lines.append('---')
        lines.append('')

        for i, info in enumerate(tabs_data, 1):
            title = info.get('title', '未命名')
            filepath = info.get('filepath') or '(未保存)'
            encoding = info.get('encoding', 'utf-8')
            line_count = info.get('line_count', 0)
            char_count = info.get('char_count', 0)
            modified = '是' if info.get('modified') else '否'

            lines.append('## ' + str(i) + '. ' + title)
            lines.append('')
            lines.append('- **路径**: `' + filepath + '`')
            lines.append('- **编码**: ' + encoding)
            lines.append('- **行数**: ' + str(line_count))
            lines.append('- **字符数**: ' + str(char_count))
            lines.append('- **修改**: ' + modified)
            lines.append('')

            preview = info.get('preview', '')
            if preview:
                lines.append('### 预览')
                lines.append('')
                lines.append('```')
                lines.append(preview[:500])
                lines.append('```')
                lines.append('')

            lines.append('---')
            lines.append('')

        return '\n'.join(lines)

    @staticmethod
    def to_pdf(text, output_path, title="Untitled"):
        """导出为 PDF（需要 reportlab）"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
        except ImportError:
            return False, "需要安装 reportlab: pip install reportlab"

        try:
            c = canvas.Canvas(output_path, pagesize=A4)
            width, height = A4

            c.setFont("Helvetica-Bold", 16)
            c.drawString(2 * cm, height - 2 * cm, title)

            c.setFont("Courier", 9)
            y = height - 3 * cm
            line_height = 0.4 * cm

            for line in text.split('\n'):
                if y < 2 * cm:
                    c.showPage()
                    c.setFont("Courier", 9)
                    y = height - 2 * cm

                while len(line) > 100:
                    c.drawString(2 * cm, y, line[:100])
                    line = line[100:]
                    y -= line_height
                    if y < 2 * cm:
                        c.showPage()
                        c.setFont("Courier", 9)
                        y = height - 2 * cm

                c.drawString(2 * cm, y, line)
                y -= line_height

            c.save()
            return True, "已导出到: " + output_path
        except Exception as e:
            return False, str(e)