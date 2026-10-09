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
