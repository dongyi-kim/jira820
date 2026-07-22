"""Jira wiki markup -> HTML renderer (subset) for renderedFields.description / renderedBody.

Real Jira DC returns a rendered-HTML form of text fields (description, comment body)
when expand=renderedFields / renderedBody. This renders a faithful **subset** of Jira
wiki notation so consumers exercising the rendered-HTML path get realistic markup.

Supported
  Blocks : h1.-h6.  |  {code[:lang]}..{code}  |  {noformat}..{noformat}
           {quote}..{quote} / "bq. "  |  {panel[:title=..]}..{panel}
           {note|info|warning|tip|success|error}..{..}  |  tables (||h|| / |c|)
           bullet/numbered lists (* / #, nestable)  |  ---- (hr)  |  paragraphs
  Inline : *strong*  _em_  +ins+  -del-  {{monospace}}  ^sup^  ~sub~
           [text|url] / [url]  |  !image!  |  [~username] mention

Output is well-formed, escaped HTML, faithful to Jira DC 8.20.8:
  - mentions -> <a class="user-hover" rel="user" href="/secure/ViewProfile.jspa?name=user">Name</a>
  - links    -> plain <a href> (document/Confluence badging is a consumer-side concern)
Callouts/panels use class names (`panel`, `callout callout-<type>`, `code`) for CSS.

  render_wiki(src, mr) -- mr: optional callable username -> displayName for mentions.
"""

from __future__ import annotations

import re
from html import escape

_CALLOUTS = {"note", "info", "warning", "tip", "success", "error"}


def render_wiki(src, mr=None) -> str:
    """Render Jira wiki markup string -> HTML. None/empty -> ''.
    mr: optional mention resolver username->displayName (for [~user] badges)."""
    if not src:
        return ""
    lines = str(src).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    html, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── fenced: {code} / {code:lang} / {noformat} ──
        m = re.match(r"^\{(code|noformat)(?::([^}]*))?\}\s*$", stripped)
        if m:
            lang = ""
            if m.group(1) == "code" and m.group(2):
                lm = re.search(r"(?:^|\|)\s*([A-Za-z0-9+#._-]+)\s*(?:$|\|)", m.group(2))
                if lm and "=" not in lm.group(1):
                    lang = lm.group(1)
            body, i = [], i + 1
            while i < n and not re.match(r"^\{" + m.group(1) + r"\}\s*$", lines[i].strip()):
                body.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            # 실 Jira DC(신 에디터) 와 동일한 태그: <pre class="jecodeblock"><code class="language-X">
            cls = " class=\"language-" + escape(lang, quote=True) + "\"" if lang else ""
            html.append("<pre class=\"jecodeblock\"><code" + cls + ">"
                        + escape("\n".join(body)) + "</code></pre>")
            continue

        # ── panel: {panel:title=..} .. {panel} ──
        m = re.match(r"^\{panel(?::([^}]*))?\}\s*$", stripped)
        if m:
            title = ""
            if m.group(1):
                tm = re.search(r"title=([^|]+)", m.group(1))
                if tm:
                    title = tm.group(1).strip()
            body, i = [], i + 1
            while i < n and lines[i].strip() != "{panel}":
                body.append(lines[i])
                i += 1
            i += 1
            inner = render_wiki("\n".join(body), mr)
            th = "<div class=\"panel-title\">" + _inline(title, mr) + "</div>" if title else ""
            html.append("<div class=\"panel\">" + th + "<div class=\"panel-body\">" + inner + "</div></div>")
            continue

        # ── callout: {note}/{info}/{warning}/{tip}/{success}/{error} .. {<same>} ──
        m = re.match(r"^\{(" + "|".join(_CALLOUTS) + r")(?::[^}]*)?\}\s*$", stripped)
        if m:
            kind = m.group(1)
            body, i = [], i + 1
            while i < n and not re.match(r"^\{" + kind + r"(?::[^}]*)?\}\s*$", lines[i].strip()):
                body.append(lines[i])
                i += 1
            i += 1
            inner = render_wiki("\n".join(body), mr)
            html.append("<div class=\"callout callout-" + kind + "\">" + inner + "</div>")
            continue

        # ── quote block: {quote} .. {quote} ──
        if stripped == "{quote}":
            body, i = [], i + 1
            while i < n and lines[i].strip() != "{quote}":
                body.append(lines[i])
                i += 1
            i += 1
            html.append("<blockquote>" + render_wiki("\n".join(body), mr) + "</blockquote>")
            continue

        # ── single-line blockquote: "bq. text" ──
        if stripped.startswith("bq. "):
            html.append("<blockquote>" + _inline(stripped[4:], mr) + "</blockquote>")
            i += 1
            continue

        # ── heading: hN. text ──
        m = re.match(r"^h([1-6])\.\s+(.*)$", stripped)
        if m:
            lvl = m.group(1)
            html.append("<h" + lvl + ">" + _inline(m.group(2), mr) + "</h" + lvl + ">")
            i += 1
            continue

        # ── horizontal rule ──
        if re.match(r"^-{4,}$", stripped):
            html.append("<hr />")
            i += 1
            continue

        # ── table: consecutive lines starting with '|' ──
        if stripped.startswith("|"):
            rows, i = [], i
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            html.append(_table(rows, mr))
            continue

        # ── list: lines starting with * or # (nestable by run length) ──
        if re.match(r"^[*#]+\s+", stripped):
            block, i = [], i
            while i < n and re.match(r"^[*#]+\s+", lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            html.append(_list(block, mr))
            continue

        # ── blank line ──
        if stripped == "":
            i += 1
            continue

        # ── paragraph: gather until blank / block starter ──
        para, i = [], i
        while i < n:
            s = lines[i].strip()
            if s == "" or s.startswith(("|", "{code", "{noformat", "{panel", "{quote", "bq. ")) \
                    or re.match(r"^h[1-6]\.\s", s) or re.match(r"^[*#]+\s", s) \
                    or re.match(r"^-{4,}$", s) \
                    or re.match(r"^\{(" + "|".join(_CALLOUTS) + r")(?::[^}]*)?\}\s*$", s):
                break
            para.append(lines[i].strip())
            i += 1
        if para:
            html.append("<p>" + "<br />".join(_inline(p, mr) for p in para) + "</p>")
    return "".join(html)


def _table(rows, mr=None) -> str:
    out = ["<table>"]
    for r in rows:
        body = r.strip()
        header = body.startswith("||")
        if header:
            cells = [c for c in body.split("||") if c != ""]
        else:
            inner = body[1:-1] if body.endswith("|") else body[1:]   # drop outer pipes
            cells = inner.split("|")
        tag = "th" if header else "td"
        out.append("<tr>" + "".join("<" + tag + ">" + _inline(c.strip(), mr) + "</" + tag + ">"
                                    for c in cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _list(items, mr=None) -> str:
    """Nested list from wiki markers (* bullet, # numbered), depth = marker run length.
    A change of marker type (*/#) at the same depth starts a new sibling list."""
    def one(idx, depth):
        m = re.match(r"^([*#]+)\s+(.*)$", items[idx])
        typ = "ol" if m.group(1)[-1] == "#" else "ul"
        lis, i = [], idx
        while i < len(items):
            m = re.match(r"^([*#]+)\s+(.*)$", items[i])
            marks, text = m.group(1), m.group(2)
            d, cur = len(marks), ("ol" if marks[-1] == "#" else "ul")
            if d < depth or (d == depth and cur != typ):
                break                                  # shallower / type switch -> stop
            if d > depth:
                inner, i = one(i, depth + 1)           # nested -> attach to last <li>
                if lis:
                    lis[-1] = lis[-1][:-5] + inner + "</li>"
                continue
            lis.append("<li>" + _inline(text, mr) + "</li>")
            i += 1
        return "<" + typ + ">" + "".join(lis) + "</" + typ + ">", i

    out, i = [], 0
    while i < len(items):
        frag, i = one(i, 1)
        out.append(frag)
    return "".join(out)


_IMG_RE = re.compile(r"!([^!\n|]+)(?:\|[^!\n]*)?!")
_LINK_RE = re.compile(r"\[(?:([^\]|]+)\|)?([^\]]+)\]")


def _inline(text, mr=None) -> str:
    """Escape then apply inline wiki formatting. Order matters (code first)."""
    s = escape(text or "", quote=False)

    # monospace {{...}} first so its content isn't touched by other rules
    code_spans = []

    def _stash(m):
        code_spans.append(m.group(1))
        return "\x00%d\x00" % (len(code_spans) - 1)

    s = re.sub(r"\{\{(.+?)\}\}", _stash, s)

    # images  !url!  (before links so ! isn't consumed)
    s = _IMG_RE.sub(lambda m: "<img src=\"" + m.group(1).strip() + "\" alt=\"\" />", s)

    # mentions [~user] -> user profile link (실 Jira DC 8.20.8 형태: a.user-hover + ViewProfile)
    def _mention(m):
        uid = m.group(1).strip()
        name = mr(uid) if mr else None
        u = escape(uid, quote=True)
        return ("<a class=\"user-hover\" rel=\"" + u + "\" "
                "href=\"/secure/ViewProfile.jspa?name=" + u + "\">" + escape(name or uid, quote=False) + "</a>")

    s = re.sub(r"\[~([^\]]+)\]", _mention, s)

    # links [text|url] or [url] — 실 Jira 처럼 일반 앵커(문서 뱃지 판별은 소비 측에서 URL 로)
    def _link(m):
        label, url = m.group(1), m.group(2).strip()
        shown = _basic(label) if label else escape(url, quote=False)
        return "<a href=\"" + url + "\">" + shown + "</a>"

    s = _LINK_RE.sub(_link, s)

    s = _basic(s)

    def _pop(m):
        return "<code>" + code_spans[int(m.group(1))] + "</code>"

    s = re.sub(r"\x00(\d+)\x00", _pop, s)
    return s


def _basic(s) -> str:
    """*strong* _em_ +ins+ -del- ^sup^ ~sub~ on already-escaped text."""
    if s is None:
        return ""
    s = re.sub(r"(?<![\w*])\*(\S(?:.*?\S)?)\*(?![\w*])", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w_])_(\S(?:.*?\S)?)_(?![\w_])", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w+])\+(\S(?:.*?\S)?)\+(?![\w+])", r"<ins>\1</ins>", s)
    s = re.sub(r"(?<![\w-])-(\S(?:.*?\S)?)-(?![\w-])", r"<del>\1</del>", s)
    s = re.sub(r"\^(\S(?:.*?\S)?)\^", r"<sup>\1</sup>", s)
    s = re.sub(r"~(\S(?:.*?\S)?)~", r"<sub>\1</sub>", s)
    return s
