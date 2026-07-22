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


# ── remote link (Confluence / Web) ──────────────────────────────────

def test_remotelink_endpoint_shape():
    """이슈 remote link 가 실 Jira DC 형태로 나온다."""
    cl = TestClient(make_app())
    keys = cl.get("/rest/api/2/search",
                  params={"jql": "project=JIRA820", "maxResults": 300}).json()["issues"]
    hit = None
    for it in keys:
        r = cl.get(f"/rest/api/2/issue/{it['key']}/remotelink").json()
        if r:
            hit = r
            break
    assert hit, "remote link 가 있는 이슈가 없음"
    o = hit[0]
    assert "id" in o and "object" in o
    assert o["object"].get("url") and o["object"].get("title")


def test_remotelink_empty_for_issue_without_links():
    cl = TestClient(make_app())
    r = cl.get("/rest/api/2/issue/JIRA820-1/remotelink")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_confluence_search_result_has_ancestors_and_space_name():
    """검색 결과 content 에 ancestors(상위 폴더)와 space.name 이 담긴다 — 경로 UI 용."""
    cl = TestClient(make_app())
    import urllib.parse
    r = cl.get("/rest/api/search", params={"cql": 'siteSearch ~ "a"', "limit": 50}).json()
    res = r.get("results", [])
    assert res, "검색 결과 없음"
    c = res[0]["content"]
    assert c["space"].get("name")                       # 스페이스 표시 이름
    assert "ancestors" in c and isinstance(c["ancestors"], list)
