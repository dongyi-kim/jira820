"""Issue and search field selection preserve discussion without scalar fan-out."""
from datetime import date

import pytest

from conftest import ok


@pytest.mark.parametrize("search", [False, True])
def test_embedded_comment_field_preserves_more_than_preview_window(client, app, search):
    issue = next(iter(app.state.store.issues.values()))
    issue["comments"] = [{"id": str(30000+i), "author": "u01", "created": date(2026, 11, 18),
                          "tcreated": "10:%02d" % i, "body": "Evidence %s END" % i} for i in range(35)]
    key = issue["key"]
    path = "/rest/api/2/search" if search else "/rest/api/2/issue/" + key
    params = {"fields": "summary,description,comment", "jql": 'key = "' + key + '"'}
    data = ok(client.get(path, params=params))
    fields = (data["issues"][0] if search else data)["fields"]
    assert set(fields) == {"summary", "description", "comment"}
    comments = fields["comment"]
    assert comments["total"] == 35 and comments["startAt"] == 0
    assert len(comments["comments"]) == 35
    assert {r["id"] for r in comments["comments"]} == {str(30000+i) for i in range(35)}
    assert all(r["body"].endswith("END") for r in comments["comments"])


def test_excluded_comments_never_materialized(client, app, monkeypatch):
    def unexpected(*args):
        pytest.fail("metadata-only request materialized comments")
    monkeypatch.setattr(app.state.store.serializer, "comment_obj", unexpected)
    data = ok(client.get("/rest/api/2/search", params={"fields": "summary,updated", "maxResults": 10}))
    assert data["issues"] and all("comment" not in i["fields"] for i in data["issues"])


def test_empty_comment_field_is_explicit_complete_empty(client, app):
    issue = next(iter(app.state.store.issues.values()))
    issue["comments"] = []
    data = ok(client.get("/rest/api/2/issue/" + issue["key"], params={"fields": "comment"}))
    assert data["fields"]["comment"] == {"comments": [], "startAt": 0, "maxResults": 0, "total": 0}
