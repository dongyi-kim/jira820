"""이슈 링크(issuelinks) — Jira DC 형태로 방출되는지."""
from fastapi.testclient import TestClient

from jira820 import make_app

c = TestClient(make_app())


def _issues():
    return c.get("/rest/api/2/search",
                 params={"jql": "project=JIRA820", "fields": "summary,issuelinks",
                         "maxResults": 1000}).json()["issues"]


def test_issuelinks_present_and_shaped():
    linked = [i for i in _issues() if i["fields"].get("issuelinks")]
    assert linked, "링크가 있는 이슈가 없음"
    ln = linked[0]["fields"]["issuelinks"][0]
    assert {"id", "type"} <= set(ln)
    assert {"id", "name", "inward", "outward"} <= set(ln["type"])
    ref = ln.get("outwardIssue") or ln.get("inwardIssue")
    assert ref and ref["key"] and ref["fields"]["summary"]
    assert ref["fields"]["status"]["name"]
    assert ref["fields"]["issuetype"]["name"]


def test_issuelinks_are_bidirectional():
    """A 가 outward 로 걸면 상대 B 에서는 inward 로 보인다(실 Jira 동작)."""
    by = {i["key"]: i["fields"].get("issuelinks") or [] for i in _issues()}
    pairs = 0
    for k, links in by.items():
        for ln in links:
            if "outwardIssue" not in ln:
                continue
            other = ln["outwardIssue"]["key"]
            if other not in by:          # 조회 범위 밖(페이징)이면 검사 불가 — 건너뛴다
                continue
            back = [x for x in by[other]
                    if "inwardIssue" in x and x["inwardIssue"]["key"] == k
                    and x["type"]["name"] == ln["type"]["name"]]
            assert back, f"{other} 에 {k} 로의 역방향 링크가 없음"
            pairs += 1
    assert pairs > 0, "outward 링크가 하나도 없음"


def test_issue_link_types_endpoint():
    r = c.get("/rest/api/2/issueLinkType")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["issueLinkTypes"]}
    assert {"Relates", "Blocks", "Duplicate", "Cloners"} <= names


def test_issue_without_links_has_empty_list():
    """링크 없는 이슈도 필드 자체는 빈 배열로 존재(실 Jira 와 동일)."""
    unlinked = [i for i in _issues() if not i["fields"].get("issuelinks")]
    assert unlinked
    assert unlinked[0]["fields"]["issuelinks"] == []
