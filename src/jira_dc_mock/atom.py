"""Jira Activity Streams ATOM feed (Atlassian Streams plugin shape).

Entry layout (real Jira):
  <title type="html"><a>{actor}</a> {verb} <a>{KEY}</a></title>   # HTML, not the summary
  <category term="{kind}"/>
  <link rel="alternate" href=".../browse/{KEY}"/>
  <activity:object><title>{KEY}</title><summary>{issue summary}</summary>...</activity:object>
"""

from __future__ import annotations

from xml.sax.saxutils import escape

_ATOM = "http://www.w3.org/2005/Atom"
_ACTIVITY = "http://activitystrea.ms/spec/1.0/"
_ATLASSIAN = "http://streams.atlassian.com/syndication/general/1.0"
_USR = "http://streams.atlassian.com/syndication/username/1.0"
_MEDIA = "http://purl.org/syndication/atommedia"

_VERB = {"created": "post", "commented": "post", "logged work": "update",
         "resolved": "update", "transitioned": "update", "updated": "update"}


def _dt(d, hm=None):
    return d.isoformat() + "T" + (hm or "09:00") + ":00.000+0000"


def feed(base_url, user, events, limit=20, display_name=None):
    dn = display_name or user
    profile = f"{base_url}/secure/ViewProfile.jspa?name={escape(user)}"
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<feed xmlns="{_ATOM}" xmlns:activity="{_ACTIVITY}" '
        f'xmlns:atlassian="{_ATLASSIAN}" xmlns:usr="{_USR}" xmlns:media="{_MEDIA}">',
        '<title>Activity Stream</title>',
        f'<id>urn:jira:activity:{escape(user)}</id>',
        f'<link rel="self" href="{escape(base_url)}/activity"/>',
    ]
    if events:
        parts.append(f'<updated>{_dt(events[0]["date"], events[0].get("time"))}</updated>')
    for i, e in enumerate(events[:limit]):
        key, kind, summ = e["key"], e["kind"], e.get("summary", "")
        when = _dt(e["date"], e.get("time"))
        browse = f"{base_url}/browse/{escape(key)}"
        verb = "http://activitystrea.ms/schema/1.0/" + _VERB.get(kind, "post")
        title_html = (f'<a href="{profile}">{escape(dn)}</a> {escape(kind)} '
                      f'<a href="{browse}">{escape(key)}</a>')
        parts += [
            '<entry>',
            f'<id>urn:jira:activity:{escape(user)}:{i}</id>',
            f'<title type="html">{escape(title_html)}</title>',
            f'<published>{when}</published>',
            f'<updated>{when}</updated>',
            '<author>',
            f'<name>{escape(user)}</name>',
            f'<usr:username>{escape(user)}</usr:username>',
            '<activity:object-type>http://activitystrea.ms/schema/1.0/person</activity:object-type>',
            '</author>',
            f'<category term="{escape(kind)}"/>',
            f'<link rel="alternate" href="{browse}"/>',
            '<atlassian:application>com.atlassian.jira</atlassian:application>',
            f'<activity:verb>{verb}</activity:verb>',
            '<activity:object>',
            f'<id>urn:jira:activity:object:{escape(key)}:{i}</id>',
            f'<title type="text">{escape(key)}</title>',
            f'<summary type="text">{escape(summ)}</summary>',
            f'<link rel="alternate" href="{browse}"/>',
            '<activity:object-type>http://streams.atlassian.com/syndication/types/issue</activity:object-type>',
            '</activity:object>',
            '</entry>',
        ]
    parts.append('</feed>')
    return "\n".join(parts)
