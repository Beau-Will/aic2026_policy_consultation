"""条文切分测试。"""

from __future__ import annotations

from policy_agent.corpus.split import normalize_text, split_articles


def test_split_by_article_with_chapters():
    text = """第一章 总则

第一条 为支持小微企业发展，制定本办法。
第二条 本办法适用于本市小微企业。

第二章 申报

第三条 申请补贴应提交营业执照复印件。
"""
    articles = split_articles(text)
    assert [a.article_no for a in articles] == ["第一条", "第二条", "第三条"]
    assert articles[0].chapter_path == "第一章 总则"
    assert articles[2].chapter_path == "第二章 申报"
    assert "营业执照复印件" in articles[2].text


def test_split_enum_fallback_when_no_article_marker():
    text = """一、申报对象
小微企业。

二、申报时间
4月1日至4月30日。
"""
    articles = split_articles(text)
    assert len(articles) == 2
    assert articles[0].article_no == "一"
    assert articles[1].article_no == "二"
    assert "4月1日" in articles[1].text


def test_split_whole_when_no_markers():
    text = "这是一段没有编号的政策说明文字。"
    articles = split_articles(text)
    assert len(articles) == 1
    assert articles[0].article_no is None
    assert "政策说明" in articles[0].text


def test_split_empty_text():
    assert split_articles("   ") == []


def test_normalize_text_collapses_blank_lines():
    raw = "第一行\r\n\r\n\r\n\r\n第二行"
    assert normalize_text(raw) == "第一行\n\n第二行"


def test_join_soft_wrapped_cjk_lines():
    """PDF 抽取常在词中换行，应重新接上。"""
    raw = "国家支持企业和高等学校等教育培\n训机构开展培训，培养网络安\n全人才。"
    assert normalize_text(raw) == "国家支持企业和高等学校等教育培训机构开展培训，培养网络安全人才。"


def test_keep_article_boundary_newline():
    raw = "第一条 内容甲。\n第二条 内容乙。"
    out = normalize_text(raw)
    assert out.count("\n") == 1, repr(out)
    assert [a.article_no for a in split_articles(out)] == ["第一条", "第二条"]


def test_keep_sentence_boundary_newline():
    # 标点后换行属真实断句，不合并
    out = normalize_text("……审议通过。\n根据2025年规定办理。")
    assert "\n" in out


def test_strips_pdf_page_number_lines():
    raw = "第一条 内容开始。\n- 1 -\n内容继续。\n第 2 页\n共 10 页\n第二条 内容乙。"
    out = normalize_text(raw)
    assert "- 1 -" not in out
    assert "第 2 页" not in out
    assert "共 10 页" not in out
    assert "第一条" in out and "第二条" in out


def test_does_not_strip_legitimate_numbered_content():
    # 普通带编号的正文行（如“1.”）不应被当作页码删掉
    raw = "第一条 申报材料如下：\n1. 营业执照复印件；\n2. 社保缴纳证明。"
    out = normalize_text(raw)
    assert "1. 营业执照复印件；" in out
    assert "2. 社保缴纳证明。" in out
