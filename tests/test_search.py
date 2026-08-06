"""통합 검색 기반 — JQL text~ , Confluence CQL 검색, 멀티프로젝트(주입) 직렬화."""
import copy

from conftest import ok


def test_jql_text_search_matches_content(client, app):
    store = app.state.store
    it = next(iter(store.issues.values()))
    word = (it["summary"].split() or ["x"])[0]
    r = ok(client.get("/rest/api/2/search", params={"jql": f'text ~ "{word}"', "maxResults": 300}))
    assert it["key"] in [i["key"] for i in r["issues"]]


def test_project_in_and_per_issue_project(client, app):
    """멀티프로젝트: 2번째 프로젝트 이슈를 additive 주입 → per-issue project + project in (...)."""
    store = app.state.store
    pk = store.config.project_key
    base = ok(client.get("/rest/api/2/search", params={"jql": f"project = {pk}", "maxResults": 0}))["total"]

    extra = copy.deepcopy(next(iter(store.issues.values())))
    extra["key"], extra["project"] = "EXTRA-1", "EXTRA"
    store.issues["EXTRA-1"] = extra
    store.reindex()

    # serialize 는 이슈별 프로젝트를 반영
    fj = ok(client.get("/rest/api/2/issue/EXTRA-1", params={"fields": "project"}))
    assert fj["fields"]["project"]["key"] == "EXTRA"
    # project in (...) 은 두 프로젝트를 모두 포함 (in 괄호 파싱 회귀 가드)
    both = ok(client.get("/rest/api/2/search", params={"jql": f"project in ({pk}, EXTRA)", "maxResults": 0}))
    assert both["total"] == base + 1


def test_confluence_cql_search_endpoint(client, app):
    store = app.state.store
    pages = store.confluence_pages()
    assert pages, "seed world 에 confluence 페이지가 있어야"
    sp = pages[0]["space"]
    r = ok(client.get("/rest/api/search", params={"cql": f'space = "{sp}"', "limit": 20}))
    assert "results" in r and "totalSize" in r and "cqlQuery" in r
    for item in r["results"]:
        assert item["content"]["type"] == "page"
        assert str(item["content"]["space"]["key"]) == str(sp)
        assert item["url"].startswith("/spaces/")
        assert "excerpt" in item


def test_confluence_space_in_and_title_search(client, app):
    store = app.state.store
    pages = store.confluence_pages()
    spaces = list({str(p["space"]) for p in pages})[:2]
    if len(spaces) >= 2:
        r = ok(client.get("/rest/api/search", params={"cql": "space in (%s)" % ", ".join(spaces), "limit": 50}))
        got = {it["content"]["space"]["key"] for it in r["results"]}
        assert got <= set(spaces)
    tw = (pages[0]["title"].split() or ["a"])[0][:3]
    r2 = ok(client.get("/rest/api/content/search", params={"cql": f'title ~ "{tw}"', "limit": 20}))
    assert r2["size"] >= 1


def test_content_search_contributor_compat(client, app):
    """활동(activity) 기능이 쓰던 contributor= + expand=version,space 호환 유지."""
    store = app.state.store
    user = next(iter(store.confluence))
    r = ok(client.get("/rest/api/content/search", params={
        "cql": f'contributor = "{user}" and lastmodified >= now("-14d")',
        "expand": "version,space", "limit": 25}))
    assert "results" in r
    for it in r["results"]:
        assert "version" in it and "space" in it and it["type"] == "page"


# ── Confluence 개별 페이지 조회 (본문) ────────────────────────────────────────
# 검색은 excerpt(스니펫)만 준다. 문서 내용을 실제로 읽거나 요약하려면 본문이 필요하다.

def test_content_by_id_returns_page(client, app):
    page = app.state.store.confluence_pages()[0]
    r = ok(client.get(f"/rest/api/content/{page['id']}"))
    assert r["type"] == "page" and r["title"] == page["title"]
    assert r["space"]["key"] == str(page["space"])
    # expand 를 안 주면 본문은 싣지 않는다(실 DC 동일 — 응답이 무거워지는 것 방지).
    assert "body" not in r


def test_content_by_id_expand_body(client, app):
    page = app.state.store.confluence_pages()[0]
    pid = page["id"]

    r = ok(client.get(f"/rest/api/content/{pid}", params={"expand": "body.storage"}))
    assert set(r["body"]) == {"storage"}
    assert r["body"]["storage"]["representation"] == "storage"
    assert r["body"]["storage"]["value"].startswith("<p>")

    # expand=body 는 storage + view 둘 다
    r2 = ok(client.get(f"/rest/api/content/{pid}", params={"expand": "body"}))
    assert set(r2["body"]) == {"storage", "view"}

    # 다른 expand 값은 본문을 부르지 않는다
    r3 = ok(client.get(f"/rest/api/content/{pid}", params={"expand": "version,space"}))
    assert "body" not in r3


def test_content_search_can_expand_body(client, app):
    sp = str(app.state.store.confluence_pages()[0]["space"])
    r = ok(client.get("/rest/api/search",
                      params={"cql": f'space = "{sp}"', "limit": 3, "expand": "body.storage"}))
    assert r["results"] and all("body" in it["content"] for it in r["results"])


def test_content_by_id_404(client):
    r = client.get("/rest/api/content/999999999")
    assert r.status_code == 404
    assert "No content found" in r.json()["message"]


def test_content_search_route_not_shadowed(client):
    """/content/search 가 /content/{id} 에 잡아먹히지 않아야 한다(라우트 순서)."""
    r = ok(client.get("/rest/api/content/search", params={"cql": "type = page", "limit": 1}))
    assert "results" in r


def test_confluence_body_is_substantial(client, app):
    """본문은 검색·요약이 의미를 갖도록 여러 문단이어야 한다.

    예전 시드는 '제목. 다른제목' 한 줄이라 CQL 은 걸려도 읽을 내용이 없었다.
    """
    pages = app.state.store.confluence_pages()
    bodies = [p.get("body") or "" for p in pages]
    assert bodies and min(len(b) for b in bodies) > 200
    assert all(b.count("\n") >= 5 for b in bodies)
    # 제목과 무관한 실제 문장이 들어 있어야 한다
    assert any(len(set(b.split())) > 30 for b in bodies)
