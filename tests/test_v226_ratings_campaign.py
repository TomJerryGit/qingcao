# -*- coding: utf-8 -*-
"""v2.26：评分运营（社区提交链接）"""

import json
import urllib.parse


def test_community_issue_url_prefills_rating():
    from ui.plugin_rating import community_issue_url

    url = community_issue_url("demo", 5, "很好用")
    assert url.startswith("https://github.com/TomJerryGit/qingcao/issues/new?")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["title"] == ["[评分] demo"]
    assert query["labels"] == ["plugin-rating"]
    body = query["body"][0]
    payload = json.loads(body.split("```json")[1].split("```")[0])
    assert payload["plugins"]["demo"]["stars"] == 5
    assert payload["plugins"]["demo"]["comment"] == "很好用"


def test_detail_has_submit_button():
    src = open("ui/plugin_detail.py", encoding="utf-8").read()
    assert "提交到社区" in src and "_submit_to_community" in src
