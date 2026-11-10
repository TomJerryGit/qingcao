# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""panels（v2.24 拆分）。"""

from ui.panels_common import *  # noqa: F401,F403
from ui.panels_dialogs import *  # noqa: F401,F403
from ui.panels_widgets import *  # noqa: F401,F403
from ui.search_bar import SearchBar  # noqa: F401


class SearchDirection(Enum):
    """搜索方向"""

    FORWARD = auto()
    BACKWARD = auto()


# ============================================================
# 搜索栏
# ============================================================
