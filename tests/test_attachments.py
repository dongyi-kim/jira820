from conftest import ok


def _create(client, pk):
    return ok(client.post("/rest/api/2/issue", json={
        "fields": {"project": {"key": pk}, "issuetype": {"name": "Task"}, "summary": "a"}}))["key"]


def test_upload_list_download_delete(client, pk):
    key = _create(client, pk)
    png = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
    r = client.post(f"/rest/api/2/issue/{key}/attachments",
                    files={"file": ("diagram.png", png, "image/png")})
    assert r.status_code == 200
    att = r.json()[0]
    assert att["filename"] == "diagram.png"
    assert att["mimeType"] == "image/png"
    assert att["size"] == len(png)
    assert "thumbnail" in att            # images expose a thumbnail url
    aid = att["id"]

    # appears in fields.attachment
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["attachment"][0]["id"] == aid

    # download raw bytes
    r = client.get(f"/secure/attachment/{aid}/diagram.png")
    assert r.status_code == 200 and r.content == png
    assert r.headers["content-type"].startswith("image/png")

    # reference it from a comment + description via wiki markup (body stored as-is)
    ok(client.post(f"/rest/api/2/issue/{key}/comment", json={"body": "screenshot: !diagram.png|thumbnail!"}))
    r = client.put(f"/rest/api/2/issue/{key}", json={"fields": {"description": "before: !diagram.png!"}})
    assert r.status_code == 204
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert "!diagram.png!" in it["fields"]["description"]

    # metadata endpoint
    m = ok(client.get(f"/rest/api/2/attachment/{aid}"))
    assert m["filename"] == "diagram.png"

    # delete
    assert client.delete(f"/rest/api/2/attachment/{aid}").status_code == 204
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert it["fields"]["attachment"] == []
    assert client.get(f"/rest/api/2/attachment/{aid}").status_code == 404


def test_multiple_files_one_request(client, pk):
    key = _create(client, pk)
    r = client.post(f"/rest/api/2/issue/{key}/attachments", files=[
        ("file", ("a.txt", b"aaa", "text/plain")),
        ("file", ("b.txt", b"bbbb", "text/plain")),
    ])
    assert r.status_code == 200 and len(r.json()) == 2
    it = ok(client.get(f"/rest/api/2/issue/{key}"))
    assert {a["filename"] for a in it["fields"]["attachment"]} == {"a.txt", "b.txt"}
