from xml.etree import ElementTree as ET

import pytest

from jira820.confluence_render import render_storage


def test_storage_renders_native_blocks_binary_references_and_checked_tasks():
    source = '''<h1>1 Heading</h1><ac:image ac:width="320"><ri:attachment ri:filename="한글 &amp; image.png" /></ac:image>
    <ac:link><ri:attachment ri:filename="report.pdf" /><ac:plain-text-link-body><![CDATA[Download & read]]></ac:plain-text-link-body></ac:link>
    <ac:structured-macro ac:name="code"><ac:parameter ac:name="language">sql</ac:parameter><ac:plain-text-body><![CDATA[select '<script>';]]></ac:plain-text-body></ac:structured-macro>
    <ac:structured-macro ac:name="info"><ac:rich-text-body><p>Note</p></ac:rich-text-body></ac:structured-macro>
    <ac:task-list><ac:task><ac:task-status>complete</ac:task-status><ac:task-body>Done</ac:task-body></ac:task></ac:task-list>
    <ac:link><ri:user ri:userkey="conf-user-alice" /></ac:link>'''
    view = render_storage(source, "42", {"alice": {"displayName": "Alice"}})
    tree = ET.fromstring("<body>" + view + "</body>")
    assert tree.find("img").get("width") == "320"
    assert tree.find("img").get("src").startswith("/download/attachments/42/")
    assert tree.find("a").text == "Download & read"
    assert tree.find("pre/code").text == "select '<script>';"
    assert tree.find("ul/li/input").get("checked") == "checked"
    assert tree.findall("a")[-1].text == "Alice"
    assert "Unsupported mock macro" in render_storage('<ac:structured-macro ac:name="unknown" />', "42")


@pytest.mark.parametrize("source", ["<!DOCTYPE x><ac:image />", '<ac:image><ri:attachment /></bad>'])
def test_invalid_storage_is_not_silently_rendered(source):
    with pytest.raises(ValueError):
        render_storage(source, "42")
