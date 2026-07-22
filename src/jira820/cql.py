"""Confluence CQL (Confluence Query Language) subset — search over the page corpus.

Mirrors Confluence Data Center 9.2.x search semantics enough for unified-search consumers:
supported clauses (AND-joined):
  space = KEY | space in (A, B)      -> page space
  type = page|blogpost               -> accepted (all mock content is 'page')
  title ~ "text"                     -> substring in title
  text ~ "text" | siteSearch ~ "t"   -> substring in title + body
  contributor = user | creator = u   -> author match  (currentUser() ok if resolver given)
  label = x                          -> ignored (no labels in mock)
  lastmodified >= now("-14d") | -14d -> date threshold
Ordering: most-recently-modified first (Confluence default for search).
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .jql import _reldays, _split_and

_OP = re.compile(r"\s*(!=|>=|<=|=|>|<|~|(?i:\bin\b)|(?i:\bnot in\b))\s*", re.I)


def _vals(raw):
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    out = []
    for part in re.split(r"\s*,\s*", raw):
        part = part.strip().strip('"').strip("'")
        if part:
            out.append(part)
    return out


def _reldate(val, today):
    """now("-14d") / -14d / "2026-01-01" -> date threshold (None if unparseable).
    _reldays 는 ("rel", days) | ("abs", date) | None 을 돌려준다."""
    m = re.search(r'now\(\s*"?([+-]?\d+)([dwmhy])"?\s*\)', val, re.I)
    src = (m.group(1) + m.group(2)) if m else val.strip().strip('"').strip("'")
    r = _reldays(src)
    if r is None:
        return None
    kind, v = r
    return (today + timedelta(days=v)) if kind == "rel" else v


def _pred(clause, today, mr=None):
    m = _OP.search(clause)
    if not m:
        return None
    field = clause[:m.start()].strip().lower()
    op = m.group(1).lower()
    vals = _vals(clause[m.end():])
    v0 = vals[0] if vals else ""

    if field == "space":
        low = [v.lower() for v in vals]
        return lambda p: str(p.get("space") or "").lower() in low
    if field == "type":
        return lambda p: True                     # mock: 전부 page
    if field == "title" and op == "~":
        return lambda p: v0.lower() in (p.get("title") or "").lower()
    if field in ("text", "sitesearch") and op == "~":
        n = v0.lower()
        return lambda p: n in ((p.get("title") or "") + " " + (p.get("body") or "")).lower()
    if field in ("contributor", "creator", "mention"):
        who = mr(v0) if (mr and v0) else v0
        return lambda p: (p.get("author") or "") == who
    if field == "label":
        return lambda p: True                     # mock: 라벨 없음 → 무시
    if field in ("lastmodified", "created") and op in (">=", ">", "<=", "<", "="):
        thr = _reldate(v0, today)
        if thr is None:
            return lambda p: True

        def _dt(p):
            d = p.get("date")
            if not isinstance(d, date):
                return True
            if op in (">=",):
                return d >= thr
            if op == ">":
                return d > thr
            if op in ("<=",):
                return d <= thr
            if op == "<":
                return d < thr
            return d == thr
        return _dt
    return None  # unknown clause -> ignore


def search_pages(store, cql, limit=25, mention_resolver=None):
    """CQL 로 Confluence 페이지 코퍼스 검색 → date desc 정렬 후 limit."""
    n = getattr(store, "now", None)                       # 속성(부모 주입) 또는 메서드(standalone) 모두 대응
    today = (n() if callable(n) else n) or store.config.base_date
    pages = store.confluence_pages()
    body = (cql or "").strip()
    # ORDER BY 제거(우린 항상 최신순)
    body = re.sub(r"(?i)\s+order\s+by\s+.*$", "", body).strip()
    preds = [p for p in (_pred(c, today, mention_resolver) for c in _split_and(body)) if p] if body else []
    matched = [pg for pg in pages if all(pr(pg) for pr in preds)]
    matched.sort(key=lambda p: p.get("date") or date.min, reverse=True)
    return matched[: max(0, int(limit or 25))]


def search_terms(cql):
    """CQL 에서 text/siteSearch/title ~ "term" 의 term 들을 뽑는다(excerpt 하이라이트용)."""
    out = []
    for m in re.finditer(r'(?i)(?:text|sitesearch|title)\s*~\s*"([^"]+)"', cql or ""):
        t = m.group(1).strip()
        if t:
            out.append(t)
    return out
