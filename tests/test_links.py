"""이슈 링크(issuelinks) — Jira DC 형태로 방출되는지."""
import re

from conftest import ok
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


# ── 링크 그래프: 티켓 ↔ Confluence ↔ 티켓 ──────────────────────────────────
# 소비자가 링크를 따라 맥락을 넓히려면 각 엣지가 **실재하는 노드**를 가리켜야 한다.

KEY_RE = re.compile(r"[A-Z][A-Z0-9]*-\d+")


def _confluence_remotelinks(store):
    out = []
    for k in sorted(store.issues):
        for rl in store.issues[k].get("remotelinks") or []:
            if (rl.get("application") or {}).get("type") == "com.atlassian.confluence":
                out.append((k, rl))
    return out


def test_confluence_remotelink_points_at_real_page(client, app):
    """원격 링크의 `/pages/{id}/` 로 실제 본문을 열 수 있어야 한다.

    예전엔 하드코딩 경로(`/spaces/DL/pages/42013/...`)라 어떤 페이지도 가리키지 않았다.
    """
    pairs = _confluence_remotelinks(app.state.store)
    assert pairs, "Confluence 원격 링크가 시드에 있어야"
    for key, rl in pairs[:5]:
        m = re.search(r"/pages/(\d+)/", rl["url"])
        assert m, f"{key}: 링크에서 page id 를 못 뽑음 — {rl['url']}"
        page = ok(client.get(f"/rest/api/content/{m.group(1)}", params={"expand": "body.storage"}))
        assert page["title"] == rl["title"]
        assert page["body"]["storage"]["value"]


def test_confluence_body_references_real_tickets(client, app):
    """문서 → 티켓 방향 엣지. 본문에 적힌 키가 실재해야 한다."""
    store = app.state.store
    found = 0
    for p in store.confluence_pages():
        for key in KEY_RE.findall(p.get("body") or ""):
            assert key in store.issues, f"본문이 없는 티켓을 가리킴: {key}"
            ok(client.get(f"/rest/api/2/issue/{key}"))
            found += 1
    assert found, "본문에 티켓 참조가 하나도 없음"


def test_crossref_comment_matches_issue_link(app):
    """코멘트의 상호참조는 issue link 그래프와 어긋나면 안 된다."""
    store = app.state.store
    seen = 0
    for k, it in store.issues.items():
        for c in it["comments"]:
            if c.get("kind") != "crossref":
                continue
            keys = KEY_RE.findall(c["text"])
            assert keys, f"{k}: crossref 코멘트에 키가 없음"
            linked = {lk.get("key") for lk in (it.get("links") or [])}
            assert keys[0] in linked, f"{k}: 코멘트가 링크 대상과 다름 {keys[0]} not in {linked}"
            seen += 1
    assert seen, "crossref 코멘트가 하나도 없음"
