from conftest import ok


def test_server_info(client):
    d = ok(client.get("/rest/api/2/serverInfo"))
    assert d["version"] == "8.20.8"
    assert d["versionNumbers"] == [8, 20, 8]
    assert d["deploymentType"] == "Server"


def test_search_paging_and_projection(client, pk):
    d = ok(client.get("/rest/api/2/search", params={"jql": f"project={pk}", "maxResults": 5, "fields": "summary,status"}))
    assert d["total"] > 100
    assert len(d["issues"]) == 5
    fields = d["issues"][0]["fields"]
    assert set(fields.keys()) == {"summary", "status"}  # projection honored
    cat = fields["status"]["statusCategory"]["key"]
    assert cat in {"new", "indeterminate", "done"}


def test_issue_has_custom_fields(client, pk):
    d = ok(client.get("/rest/api/2/search", params={"jql": f"project={pk}", "maxResults": 1}))
    it = d["issues"][0]
    f = it["fields"]
    store_cfg = None
    # sp + epic-link + sprint custom field ids are present
    assert "customfield_10004" in f
    assert "customfield_10008" in f
    assert "customfield_10007" in f
    assert f["project"]["key"] == pk


def test_field_discovery(client):
    fields = ok(client.get("/rest/api/2/field"))
    names = {f["name"] for f in fields}
    assert {"Summary", "Story Points", "Epic Link", "Sprint"} <= names


def test_createmeta(client, pk):
    d = ok(client.get("/rest/api/2/issue/createmeta"))
    proj = d["projects"][0]
    assert proj["key"] == pk
    it0 = proj["issuetypes"][0]
    assert it0["fields"]["summary"]["required"] is True


def test_issue_404(client):
    r = client.get("/rest/api/2/issue/NOPE-999")
    assert r.status_code == 404
    assert "Does Not Exist" in r.json()["errorMessages"][0]
