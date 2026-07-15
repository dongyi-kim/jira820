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
