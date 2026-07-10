from conftest import ok


def _boards(client):
    vals = ok(client.get("/rest/agile/1.0/board"))["values"]
    scrum = next(b["id"] for b in vals if b["type"] == "scrum")
    kanban = next(b["id"] for b in vals if b["type"] == "kanban")
    return vals, scrum, kanban


def test_boards_scrum_and_kanban(client):
    vals, scrum, kanban = _boards(client)
    assert {b["type"] for b in vals} == {"scrum", "kanban"}


def test_kanban_columns(client):
    _, scrum, kanban = _boards(client)
    cfg = ok(client.get(f"/rest/agile/1.0/board/{kanban}/configuration"))
    names = [c["name"] for c in cfg["columnConfig"]["columns"]]
    assert names == ["To Do", "In Progress", "Done"]


def test_sprints_seeded_states(client):
    _, scrum, _ = _boards(client)
    sprints = ok(client.get(f"/rest/agile/1.0/board/{scrum}/sprint"))["values"]
    states = [s["state"] for s in sprints]
    assert "active" in states and "closed" in states and "future" in states


def test_move_issue_between_sprint_and_backlog(client, pk):
    _, scrum, _ = _boards(client)
    active = next(s["id"] for s in ok(client.get(f"/rest/agile/1.0/board/{scrum}/sprint"))["values"]
                  if s["state"] == "active")
    key = ok(client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": pk}, "issuetype": {"name": "Story"}, "summary": "s"}}))["key"]

    assert client.post(f"/rest/agile/1.0/sprint/{active}/issue", json={"issues": [key]}).status_code == 204
    keys = [i["key"] for i in ok(client.get(f"/rest/agile/1.0/sprint/{active}/issue"))["issues"]]
    assert key in keys

    assert client.post("/rest/agile/1.0/backlog/issue", json={"issues": [key]}).status_code == 204
    keys = [i["key"] for i in ok(client.get(f"/rest/agile/1.0/sprint/{active}/issue"))["issues"]]
    assert key not in keys


def test_create_and_start_sprint(client):
    _, scrum, _ = _boards(client)
    sp = ok(client.post("/rest/agile/1.0/sprint", json={"originBoardId": scrum, "name": "New", "goal": "g"}))
    assert sp["state"] == "future"
    started = ok(client.put(f"/rest/agile/1.0/sprint/{sp['id']}", json={"state": "active"}))
    assert started["state"] == "active"
    assert started["startDate"] is not None


def test_kanban_column_move_is_a_transition(client, pk):
    # moving a card across a kanban column == transitioning to the mapped status
    key = ok(client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": pk}, "issuetype": {"name": "Task"}, "summary": "k"}}))["key"]
    trs = ok(client.get(f"/rest/api/2/issue/{key}/transitions"))["transitions"]
    tid = next(t["id"] for t in trs if t["to"]["statusCategory"]["key"] == "indeterminate")
    assert client.post(f"/rest/api/2/issue/{key}/transitions", json={"transition": {"id": tid}}).status_code == 204
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["status"]["statusCategory"]["key"] == "indeterminate"


def test_epic_children(client, pk):
    # find an epic that has children
    d = ok(client.get("/rest/api/2/search", params={"jql": f"project={pk} AND type=Epic", "maxResults": 50}))
    for e in d["issues"]:
        res = ok(client.get(f"/rest/agile/1.0/epic/{e['key']}/issue"))
        if res["total"] > 0:
            assert all(i["key"].startswith(pk) for i in res["issues"])
            return
    raise AssertionError("no epic with children found")
