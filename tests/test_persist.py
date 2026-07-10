from jira_dc_mock import build_store
from jira_dc_mock.config import Config


def test_persist_survives_reload(tmp_path):
    path = str(tmp_path / "state.json")
    s1 = build_store(Config(seed="p", persist=path))
    created = s1.create_issue({"project": {"key": s1.config.project_key},
                               "issuetype": {"name": "Task"}, "summary": "persisted"})
    key = created["key"]
    n = len(s1.issues)

    # new store loads from the persisted file
    s2 = build_store(Config(seed="p", persist=path))
    assert len(s2.issues) == n
    assert key in s2.issues
    assert s2.issues[key]["summary"] == "persisted"


def test_persist_keeps_dates_typed(tmp_path):
    from datetime import date
    path = str(tmp_path / "s.json")
    s1 = build_store(Config(seed="p2", persist=path))
    s2 = build_store(Config(seed="p2", persist=path))
    it = next(iter(s2.issues.values()))
    assert isinstance(it["created"], date)
