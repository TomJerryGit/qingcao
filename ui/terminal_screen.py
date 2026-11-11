# -*- coding: utf-8 -*-
"""轻量 ANSI/VT 屏幕模拟器（v2.25 P2：alt-screen / 光标 / 清屏 / 颜色）。"""

import html
import unicodedata


FG = {
    30: "#000000",
    31: "#cd3131",
    32: "#0dbc79",
    33: "#e5e510",
    34: "#2472c8",
    35: "#bc3fbc",
    36: "#11a8cd",
    37: "#e5e5e5",
    90: "#666666",
    91: "#f14c4c",
    92: "#23d18b",
    93: "#f5f543",
    94: "#3b8eea",
    95: "#d670d6",
    96: "#29b8db",
    97: "#ffffff",
}
BG = {
    40: "#000000",
    41: "#cd3131",
    42: "#0dbc79",
    43: "#e5e510",
    44: "#2472c8",
    45: "#bc3fbc",
    46: "#11a8cd",
    47: "#e5e5e5",
    100: "#666666",
    101: "#f14c4c",
    102: "#23d18b",
    103: "#f5f543",
    104: "#3b8eea",
    105: "#d670d6",
    106: "#29b8db",
    107: "#ffffff",
}


def _width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


class TerminalScreen:
    """字符网格 + VT 子集解析；feed() 输入字节，render_html() 输出 HTML。"""

    def __init__(self, rows=30, cols=100):
        self.rows = max(1, int(rows))
        self.cols = max(1, int(cols))
        self.alt = False
        self._saved = None
        self._state = "text"
        self._params = ""
        self._osc_esc = False
        self._reset_grid()
        self.r = 0
        self.c = 0
        self.fg = None
        self.bg = None
        self.bold = False

    # ---- 基础 ----
    def _blank(self):
        return (" ", None, None, False)

    def _reset_grid(self):
        self.grid = [[self._blank() for _ in range(self.cols)] for _ in range(self.rows)]

    def clear(self):
        self._reset_grid()
        self.r = self.c = 0

    def resize(self, rows, cols):
        rows, cols = max(1, int(rows)), max(1, int(cols))
        new = [[self._blank() for _ in range(cols)] for _ in range(rows)]
        for r in range(min(rows, self.rows)):
            for c in range(min(cols, self.cols)):
                new[r][c] = self.grid[r][c]
        self.rows, self.cols, self.grid = rows, cols, new
        self.r = min(self.r, rows - 1)
        self.c = min(self.c, cols - 1)

    def _linefeed(self):
        self.r += 1
        if self.r >= self.rows:
            self.grid.pop(0)
            self.grid.append([self._blank() for _ in range(self.cols)])
            self.r = self.rows - 1

    def _put(self, ch):
        w = _width(ch)
        if w == 0:
            return
        if self.c + w > self.cols:
            self.c = 0
            self._linefeed()
        self.grid[self.r][self.c] = (ch, self.fg, self.bg, self.bold)
        if w == 2 and self.c + 1 < self.cols:
            self.grid[self.r][self.c + 1] = (" ", self.fg, self.bg, self.bold)
        self.c += w
        if self.c >= self.cols:
            self.c = 0
            self._linefeed()

    # ---- 解析 ----
    def feed(self, data):
        if not data:
            return
        for ch in data:
            if self._state == "text":
                if ch == "\x1b":
                    self._state = "esc"
                elif ch == "\r":
                    self.c = 0
                elif ch == "\n":
                    self._linefeed()
                elif ch == "\b":
                    self.c = max(0, self.c - 1)
                elif ch == "\t":
                    self.c = min(self.cols - 1, (self.c // 8 + 1) * 8)
                elif ch >= " ":
                    self._put(ch)
            elif self._state == "esc":
                if ch == "[":
                    self._state, self._params = "csi", ""
                elif ch == "]":
                    self._state = "osc"
                elif ch in "78":
                    self._state = "text"
                elif ch == "c":
                    self.clear()
                    self._state = "text"
                else:
                    self._state = "text"
            elif self._state == "csi":
                if "@" <= ch <= "~":
                    self._csi(self._params, ch)
                    self._state = "text"
                else:
                    self._params += ch
            elif self._state == "osc":
                if ch == "\x07":
                    self._state = "text"
                elif ch == "\x1b":
                    self._osc_esc = True
            elif self._state == "osc_esc":
                self._state = "text" if ch == "\\" else "osc"
                self._osc_esc = False

    def _csi(self, params, cmd):
        private = params.startswith("?")
        body = params[1:] if private else params
        nums = []
        for part in body.split(";"):
            try:
                nums.append(int(part) if part else 0)
            except ValueError:
                nums.append(0)
        if cmd in "hl" and private and any(n in (47, 1047, 1049) for n in nums):
            self._toggle_alt(cmd == "h")
            return
        if cmd == "m":
            self._sgr(nums or [0])
            return
        if cmd in "Hf":
            r = (nums[0] if nums and nums[0] else 1) - 1
            c = (nums[1] if len(nums) > 1 and nums[1] else 1) - 1
            self.r, self.c = min(max(0, r), self.rows - 1), min(max(0, c), self.cols - 1)
        elif cmd == "A":
            self.r = max(0, self.r - (nums[0] or 1))
        elif cmd == "B":
            self.r = min(self.rows - 1, self.r + (nums[0] or 1))
        elif cmd == "C":
            self.c = min(self.cols - 1, self.c + (nums[0] or 1))
        elif cmd == "D":
            self.c = max(0, self.c - (nums[0] or 1))
        elif cmd == "G":
            self.c = min(max(0, (nums[0] or 1) - 1), self.cols - 1)
        elif cmd == "J":
            mode = nums[0] if nums else 0
            if mode == 2 or mode == 3:
                for rr in range(self.rows):
                    self.grid[rr] = [self._blank() for _ in range(self.cols)]
            elif mode == 0:
                for cc in range(self.c, self.cols):
                    self.grid[self.r][cc] = self._blank()
                for rr in range(self.r + 1, self.rows):
                    self.grid[rr] = [self._blank() for _ in range(self.cols)]
        elif cmd == "K":
            mode = nums[0] if nums else 0
            if mode == 0:
                for cc in range(self.c, self.cols):
                    self.grid[self.r][cc] = self._blank()
            elif mode == 1:
                for cc in range(0, self.c + 1):
                    self.grid[self.r][cc] = self._blank()

    def _sgr(self, nums):
        i = 0
        while i < len(nums):
            n = nums[i]
            if n == 0:
                self.fg = self.bg = None
                self.bold = False
            elif n == 1:
                self.bold = True
            elif n == 22:
                self.bold = False
            elif n in FG:
                self.fg = FG[n]
            elif n in BG:
                self.bg = BG[n]
            elif n == 39:
                self.fg = None
            elif n == 49:
                self.bg = None
            i += 1

    def _toggle_alt(self, on):
        if on and not self.alt:
            self._saved = (self.grid, self.r, self.c)
            self.alt = True
            self._reset_grid()
            self.r = self.c = 0
        elif not on and self.alt:
            if self._saved:
                self.grid, self.r, self.c = self._saved
            self._saved = None
            self.alt = False

    # ---- 输出 ----
    def text(self):
        rows = []
        for row in self.grid:
            rows.append("".join(cell[0] for cell in row).rstrip())
        return "\n".join(rows).rstrip()

    def render_html(self):
        out = []
        escape = html.escape
        for row in self.grid:
            cells = []
            last = -1
            for idx, cell in enumerate(row):
                if cell[0] != " ":
                    last = idx
            for idx in range(last + 1):
                ch, fg, bg, bold = row[idx]
                style = ""
                if fg:
                    style += "color:%s;" % fg
                if bg:
                    style += "background-color:%s;" % bg
                if bold:
                    style += "font-weight:bold;"
                ch = escape(ch if ch != "" else " ")
                cells.append('<span style="%s">%s</span>' % (style, ch) if style else ch)
            out.append("".join(cells))
        body = "\n".join(out).replace("\n", "<br>")
        return (
            '<pre style="margin:0; font-family:Consolas,monospace; font-size:10pt; '
            'color:#d4d4d4; background:#1e1e1e;">%s</pre>' % body
        )
