"""Bounded CQL subset for published Confluence content, independent of Jira/LTM.

Supported expressions are explicit: unsupported fields/functions/operators raise
ValueError rather than silently dropping a filter. This is not a Lucene engine;
text/title ~ searches are case-insensitive literal substrings.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

_LIMIT = 16 * 1024
_FIELDS = {"space", "title", "text", "sitesearch", "type", "id", "parent", "ancestor",
           "label", "creator", "contributor", "mention", "lastmodified", "created"}
_DATES = {"lastmodified", "created"}
_PEOPLE = {"creator", "contributor", "mention"}
_ORDER = {"title", "lastmodified", "created", "id"}


def _tokens(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > _LIMIT:
        raise ValueError("CQL must be a string of at most 16 KiB")
    out, pos = [], 0
    while pos < len(text):
        ch = text[pos]
        if ch.isspace():
            pos += 1
            continue
        if ch in "\"'":
            quote, value = ch, []
            pos += 1
            while pos < len(text) and text[pos] != quote:
                if text[pos] == "\\":
                    pos += 1
                    if pos == len(text):
                        raise ValueError("Unterminated CQL escape")
                value.append(text[pos])
                pos += 1
            if pos == len(text):
                raise ValueError("Unterminated CQL string")
            out.append(("string", "".join(value)))
            pos += 1
        elif ch in "(),":
            out.append((ch, ch))
            pos += 1
        elif ch in "=!<>~":
            op = text[pos:pos + 2] if text[pos:pos + 2] in {"!=", ">=", "<=", "!~"} else ch
            if op == "!":
                raise ValueError("Invalid CQL operator")
            out.append(("op", op))
            pos += len(op)
        else:
            end = pos
            while end < len(text) and not text[end].isspace() and text[end] not in "(),=!<>~\"'":
                end += 1
            out.append(("word", text[pos:end]))
            pos = end
    return out


class _Parser:
    def __init__(self, text):
        self.tokens, self.pos, self.depth, self.atoms = _tokens(text), 0, 0, 0

    def peek(self, value=None):
        token = self.tokens[self.pos] if self.pos < len(self.tokens) else None
        return token if value is None else bool(token and token[0] != "string" and token[1].upper() == value)

    def take(self, value=None):
        token = self.peek()
        if token is None or value is not None and not self.peek(value):
            raise ValueError("Incomplete or malformed CQL expression")
        self.pos += 1
        return token

    def parse(self):
        tree = self.expression("OR") if self.peek() and not self.peek("ORDER") else None
        order = []
        if self.peek("ORDER"):
            self.take("ORDER")
            self.take("BY")
            while True:
                kind, field = self.take()
                field = field.lower()
                if kind not in {"word", "string"} or field not in _ORDER:
                    raise ValueError("Unsupported CQL sort field")
                reverse = False
                if self.peek("ASC") or self.peek("DESC"):
                    reverse = self.take()[1].upper() == "DESC"
                order.append((field, reverse))
                if not self.peek(","):
                    break
                self.take(",")
        if self.peek() is not None:
            raise ValueError("Unexpected trailing CQL input")
        return tree, order

    def expression(self, level):
        read = (lambda: self.expression("AND")) if level == "OR" else self.unary
        nodes = [read()]
        while self.peek(level):
            self.take(level)
            nodes.append(read())
        return nodes[0] if len(nodes) == 1 else (level, nodes)

    def unary(self):
        self.depth += 1
        if self.depth > 64:
            raise ValueError("CQL nesting exceeds 64 levels")
        try:
            if self.peek("NOT"):
                self.take("NOT")
                return ("NOT", self.unary())
            if self.peek("("):
                self.take("(")
                result = self.expression("OR")
                self.take(")")
                return result
            return self.atom()
        finally:
            self.depth -= 1

    def value(self):
        kind, value = self.take()
        if kind not in {"word", "string"}:
            raise ValueError("Expected a CQL literal")
        if kind == "word" and value.upper() in {"AND", "OR", "NOT", "ORDER", "BY", "IN"}:
            raise ValueError("Reserved CQL words must be quoted")
        if kind == "word" and self.peek("("):
            self.take("(")
            arguments = []
            if not self.peek(")"):
                arg_kind, argument = self.take()
                if arg_kind not in {"word", "string"}:
                    raise ValueError("Invalid CQL function argument")
                arguments.append(argument)
            self.take(")")
            return ("function", value.lower(), arguments)
        return ("literal", value)

    def atom(self):
        kind, field = self.take()
        field = field.lower()
        if kind not in {"word", "string"} or field not in _FIELDS:
            raise ValueError("Unsupported CQL field")
        kind, operator = self.take()
        operator = operator.upper()
        if kind == "word" and operator == "NOT":
            self.take("IN")
            operator = "NOT IN"
        elif kind != "op" and not (kind == "word" and operator == "IN"):
            raise ValueError("Unsupported CQL operator")
        if operator in {"IN", "NOT IN"}:
            self.take("(")
            values = [self.value()]
            while self.peek(","):
                self.take(",")
                values.append(self.value())
            self.take(")")
        else:
            values = [self.value()]
        self.atoms += 1
        if self.atoms > 256:
            raise ValueError("CQL exceeds 256 conditions")
        return ("ATOM", field, operator, values)


def _as_time(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, timezone.utc)
    if isinstance(value, str):
        try:
            return _as_time(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _date_value(value, today):
    relative = re.fullmatch(r"([+-]?\d+)([mhdwy])", value, re.I)
    if relative:
        seconds = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}
        try:
            return today + timedelta(seconds=int(relative[1]) * seconds[relative[2].lower()])
        except (OverflowError, ValueError):
            raise ValueError("CQL relative date is outside the supported range") from None
    actual = _as_time(value)
    if actual is None:
        raise ValueError("Invalid CQL date")
    return actual


def _body(row):
    value = row.get("body") or ""
    return str((value.get("storage") or {}).get("value") or "") if isinstance(value, dict) else str(value)


def _ids(values):
    if values is None:
        return []
    if isinstance(values, (str, dict)):
        values = [values]
    return [str(value.get("id", value.get("name", "")) if isinstance(value, dict) else value) for value in values]


def _people(value):
    if isinstance(value, dict):
        return [str(value[key]) for key in ("username", "userKey", "name") if value.get(key)]
    return [str(value)] if value else []


def _field(row, field, ancestors, labels):
    if field == "space":
        value = row.get("space") or ""
        return [str(value.get("key") or "") if isinstance(value, dict) else str(value)]
    if field in {"title", "type", "id", "parent"}:
        value = row.get(field, "page" if field == "type" else "")
        return [str(value)] if value not in (None, "") else []
    if field in {"text", "sitesearch"}:
        return [str(row.get("title") or "") + " " + _body(row)]
    if field == "ancestor":
        return _ids(ancestors(row) if ancestors else row.get("ancestors"))
    if field == "label":
        return _ids(labels(row) if labels else row.get("labels"))
    if field in _DATES:
        history = row.get("history") or {}
        value = history.get("createdDate") if field == "created" else None
        value = value or (row.get("version") or {}).get("when") or row.get("date")
        actual = _as_time(value)
        return [actual] if actual else []
    author = _people((row.get("version") or {}).get("by") or row.get("author"))
    if field == "creator":
        return _people((row.get("history") or {}).get("createdBy")) or author
    if field == "contributor":
        return list({*author, *(person for item in row.get("contributors", []) for person in _people(item))})
    if field == "mention":
        explicit = row.get("mentions") or []
        return [person for item in explicit for person in _people(item)] + re.findall(
            r'ri:(?:userkey|username)=["\']([^"\']+)', _body(row), re.I)
    raise ValueError("Unsupported CQL field")


def _compile(tree, today, current_user, ancestors, labels, resolver=None):
    if tree is None:
        return lambda row: True
    if tree[0] == "NOT":
        child = _compile(tree[1], today, current_user, ancestors, labels, resolver)
        return lambda row: not child(row)
    if tree[0] in {"AND", "OR"}:
        children = [_compile(node, today, current_user, ancestors, labels, resolver) for node in tree[1]]
        return (lambda row: all(fn(row) for fn in children)) if tree[0] == "AND" else (lambda row: any(fn(row) for fn in children))
    _, field, operator, raw = tree
    allowed = {"=", "!=", "IN", "NOT IN"}
    if field in _DATES:
        allowed |= {">", ">=", "<", "<="}
    if field in {"title", "text", "sitesearch"}:
        allowed |= {"~", "!~"}
    if operator not in allowed:
        raise ValueError("Unsupported CQL operator for field")
    wanted = []
    for item in raw:
        if item[0] == "function":
            _, name, arguments = item
            if name == "currentuser" and field in _PEOPLE and not arguments:
                value = resolver("currentUser()") if resolver else current_user
                if not value:
                    raise ValueError("currentUser() requires a configured current user")
            elif name == "now" and field in _DATES and len(arguments) <= 1:
                value = _date_value(arguments[0], today) if arguments else today
            else:
                raise ValueError("Unsupported CQL function for field")
        else:
            value = item[1]
            if resolver and field in _PEOPLE:
                value = resolver(value)
        if field in _DATES:
            value = value if isinstance(value, datetime) else _date_value(value, today)
        else:
            value = str(value).casefold()
        wanted.append(value)

    def predicate(row):
        actual = _field(row, field, ancestors, labels)
        if not actual:
            return False
        if field not in _DATES:
            actual = [value.casefold() for value in actual]
        if operator in {"~", "!~"}:
            match = any(wanted[0] in value for value in actual)
        elif operator in {">", ">=", "<", "<="}:
            a, b = actual[0], wanted[0]
            return {">": lambda: a > b, ">=": lambda: a >= b,
                    "<": lambda: a < b, "<=": lambda: a <= b}[operator]()
        else:
            match = any(value in wanted for value in actual)
        return not match if operator in {"!=", "NOT IN", "!~"} else match
    return predicate


def _sort(rows, order):
    def value(row, field):
        if field == "id":
            identifier = str(row.get("id") or "")
            return (0, int(identifier)) if identifier.isdigit() else (1, identifier)
        if field in _DATES:
            return (_field(row, field, None, None) or [datetime.min.replace(tzinfo=timezone.utc)])[0]
        return str(row.get(field) or "").casefold()
    rows.sort(key=lambda row: value(row, "id"))
    for field, reverse in reversed(order or [("lastmodified", True)]):
        rows.sort(key=lambda row: value(row, field), reverse=reverse)
    return rows


def filter_content(rows, cql, today, current_user="", ancestor_resolver=None, labels_resolver=None):
    """Return matching native content rows, sorted; resolvers receive a native row."""
    tree, order = _Parser(cql or "").parse()
    current = _as_time(today)
    if current is None:
        raise ValueError("CQL requires a valid reference date")
    predicate = _compile(tree, current, current_user, ancestor_resolver, labels_resolver)
    return _sort([row for row in rows if predicate(row)], order)


def _pred(clause, today, mr=None):
    """Compatibility predicate over the historical flat page corpus."""
    tree, _ = _Parser(clause).parse()
    return _compile(tree, _as_time(today), "", None, None, mr)


def search_pages(store, cql, limit=25, mention_resolver=None):
    """Search the legacy injected corpus without altering its page record shape."""
    now = getattr(store, "now", None)
    today = (now() if callable(now) else now) or store.config.base_date
    tree, order = _Parser(cql or "").parse()
    predicate = _compile(tree, _as_time(today), store.config.current_user, None, None, mention_resolver)
    return _sort([row for row in store.confluence_pages() if predicate(row)], order)[:max(0, int(limit))]


def search_terms(cql):
    """Literal text terms for result excerpts; quoted boolean words remain intact."""
    tree, _ = _Parser(cql or "").parse()
    result = []
    def visit(node):
        if node is None:
            return
        if node[0] in {"AND", "OR"}:
            for child in node[1]:
                visit(child)
        elif node[0] == "NOT":
            visit(node[1])
        elif node[1] in {"title", "text", "sitesearch"} and node[2] == "~" and node[3][0][0] == "literal":
            result.append(node[3][0][1])
    visit(tree)
    return result
