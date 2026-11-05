"""Small DC storage-to-view renderer for deterministic document/attachment tests.

This is not a general Confluence macro engine. Unknown macros remain explicit.
"""
from html import escape
import re
from urllib.parse import quote
from xml.etree import ElementTree as ET

AC, RI = "http://atlassian.com/content", "http://atlassian.com/resource/identifier"


def render_storage(value, page_id, users=None):
    if not re.search(r"<(?:ac|ri):", value):
        return value
    markup = re.sub(r'<!\[CDATA\[[\s\S]*?\]\]>', '', value)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", markup, re.I):
        raise ValueError("Storage declarations are not supported")
    try:
        root = ET.fromstring(f'<root xmlns:ac="{AC}" xmlns:ri="{RI}">{value}</root>')
    except ET.ParseError as exc:
        raise ValueError("Invalid Confluence storage XML") from exc
    users = users or {}

    def content(node):
        return escape(node.text or "") + "".join(render(child) + escape(child.tail or "") for child in node)

    def resource(node):
        attachment = node.find(f"{{{RI}}}attachment")
        if attachment is not None:
            name = attachment.get(f"{{{RI}}}filename", "")
            return f"/download/attachments/{page_id}/{quote(name, safe='')}", name
        person = node.find(f"{{{RI}}}user")
        if person is not None:
            key = person.get(f"{{{RI}}}userkey", "")
            username = key.removeprefix("conf-user-")
            user = users.get(username, {})
            return "/display/~" + quote(username, safe=""), user.get("displayName") or user.get("name") or username
        return "", ""

    def render(node):
        tag = node.tag
        if tag == f"{{{AC}}}image":
            href, label = resource(node)
            width = node.get(f"{{{AC}}}width", "")
            attrs = ' width="' + width + '"' if width.isdigit() else ""
            return '<img src="' + escape(href, quote=True) + '" alt="' + escape(node.get(f"{{{AC}}}alt", label), quote=True) + '"' + attrs + ' />'
        if tag == f"{{{AC}}}link":
            href, label = resource(node)
            text = node.find(f"{{{AC}}}plain-text-link-body")
            return '<a href="' + escape(href, quote=True) + '">' + escape(text.text if text is not None and text.text else label) + '</a>'
        if tag == f"{{{AC}}}structured-macro":
            name = node.get(f"{{{AC}}}name", "")
            params = {item.get(f'{{{AC}}}name',''): ''.join(item.itertext()) for item in node.findall(f'{{{AC}}}parameter')}
            if name in {"code", "noformat"}:
                body = node.find(f"{{{AC}}}plain-text-body")
                language = next((p.text for p in node.findall(f"{{{AC}}}parameter") if p.get(f"{{{AC}}}name") == "language"), "")
                return '<pre><code class="language-' + escape(language or "", quote=True) + '">' + escape(body.text or "" if body is not None else "") + '</code></pre>'
            body = node.find(f"{{{AC}}}rich-text-body")
            text = content(body) if body is not None else ''
            if name == 'expand':
                return '<details><summary>' + escape(params.get('title') or 'Click here to expand...') + '</summary>' + text + '</details>'
            if name == 'excerpt':
                return '' if params.get('hidden') == 'true' else text
            if name == 'panel':
                return '<div class="panel"><strong>' + escape(params.get('title','')) + '</strong>' + text + '</div>'
            if name == 'status':
                return '<span class="status">' + escape(params.get('title','')) + '</span>'
            if name == 'anchor':
                return '<span id="' + escape(params.get('',''),quote=True) + '"></span>'
            if name in {"info", "note", "tip", "warning"}:
                return '<div class="confluence-information-macro confluence-information-macro-' + name + '">' + (content(body) if body is not None else "") + '</div>'
            return '<div class="confluence-unsupported-macro">Unsupported mock macro: ' + escape(name) + '</div>'
        if tag == f"{{{AC}}}task-list":
            return '<ul class="inline-task-list">' + content(node) + '</ul>'
        if tag == f"{{{AC}}}task":
            checked = node.findtext(f"{{{AC}}}task-status") == "complete"
            body = node.find(f"{{{AC}}}task-body")
            return '<li><input type="checkbox" disabled="disabled"' + (' checked="checked"' if checked else '') + ' />' + (content(body) if body is not None else '') + '</li>'
        if tag.startswith("{"):
            return content(node)
        attrs = "".join(' ' + key + '="' + escape(val, quote=True) + '"' for key, val in node.attrib.items())
        return '<' + tag + attrs + (' />' if tag in {"br", "hr", "img", "input", "col"} else '>' + content(node) + '</' + tag + '>')
    return content(root)
