"""Published document contracts through HTTP, including reusable injected worlds."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from jira820 import Config, make_app
from jira820.server_confluence import install_confluence


def storage(text):
    return {"storage": {"value": text, "representation": "storage"}}


@pytest.fixture
def docs(app):
    # Child deliberately precedes its explicit parent: it must not become a placeholder.
    app.state.store.confluence = {"alice": [
        {"id": "102", "title": "Child", "space": "DOC", "parentId": "101",
         "ancestors": [{"id": "101", "title": "Root"}], "body": "<h2>Child heading</h2>", "date": date(2026, 10, 1)},
        {"id": "101", "title": "Root", "space": "DOC", "body": "<h2>Rich root</h2><table><tr><td>Cell</td></tr></table>"},
        {"id": "103", "title": "Other root", "space": "DOC", "body": "<p>Other</p>"},
        {"id": "104", "title": "Foreign", "space": "OTHER", "body": "Foreign body"},
    ]}
    state = install_confluence(app)
    with TestClient(app) as client:
        yield client, state


def get(client, cid, **params):
    response = client.get(f"/rest/api/content/{cid}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_injected_ids_rich_body_real_ancestors_and_reinstall(docs, app):
    client, state = docs
    root = get(client, "101", expand="body.storage")
    assert "<table>" in root["body"]["storage"]["value"]
    assert "ancestors" not in get(client, "102", expand="body.storage,space,version")
    child = get(client, "102", expand="ancestors,body.view")
    assert [row["id"] for row in child["ancestors"]] == ["101"]
    assert child["body"]["view"]["value"] == "<h2>Child heading</h2>"
    assert [r["id"] for r in client.get("/rest/api/space/DOC/content/page?depth=root").json()["results"]] == ["101", "103"]
    route_count = len(app.routes)
    assert install_confluence(app, reset=False) is state
    app.state.store.confluence = {"alice": [{"id": "110", "title": "New root", "space": "DOC"}]}
    assert install_confluence(app) is not state
    assert len(app.routes) == route_count
    assert get(client, "110")["title"] == "New root"
    assert client.get("/rest/api/content/101").status_code == 404


def test_children_pagination_retains_expand_and_filter_query(docs):
    client, state = docs
    state.seed()
    for index in range(55):
        state.create({"id": str(1000 + index), "title": f"Page {index:02d}", "space": {"key": "DOC"},
                      "ancestors": [{"id": "103"}], "body": storage("<h2>Page</h2>")})
    first = client.get("/rest/api/content/103/child/page?limit=50&expand=body.storage,ancestors").json()
    assert first["size"] == 50 and first["totalSize"] == 55
    second = client.get(first["_links"]["next"]).json()
    assert second["size"] == 5 and "next" not in second["_links"]
    all_rows = first["results"] + second["results"]
    assert len({row["id"] for row in all_rows}) == 55
    assert all("storage" in row["body"] and row["ancestors"][0]["id"] == "103" for row in all_rows)
    assert client.get("/rest/api/content/103/child/page?limit=0").status_code == 400


def test_cas_revision_read_move_and_trash_restore(docs):
    client, state = docs
    original = get(client, "102", expand="body.storage")
    edit = {"version": {"number": 2}, "title": "Changed", "body": storage("<p>New</p>")}
    assert client.put("/rest/api/content/102", json=edit).status_code == 200
    assert client.put("/rest/api/content/102", json=edit).status_code == 409
    assert get(client, "102", version=1, expand="body.storage")["body"] == original["body"]
    assert client.put("/rest/api/content/102", json={"version": {"number": 3}, "ancestors": [{"id": "103"}]}).status_code == 200
    moved = get(client, "102", expand="body.storage,ancestors")
    assert moved["body"] == storage("<p>New</p>")
    assert [row["id"] for row in moved["ancestors"]] == ["103"]
    assert client.put("/rest/api/content/103", json={"version": {"number": 2}, "ancestors": [{"id": "102"}]}).status_code == 409
    assert client.put("/rest/api/content/102", json={"version": {"number": 4}, "ancestors": [{"id": "104"}]}).status_code == 400
    assert client.delete("/rest/api/content/103").status_code == 409
    assert client.delete("/rest/api/content/102").status_code == 204
    assert client.get("/rest/api/content/102").status_code == 404
    assert get(client, "102", status="trashed")["version"]["number"] == 3
    assert client.put("/rest/api/content/102", json={"version": {"number": 4}, "status": "current"}).status_code == 200
    history = client.get("/rest/api/content/102/history").json()
    assert history["lastUpdated"]["number"] == 4
    assert history["previousVersion"]["number"] == 3
    assert history["createdBy"] == original["history"]["createdBy"]


def test_concurrent_updates_have_one_winner(docs):
    client, state = docs
    get(client, "101")
    def write(title):
        return client.put("/rest/api/content/101", json={"version": {"number": 2}, "title": title}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ["One", "Two"]))
    assert sorted(results) == [200, 409]
    assert get(client, "101")["version"]["number"] == 2


def test_comments_labels_restrictions_and_inherited_permission(docs):
    client, state = docs
    comment = client.post("/rest/api/content", json={"type": "comment", "container": {"id": "102"}, "body": storage("<p>Comment</p>")}).json()
    cid = comment["id"]
    assert client.get("/rest/api/content/102/child/comment").json()["results"][0]["id"] == cid
    assert client.put(f"/rest/api/content/{cid}", json={"version": {"number": 2}, "body": storage("<p>Edited</p>")}).status_code == 200
    assert client.post("/rest/api/content/102/label", json=[{"name": "guide"}]).status_code == 200
    assert [row["id"] for row in client.get("/rest/api/content/search", params={"cql": 'ancestor=101 AND label="guide"'}).json()["results"]] == ["102"]
    access = [{"operation": "read", "restrictions": {"user": [{"username": "alice"}]}}]
    assert client.put("/rest/api/content/102/restriction", json=access).status_code == 200
    assert client.get("/rest/api/content/102/restriction/byOperation").json()["read"]["restrictions"]["user"]["size"] == 1
    # Access-denial injection is explicit; restriction storage is not a full permission engine.
    state.denied.add("101")
    assert client.get(f"/rest/api/content/{cid}").status_code == 403
    assert client.get("/rest/api/content/search", params={"cql": "ancestor=101"}).json()["size"] == 0
    state.denied.clear()
    assert client.delete(f"/rest/api/content/{cid}").status_code == 204
    assert client.delete("/rest/api/content/102/label?name=guide").status_code == 204
    assert client.get("/rest/api/content/102/label").json()["size"] == 0


def test_attachment_binary_revisions_owner_and_duplicate(docs):
    client, state = docs
    upload = client.post("/rest/api/content/102/child/attachment", files={"file": ("한글 image.png", b"first", "image/png")})
    assert upload.status_code == 200, upload.text
    row = upload.json()["results"][0]
    aid, url = row["id"], row["_links"]["download"]
    assert client.get(url).content == b"first"
    assert client.post("/rest/api/content/102/child/attachment", files={"file": ("한글 image.png", b"duplicate")}).status_code == 409
    updated = client.post(f"/rest/api/content/102/child/attachment/{aid}/data", files={"file": ("한글 image.png", b"second", "image/png")})
    assert updated.status_code == 200 and updated.json()["version"]["number"] == 2
    assert client.get(url).content == b"second"
    assert client.get(url, params={"version": 1}).content == b"first"
    assert client.get(url, params={"version": 3}).status_code == 404
    assert client.delete(f"/rest/api/content/103/child/attachment/{aid}").status_code == 404
    assert client.delete(f"/rest/api/content/102/child/attachment/{aid}").status_code == 204
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("method,path,payload", [
    ("post", "/rest/api/content", {"title": "No", "type": "page"}),
    ("put", "/rest/api/content/102", {"version": {"number": 2}, "title": "No"}),
    ("delete", "/rest/api/content/102", None),
    ("post", "/rest/api/content/102/label", [{"name": "no"}]),
    ("delete", "/rest/api/content/102/label?name=no", None),
    ("put", "/rest/api/content/102/restriction", []),
    ("post", "/rest/api/content/102/child/attachment", None),
    ("post", "/rest/api/content/102/child/attachment/999/data", None),
])
def test_readonly_rejects_writes_without_mutation(docs, method, path, payload):
    client, state = docs
    state.seed()
    before = state.snapshot()
    state.store.config.readonly = True
    response = client.request(method, path, **({"json": payload} if payload is not None else {}))
    assert response.status_code == 403, response.text
    assert state.snapshot() == before


def test_mutated_documents_and_binary_survive_persist_restart(docs, tmp_path):
    client, state = docs
    path = tmp_path / "world.json"
    state.store.config.persist = str(path)
    assert client.put("/rest/api/content/102", json={"version": {"number": 2}, "body": storage("<p>Persisted</p>")}).status_code == 200
    client.post("/rest/api/content/102/label", json=[{"name": "saved"}])
    client.put("/rest/api/content/102/restriction", json=[{"operation": "update", "restrictions": {"group": [{"name": "writers"}]}}])
    upload = client.post("/rest/api/content/102/child/attachment", files={"file": ("data.bin", b"\x00\xffbytes")}).json()["results"][0]
    restarted = make_app(config=Config(seed="unrelated", persist=str(path)))
    with TestClient(restarted) as again:
        assert get(again, "102", expand="body.storage")["body"] == storage("<p>Persisted</p>")
        assert get(again, "102", version=1, expand="body.storage")["body"] == storage("<h2>Child heading</h2>")
        assert again.get(upload["_links"]["download"]).content == b"\x00\xffbytes"
        assert again.get("/rest/api/content/102/label").json()["results"][0]["name"] == "saved"
        assert again.get("/rest/api/content/102/restriction/byOperation").json()["update"]["restrictions"]["group"]["size"] == 1


def test_invalid_search_is_not_silently_broadened(docs):
    client, state = docs
    for cql in ('unknownField = secret', 'space=DOC AND (', 'title ~ "unterminated'):
        response = client.get("/rest/api/content/search", params={"cql": cql})
        assert response.status_code == 400 and response.json()["message"]


@pytest.mark.parametrize("field,value", [
    ("ancestors", "102"), ("ancestors", ["102"]), ("container", []),
    ("space", "DOC"), ("version", "2"), ("title", None), ("position", "first"),
])
def test_malformed_content_is_a_controlled_error(docs, field, value):
    client, state = docs
    payload = {"title": "Bad", field: value}
    assert client.post("/rest/api/content", json=payload).status_code == 400
    assert client.put("/rest/api/content/102", json={"version": {"number": 2}, **payload}).status_code == 400


def test_parent_trash_hides_owned_content_until_restore(docs):
    client, state = docs
    comment = client.post("/rest/api/content", json={"type": "comment", "container": {"id": "102"}, "body": storage("<p>Saved</p>")}).json()
    attachment = client.post("/rest/api/content/102/child/attachment", files={"file": ("file.txt", b"saved")}).json()["results"][0]
    assert client.delete("/rest/api/content/102").status_code == 204
    for cid in (comment["id"], attachment["id"]):
        assert client.get(f"/rest/api/content/{cid}").status_code == 404
        assert client.get("/rest/api/content/search", params={"cql": f'id={cid}'}).json()["size"] == 0
    assert client.put("/rest/api/content/102", json={"version": {"number": 2}, "status": "current"}).status_code == 200
    assert get(client, comment["id"])["version"]["number"] == 1
    assert client.get(attachment["_links"]["download"]).content == b"saved"
