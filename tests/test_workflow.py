from conftest import ok


def _create(client, pk):
    return ok(client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": pk}, "issuetype": {"name": "Task"}, "summary": "wf"}}))["key"]


def _transition_to(client, key, predicate):
    trs = ok(client.get(f"/rest/api/2/issue/{key}/transitions"))["transitions"]
    tid = next(t["id"] for t in trs if predicate(t))
    r = client.post(f"/rest/api/2/issue/{key}/transitions", json={"transition": {"id": tid}})
    assert r.status_code == 204


def test_done_sets_resolution_then_reopen_clears(client, pk):
    key = _create(client, pk)
    _transition_to(client, key, lambda t: t["to"]["statusCategory"]["key"] == "done")
    it = ok(client.get(f"/rest/api/2/issue/{key}", params={"expand": "changelog"}))
    assert it["fields"]["status"]["statusCategory"]["key"] == "done"
    assert it["fields"]["resolutiondate"] is not None
    assert it["fields"]["resolution"] is not None
    assert it["changelog"]["total"] >= 1

    # reopen -> resolution cleared
    _transition_to(client, key, lambda t: t["to"]["statusCategory"]["key"] == "new")
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["resolutiondate"] is None
    assert it["fields"]["resolution"] is None


def test_transitions_exclude_current(client, pk):
    key = _create(client, pk)
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    cur = it["fields"]["status"]["name"]
    trs = ok(client.get(f"/rest/api/2/issue/{key}/transitions"))["transitions"]
    assert all(t["to"]["name"] != cur for t in trs)
