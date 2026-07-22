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


# ── 쓰기: 이슈 링크 / 원격 링크 생성·삭제 (실 Jira DC 형태의 바디) ──


def _two_keys(cl):
    ks = [i["key"] for i in cl.get("/rest/api/2/search",
                                   params={"jql": "project=JIRA820", "maxResults": 5}).json()["issues"]]
    return ks[0], ks[1]


def test_create_and_delete_issue_link():
    cl = TestClient(make_app())
    a, b = _two_keys(cl)
    r = cl.post("/rest/api/2/issueLink", json={
        "type": {"name": "Blocks"}, "inwardIssue": {"key": a}, "outwardIssue": {"key": b}})
    assert r.status_code == 201

    def links(k):
        return cl.get(f"/rest/api/2/issue/{k}", params={"fields": "issuelinks"}) \
                 .json()["fields"]["issuelinks"]

    mine = [ln for ln in links(a) if (ln.get("outwardIssue") or {}).get("key") == b]
    assert mine and mine[0]["type"]["name"] == "Blocks"      # a --blocks--> b
    theirs = [ln for ln in links(b) if (ln.get("inwardIssue") or {}).get("key") == a]
    assert theirs, "상대 이슈에서 inward 로 보여야 한다"

    cl.delete("/rest/api/2/issueLink/" + mine[0]["id"])
    assert not [ln for ln in links(a) if (ln.get("outwardIssue") or {}).get("key") == b]
    assert not [ln for ln in links(b) if (ln.get("inwardIssue") or {}).get("key") == a]


def test_issue_link_rejects_self_and_missing_target():
    cl = TestClient(make_app())
    a, _ = _two_keys(cl)
    assert cl.post("/rest/api/2/issueLink", json={
        "type": {"name": "Relates"}, "inwardIssue": {"key": a},
        "outwardIssue": {"key": a}}).status_code == 400
    assert cl.post("/rest/api/2/issueLink",
                   json={"type": {"name": "Relates"}, "inwardIssue": {"key": a}}).status_code == 400


def test_create_remote_link_upserts_on_global_id():
    cl = TestClient(make_app())
    a, _ = _two_keys(cl)
    url = "https://conf.test/display/DP/설계"
    body = {"globalId": url, "object": {"url": url, "title": "설계 문서"}}
    assert cl.post(f"/rest/api/2/issue/{a}/remotelink", json=body).status_code == 201
    cl.post(f"/rest/api/2/issue/{a}/remotelink",          # 같은 문서 재등록 → 한 줄만
            json={"globalId": url, "object": {"url": url, "title": "설계 문서 v2"}})
    got = [r for r in cl.get(f"/rest/api/2/issue/{a}/remotelink").json()
           if r["object"]["url"] == url]
    assert len(got) == 1 and got[0]["object"]["title"] == "설계 문서 v2"

    cl.delete(f"/rest/api/2/issue/{a}/remotelink/{got[0]['id']}")
    assert not [r for r in cl.get(f"/rest/api/2/issue/{a}/remotelink").json()
                if r["object"]["url"] == url]
