"""CQL evaluates real boolean structure and rejects filters it cannot honor."""
from datetime import date
from types import SimpleNamespace

import pytest

from jira820.cql import _pred, filter_content, search_pages, search_terms


TODAY = date(2026, 11, 5)
ROWS = [
    {"id": "1", "title": 'Guide AND OR "quoted"', "type": "page", "space": {"key": "DL"},
     "parent": "10", "body": {"storage": {"value": '<p>quality checkpoint</p><ri:user ri:userkey="u2" />'}},
     "version": {"number": 2, "when": "2026-11-04T02:00:00Z", "by": {"username": "u1"}},
     "history": {"createdDate": "2026-01-01T00:00:00Z", "createdBy": {"username": "owner"}},
     "ancestors": [{"id": "10"}, {"id": "20"}], "labels": ["pipeline"]},
    {"id": "2", "title": "Alpha", "type": "page", "space": {"key": "PMO"}, "parent": "",
     "body": {"storage": {"value": "checkpoint"}}, "version": {"number": 1, "when": "2026-10-01T00:00:00Z", "by": {"username": "u2"}}},
    {"id": "3", "title": "Zulu", "type": "comment", "space": {"key": "DL"}, "parent": "",
     "body": {"storage": {"value": "comment"}}, "version": {"number": 1, "when": "2026-11-03T00:00:00Z", "by": {"username": "u1"}}},
]


def selected(query, rows=ROWS, **kwargs):
    return [row["id"] for row in filter_content(rows, query, TODAY, current_user="u1", **kwargs)]


@pytest.mark.parametrize("query,expected", [
    ('space = DL AND (id = 1 OR id = 2)', ["1"]),
    ('(space = DL AND type = page) OR space = PMO ORDER BY id DESC', ["2", "1"]),
    ('NOT (space = PMO OR type = comment)', ["1"]),
    ('space IN (DL, PMO) AND type NOT IN (comment, blogpost) ORDER BY title ASC', ["2", "1"]),
    ('space != PMO AND type != comment', ["1"]),
    ('id IN (2, 1) ORDER BY id ASC', ["1", "2"]),
    ('parent = 10 AND ancestor = 20', ["1"]),
    ('label = pipeline', ["1"]),
    ('title ~ "AND OR"', ["1"]),
    ('title = "Guide AND OR \\"quoted\\""', ["1"]),
    ('text ~ checkpoint AND siteSearch ~ quality', ["1"]),
    ('contributor = currentUser() AND type = page', ["1"]),
    ('creator = owner AND mention = u2', ["1"]),
    ('lastmodified >= now("-14d") AND type = page', ["1"]),
    ('lastmodified >= -1w AND lastmodified < now()', ["1", "3"]),
    ('created < "2026-02-01"', ["1"]),
    ('ORDER BY title DESC', ["3", "1", "2"]),
], ids=["parentheses", "or-branches", "not", "in-not-in", "negative", "numeric-id-sort", "hierarchy",
        "label", "literal-boolean", "escaped-quotes", "body", "current-user", "creator-mention",
        "relative-function", "relative-literal", "created-date", "order-only"])
def test_supported_queries(query, expected):
    assert selected(query) == expected


@pytest.mark.parametrize("query", [
    'unknown = value', 'space = DL OR unknown = value', 'label ~ pipeline', 'title > abc',
    'space =', 'space IN ()', 'space IN (DL,)', 'space = DL trailing', '(space = DL',
    'space = DL)', 'space = "DL', 'space = "DL\\', 'space = DL AND', 'space = DL OR',
    'title ~ AND', 'lastmodified >= sometime()', 'lastmodified >= now("nonsense")',
    'contributor = currentUser("u1")', 'space = currentUser()', 'ORDER BY rank',
    'ORDER BY title sideways', 'space === DL', 'space NOT DL', 'NOT',
])
def test_unsupported_or_malformed_filters_fail_even_with_no_rows(query):
    with pytest.raises(ValueError):
        selected(query, [])


def test_limits_are_on_bytes_nesting_and_condition_count():
    for query in ('title ~ "' + '가' * 6000 + '"', '(' * 65 + 'type = page' + ')' * 65,
                  ' OR '.join(['type = page'] * 257)):
        with pytest.raises(ValueError):
            selected(query)


def test_resolvers_accept_rows_and_all_sort_fields_are_stable():
    rows = [dict(row, labels=[], ancestors=[]) for row in ROWS]
    assert selected('ancestor = 77 AND label = shared', rows,
        ancestor_resolver=lambda row: [{"id": "77"}] if row["id"] == "2" else [],
        labels_resolver=lambda row: {"shared"}) == ["2"]
    equal = [dict(ROWS[0], id=identifier, title="Same") for identifier in ("10", "2", "1")]
    assert selected('ORDER BY title ASC, id DESC', equal) == ["10", "2", "1"]


def test_legacy_corpus_and_mention_resolver_remain_usable():
    corpus = [{"id": 1, "title": "A", "space": "DL", "author": "u1", "body": "checkpoint", "date": TODAY},
              {"id": 2, "title": "B", "space": "PMO", "author": "u2", "body": "other", "date": date(2026, 1, 1)}]
    store = SimpleNamespace(config=SimpleNamespace(base_date=TODAY, current_user="u1"), confluence_pages=lambda: corpus)
    assert search_pages(store, 'contributor = currentUser() AND text ~ checkpoint') == [corpus[0]]
    assert search_pages(store, '', limit=0) == []
    assert _pred('contributor = "me"', TODAY, lambda who: 'u1' if who == 'me' else who)(corpus[0])
    assert search_terms('title ~ "AND OR" OR text ~ "a \\"quote\\""') == ['AND OR', 'a "quote"']
    assert corpus[0]["body"] == "checkpoint"


def test_current_user_requires_identity_but_unknown_dates_do_not_match():
    with pytest.raises(ValueError):
        filter_content([], 'creator = currentUser()', TODAY)
    assert selected('lastmodified >= -1d', [{"id": "1", "version": {"when": "invalid"}}]) == []
