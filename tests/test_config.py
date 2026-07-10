import os

from jira820 import build_store, load_config
from jira820.config import Config


def test_determinism_same_seed():
    a = build_store(Config(seed="abc"))
    b = build_store(Config(seed="abc"))
    ka, kb = next(iter(a.issues)), next(iter(b.issues))
    assert a.issues[ka]["summary"] == b.issues[kb]["summary"]
    assert len(a.issues) == len(b.issues)


def test_different_seed_varies():
    a = build_store(Config(seed="one"))
    b = build_store(Config(seed="two"))
    sa = [a.issues[k]["summary"] for k in list(a.issues)[:10]]
    sb = [b.issues[k]["summary"] for k in list(b.issues)[:10]]
    assert sa != sb


def test_env_override(monkeypatch):
    monkeypatch.setenv("JIRA820_PROJECT_KEY", "ACME")
    monkeypatch.setenv("JIRA820_SEED", "9")
    monkeypatch.setenv("JIRA820_LOCALE", "ko")
    c = load_config()
    assert c.project_key == "ACME"
    assert c.seed == "9"
    assert c.locale == "ko"
    s = build_store(c)
    assert next(iter(s.issues)).startswith("ACME-")


def test_locale_ko_uses_korean_pool():
    s = build_store(Config(seed="k", locale="ko"))
    # at least one Korean summary token appears
    joined = " ".join(it["summary"] for it in list(s.issues.values())[:50])
    assert any("가" <= ch <= "힣" for ch in joined)
