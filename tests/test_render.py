"""Jira wiki -> HTML 렌더러(renderedFields.description) 테스트."""
from jira820.render import render_wiki


def test_empty():
    assert render_wiki("") == ""
    assert render_wiki(None) == ""


def test_headings_and_paragraph():
    out = render_wiki("h2. 제목\n본문 한 줄")
    assert "<h2>제목</h2>" in out
    assert "<p>본문 한 줄</p>" in out


def test_inline_styles():
    out = render_wiki("*굵게* _기울임_ {{mono}} +밑줄+ -취소- ^위^ ~아래~")
    assert "<strong>굵게</strong>" in out
    assert "<em>기울임</em>" in out
    assert "<code>mono</code>" in out
    assert "<ins>밑줄</ins>" in out and "<del>취소</del>" in out
    assert "<sup>위</sup>" in out and "<sub>아래</sub>" in out


def test_link_and_mention_and_image():
    out = render_wiki("[라벨|https://x.test/a] [~kim.dev] !/img.svg!")
    assert '<a href="https://x.test/a">라벨</a>' in out
    # 실 Jira DC 8.20.8 맨션 형태: a.user-hover + ViewProfile 링크
    assert 'class="user-hover"' in out and 'rel="kim.dev"' in out
    assert 'href="/secure/ViewProfile.jspa?name=kim.dev"' in out and ">kim.dev</a>" in out
    assert '<img src="/img.svg" alt="" />' in out


def test_mention_resolver_shows_display_name():
    out = render_wiki("[~x1042] 확인", mr=lambda u: "홍길동 SK" if u == "x1042" else u)
    assert 'class="user-hover"' in out and ">홍길동 SK</a>" in out


def test_confluence_link_is_plain_anchor():
    # jira820(실 Jira 준수)은 일반 앵커만 렌더 — 문서 뱃지 판별은 소비 측(URL) 몫
    out = render_wiki("[문서 제목|https://confluence.example/display/DL/page]")
    assert '<a href="https://confluence.example/display/DL/page">문서 제목</a>' in out
    assert "conf-link" not in out


def test_table_header_and_cells():
    out = render_wiki("||A||B||\n|1|2|\n|3|4|")
    assert "<table>" in out and "</table>" in out
    assert "<th>A</th><th>B</th>" in out
    assert "<td>1</td><td>2</td>" in out


def test_code_block_language_and_escaping():
    out = render_wiki("{code:python}\nif a < b & c > d:\n    pass\n{code}")
    assert '<pre class="code"><code class="lang-python">' in out
    assert "&lt;" in out and "&amp;" in out and "&gt;" in out    # 코드 내용 escape
    assert "<script" not in out.lower()


def test_quote_and_bq():
    out = render_wiki("{quote}\n인용 본문\n{quote}\nbq. 한 줄 인용")
    assert out.count("<blockquote>") == 2
    assert "인용 본문" in out and "한 줄 인용" in out


def test_panel_with_title():
    out = render_wiki("{panel:title=요약}\n본문\n{panel}")
    assert '<div class="panel">' in out
    assert '<div class="panel-title">요약</div>' in out
    assert '<div class="panel-body">' in out and "본문" in out


def test_callouts():
    for kind in ["note", "info", "warning", "tip", "success", "error"]:
        out = render_wiki("{%s}\n내용\n{%s}" % (kind, kind))
        assert 'class="callout callout-%s"' % kind in out
        assert "내용" in out


def test_lists_bullet_ordered_nested():
    out = render_wiki("* a\n** a1\n* b\n# 1\n# 2")
    assert "<ul><li>a<ul><li>a1</li></ul></li><li>b</li></ul>" in out
    assert "<ol><li>1</li><li>2</li></ol>" in out


def test_hr():
    assert "<hr />" in render_wiki("위\n\n----\n\n아래")


def test_raw_html_in_source_is_escaped():
    # 소스에 들어온 원시 HTML 은 실행되지 않게 escape (렌더러는 마크업만 태그화)
    out = render_wiki("문장 <script>alert(1)</script> <b>x</b>")
    assert "<script" not in out.lower()
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;" in out
