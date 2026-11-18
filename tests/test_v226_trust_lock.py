# -*- coding: utf-8 -*-
"""v2.26 Sprint1：生产信任回退锁定"""


def test_production_refuses_env_fallback(monkeypatch):
    from core.plugin_trust import env_fallback_allowed

    monkeypatch.setenv("QINGCAO_ENV", "production")
    monkeypatch.setenv("QINGCAO_TRUST_ENV_FALLBACK", "1")
    assert not env_fallback_allowed()


def test_dev_allows_explicit_fallback(monkeypatch):
    from core.plugin_trust import env_fallback_allowed

    monkeypatch.setenv("QINGCAO_ENV", "test")
    monkeypatch.setenv("QINGCAO_TRUST_ENV_FALLBACK", "1")
    assert env_fallback_allowed()


def test_dev_requires_explicit_flag(monkeypatch):
    from core.plugin_trust import env_fallback_allowed

    monkeypatch.setenv("QINGCAO_ENV", "dev")
    monkeypatch.delenv("QINGCAO_TRUST_ENV_FALLBACK", raising=False)
    assert not env_fallback_allowed()
