from conftest import ok

from fastapi.testclient import TestClient
from jira_dc_mock import make_app
from jira_dc_mock.config import Config


def _create(client, pk, summary="new ticket", itype="Task"):
    return ok(client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": pk}, "issuetype": {"name": itype}, "summary": summary}}))


def test_create_get_edit_delete(client, pk):
    created = _create(client, pk, "hello world")
    key = created["key"]
    assert key.startswith(pk + "-")
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["summary"] == "hello world"
    assert it["fields"]["status"]["statusCategory"]["key"] == "new"

    r = client.put(f"/rest/api/2/issue/{key}", json={"fields": {"summary": "edited", "labels": ["x"]}})
    assert r.status_code == 204
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["summary"] == "edited"
    assert it["fields"]["labels"] == ["x"]

    r = client.delete(f"/rest/api/2/issue/{key}")
    assert r.status_code == 204
    assert client.get(f"/rest/api/2/issue/{key}").status_code == 404


def test_create_validation(client, pk):
    r = client.post("/rest/api/2/issue", json={"fields": {"project": {"key": pk}, "issuetype": {"name": "Task"}}})
    assert r.status_code == 400
    assert "summary" in r.json()["errors"]


def test_comment_and_worklog(client, pk):
    key = _create(client, pk)["key"]
    cm = ok(client.post(f"/rest/api/2/issue/{key}/comment", json={"body": "first"}))
    assert cm["body"] == "first"
    cid = cm["id"]
    ok(client.put(f"/rest/api/2/issue/{key}/comment/{cid}", json={"body": "edited"}))
    comments = ok(client.get(f"/rest/api/2/issue/{key}/comment"))["comments"]
    assert comments[0]["body"] == "edited"
    assert client.delete(f"/rest/api/2/issue/{key}/comment/{cid}").status_code == 204

    ok(client.post(f"/rest/api/2/issue/{key}/worklog", json={"timeSpentSeconds": 7200}))
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["timespent"] == 7200


def test_set_assignee(client, pk):
    key = _create(client, pk)["key"]
    assert client.put(f"/rest/api/2/issue/{key}/assignee", json={"name": "admin"}).status_code == 204
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["assignee"]["name"] == "admin"


def test_readonly_mode(pk):
    ro = TestClient(make_app(config=Config(seed="test", readonly=True)))
    r = ro.post("/rest/api/2/issue", json={"fields": {"project": {"key": pk}, "issuetype": {"name": "Task"}, "summary": "x"}})
    assert r.status_code == 403
    # reads still work
    assert ro.get("/rest/api/2/serverInfo").status_code == 200
