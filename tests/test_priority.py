# -*- coding: utf-8 -*-
"""우선순위 — 설정 가능한 목록 + 이슈별 값.

스킴은 인스턴스마다 다르다(사내는 P0-Blocker … P4-Trivial / Unclassified).
mock 은 특정 스킴을 알 필요가 없고, 목록을 갈아끼울 수 있으면 된다.
"""
from fastapi.testclient import TestClient

from jira820 import build_store, make_app
from jira820.config import Config


def _client(**over):
    c = Config()
    for k, v in over.items():
        setattr(c, k, v)
    return TestClient(make_app(config=c)), c


def test_default_priority_list_is_jira_default():
    cl, _ = _client()
    names = [p["name"] for p in cl.get("/rest/api/2/priority").json()]
    assert names == ["Highest", "High", "Medium", "Low", "Lowest"]


def test_priority_list_is_configurable():
    scheme = [["P0-Blocker", "1"], ["P1-Critical", "2"], ["Unclassified", "9"]]
    cl, _ = _client(priorities=scheme)
    got = cl.get("/rest/api/2/priority").json()
    assert [p["name"] for p in got] == ["P0-Blocker", "P1-Critical", "Unclassified"]
    assert [p["id"] for p in got] == ["1", "2", "9"]


def test_issue_carries_its_own_priority():
    cl, _ = _client()
    key = cl.get("/rest/api/2/search", params={"jql": "project=JIRA820", "maxResults": 1}).json()["issues"][0]["key"]
    assert cl.get(f"/rest/api/2/issue/{key}").json()["fields"]["priority"]["name"]


def test_default_priority_used_when_issue_has_none():
    """사내처럼 '값 없음' 이 아니라 기본값(Unclassified)이 항상 붙는 운용도 가능해야 한다."""
    scheme = [["P0-Blocker", "1"], ["Unclassified", "9"]]
    cl, _ = _client(priorities=scheme, default_priority="Unclassified")
    key = cl.get("/rest/api/2/search", params={"jql": "project=JIRA820", "maxResults": 1}).json()["issues"][0]["key"]
    got = cl.get(f"/rest/api/2/issue/{key}").json()["fields"]["priority"]
    assert got["name"] == "Unclassified" and got["id"] == "9"


def test_unknown_priority_name_passes_through():
    """목록 밖 이름도 검열하지 않는다(mock 이 스킴을 판단할 이유가 없다)."""
    _cl, c = _client()
    obj = build_store(c).serializer.priority_obj("사내전용-초긴급")
    assert obj["name"] == "사내전용-초긴급" and obj["id"] == "0"
