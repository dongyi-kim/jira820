import xml.etree.ElementTree as ET

from conftest import ok


def test_activity_feed_wellformed(client):
    store = client.app.state.store
    user = next(u for u in store.activity if store.activity[u])
    r = client.get("/activity", params={"streams": f"user IS {user}", "maxResults": 5})
    assert r.status_code == 200
    assert "application/atom+xml" in r.headers["content-type"]
    root = ET.fromstring(r.text)  # parses -> well-formed
    ns = {"a": "http://www.w3.org/2005/Atom", "act": "http://activitystrea.ms/spec/1.0/"}
    entries = root.findall("a:entry", ns)
    assert entries
    e0 = entries[0]
    # category term = kind
    assert e0.find("a:category", ns).get("term")
    # alternate link -> /browse/KEY
    alt = e0.find("a:link", ns).get("href")
    assert "/browse/" in alt
    # activity:object/summary carries the real summary
    obj = e0.find("act:object", ns)
    assert obj.find("a:summary", ns) is not None
