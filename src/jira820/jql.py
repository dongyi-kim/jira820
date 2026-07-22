"""A pragmatic JQL evaluator over the internal issue dicts.

Supports the shapes a real Jira client commonly sends, plus some convenience:
  field ops: = != >= <= > < , IN (...) , ~ (contains)
  fields: "Epic Link", project, labels, assignee, reporter, component, key,
          status, statusCategory, type/issuetype, sprint, created/updated/resolved/duedate
  boolean: AND / OR (OR of AND-groups; parentheses tolerated), ORDER BY <fields> [ASC|DESC]
Unknown clauses are ignored (safe) so partial support never over-filters into an error.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_CAT = {"to do": "todo", "in progress": "inprogress", "done": "done",
        "new": "todo", "indeterminate": "inprogress", "todo": "todo"}

_OP_RE = re.compile(r"\s*(!=|>=|<=|=|>|<|~|(?i:\bin\b)|(?i:\bnot in\b))\s*", re.I)


def filter_keys(store, jql: str) -> list:
    jql = (jql or "").strip()
    order = _extract_order(jql)
    body = re.sub(r"(?i)\s+order\s+by\s+.*$", "", jql).strip()

    groups = re.split(r"(?i)\s+or\s+", body) if body else []
    group_preds = [[p for p in (_pred(store, c) for c in _split_and(g)) if p] for g in groups]

    def match(it):
        if not group_preds:
            return True
        return any(all(p(it) for p in preds) for preds in group_preds if preds is not None) \
            if any(group_preds) else True

    matched = [it for it in store.issues.values() if match(it)]
    _sort(matched, order)
    return [it["key"] for it in matched]


def _split_and(group: str):
    group = group.strip()
    # 전체를 감싼 괄호쌍만 벗긴다(첫 '(' 가 마지막 ')' 와 매칭될 때). in (...) 의 닫는 괄호는 보존.
    if group.startswith("(") and group.endswith(")"):
        depth, wrap = 0, True
        for i, ch in enumerate(group):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(group) - 1:
                    wrap = False
                    break
        if wrap:
            group = group[1:-1].strip()
    return re.split(r"(?i)\s+and\s+", group) if group else []


def _extract_order(jql: str):
    m = re.search(r"(?i)\border\s+by\s+(.+)$", jql)
    if not m:
        return []
    out = []
    for part in m.group(1).split(","):
        toks = part.strip().split()
        if not toks:
            continue
        field = toks[0].strip().strip('"').lower()
        desc = len(toks) > 1 and toks[1].lower() == "desc"
        out.append((field, desc))
    return out


def _parse_clause(clause: str):
    m = _OP_RE.search(clause)
    if not m:
        return None, None, None
    field = clause[:m.start()].strip().strip('"').lower()
    op = m.group(1).lower()
    val = clause[m.end():].strip()
    return field, op, val


def _values(val: str):
    v = val.strip()
    if v.startswith("(") and v.endswith(")"):
        return [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
    return [v.strip().strip('"').strip("'")]


def _reldays(v: str):
    """'-7d','-2w','-1m','-24h' -> comparable day count; ISO date -> date."""
    v = v.strip().strip('"').strip("'")
    m = re.fullmatch(r"(-?\d+)([dwmhy]?)", v, re.I)
    if m:
        n = int(m.group(1))
        unit = (m.group(2) or "d").lower()
        mult = {"h": 1 / 24, "d": 1, "w": 7, "m": 30, "y": 365}.get(unit, 1)
        return ("rel", n * mult)
    try:
        return ("abs", date.fromisoformat(v[:10]))
    except ValueError:
        return None


def _date_pred(getter, op, val, today):
    parsed = _reldays(val)
    if not parsed:
        return None
    kind, amt = parsed
    if kind == "rel":
        # threshold = today + amt days (amt is negative for past)
        thr = today + timedelta(days=amt)
    else:
        thr = amt

    def p(it):
        d = getter(it)
        if not d:
            return False
        if op == ">=":
            return d >= thr
        if op == "<=":
            return d <= thr
        if op == ">":
            return d > thr
        if op == "<":
            return d < thr
        if op in ("=",):
            return d == thr
        return False
    return p


def _pred(store, clause):
    """절 하나 -> 술어. 부정 연산자(!= / NOT IN)는 여기서 한 번에 뒤집는다.
    (필드별 술어가 각자 op 를 챙기게 하면 하나만 빠뜨려도 조용히 정반대 결과가 나온다 —
     실제로 statusCategory != Done 이 '완료만' 돌려주는 버그가 그렇게 생겼다.)"""
    field, op, _val = _parse_clause(clause)
    p = _pred_pos(store, clause)
    if p is None or field is None:
        return p
    if (op or "").lower() in ("!=", "not in"):
        return lambda it: not p(it)
    return p


def _pred_pos(store, clause):
    field, op, val = _parse_clause(clause)
    if field is None:
        return None
    today = store.now
    vals = _values(val)
    v0 = vals[0] if vals else ""

    if field in ("epic link", "epiclink", "\"epic link\"", store.config.epic_link_field):
        return lambda it: it.get("epicKey") == v0
    if field == "project":
        return lambda it: (it.get("project") or "").lower() in [x.lower() for x in vals]
    if field == "labels":
        if op in ("in",):
            return lambda it: any(x in it.get("labels", []) for x in vals)
        return lambda it: v0 in it.get("labels", [])
    if field == "assignee":
        return lambda it: (it.get("assignee") or "") in vals
    if field == "reporter":
        return lambda it: (it.get("reporter") or "") in vals
    if field in ("component", "components"):
        return lambda it: (it.get("component") or "") in vals
    if field == "key":
        if op in ("in",):
            return lambda it: it["key"] in vals
        return lambda it: it["key"] == v0
    if field == "statuscategory":
        cats = [_CAT.get(x.lower(), x.lower()) for x in vals]
        return lambda it: it["statusCategory"] in cats
    if field == "status":
        low = [x.lower() for x in vals]
        return lambda it: (it.get("statusName") or "").lower() in low
    if field in ("type", "issuetype"):
        low = [x.lower() for x in vals]
        return lambda it: (it.get("type") or "").lower() in low
    if field == "sprint":
        def sp(it):
            for sid in it.get("sprints", []):
                s = store.sprints.get(sid)
                if not s:
                    continue
                if str(sid) in vals or s["name"] in vals or s["state"] in vals:
                    return True
            return False
        return sp
    if field in ("resolved", "resolutiondate"):
        return _date_pred(lambda it: it.get("resolved"), op, v0, today)
    if field == "created":
        return _date_pred(lambda it: it.get("created"), op, v0, today)
    if field == "updated":
        return _date_pred(lambda it: it.get("updated"), op, v0, today)
    if field in ("due", "duedate"):
        return _date_pred(lambda it: it.get("due"), op, v0, today)
    if op == "~" and field in ("text", "summary", "description", "comment"):
        needle = (v0 or "").lower()

        def _txt(it):
            hay = []
            if field in ("text", "summary"):
                hay.append(it.get("summary") or "")
            if field in ("text", "description"):
                hay.append(it.get("description") or "")
            if field in ("text", "comment"):
                for c in it.get("comments", []):
                    hay.append(c.get("body") or c.get("text") or "")
            return needle in " ".join(hay).lower()
        return _txt
    return None  # unknown clause -> ignore


def _sort(items, order):
    if not order:
        items.sort(key=lambda it: it["key"])
        return
    for field, desc in reversed(order):
        if field == "key":
            items.sort(key=lambda it: it["key"], reverse=desc)
        elif field in ("updated", "created", "duedate", "due", "resolved"):
            fk = {"duedate": "due"}.get(field, field)
            items.sort(key=lambda it: (it.get(fk) or date.min), reverse=desc)
        elif field in ("summary",):
            items.sort(key=lambda it: it.get("summary") or "", reverse=desc)
