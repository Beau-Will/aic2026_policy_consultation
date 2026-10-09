"""条文切分：把一份原文切成“章节路径 + 条号 + 条文正文”的可引用单元。

中文法规/政策常见层级：第X章 / 第X节 / 第X条；
通知类文件常常没有“条”，退化为“一、二、三、”编号段落。
"""

from __future__ import annotations

import re

from .models import CorpusArticle

_NUM = r"[一二三四五六七八九十百零〇两0-9]+"

_RE_CHAPTER = re.compile(rf"^第{_NUM}章[\s　、.]*(.*)$")
_RE_SECTION = re.compile(rf"^第{_NUM}节[\s　、.]*(.*)$")
_RE_ARTICLE = re.compile(rf"^(第{_NUM}条)[\s　、.]*(.*)$")
_RE_ENUM = re.compile(rf"^([一二三四五六七八九十]+)[、.．][\s　]*(.*)$")
_RE_INT_ENUM = re.compile(r"^(\d{1,3})[、.．][\s]*(.*)$")


def normalize_text(text: str) -> str:
    """统一换行与空白，保留段落结构。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.rstrip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        out.append(line)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _join_body(lines: list[str]) -> str:
    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def split_articles(text: str) -> list[CorpusArticle]:
    """把原文切分为条文级记录（article_id 留空，由调用方按 doc_id 赋值）。"""
    text = normalize_text(text)
    lines = text.split("\n")

    chapter_path: list[str] = []
    current_chapter: str | None = None
    current_section: str | None = None

    articles: list[CorpusArticle] = []
    preamble: list[str] = []
    body: list[str] = []
    article_no: str | None = None
    heading: str | None = None

    def chapter_str() -> str | None:
        parts = [p for p in (current_chapter, current_section) if p]
        return " / ".join(parts) if parts else None

    def flush() -> None:
        nonlocal body, article_no, heading
        if article_no is None and not body:
            return
        articles.append(
            CorpusArticle(
                article_id="",
                doc_id="",
                ordinal=len(articles),
                text=_join_body(body),
                chapter_path=chapter_str(),
                article_no=article_no,
                heading=heading,
            )
        )
        body = []
        article_no = None
        heading = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if article_no is not None or body:
                body.append("")
            continue

        m_chapter = _RE_CHAPTER.match(line)
        if m_chapter:
            flush()
            current_chapter = line
            current_section = None
            continue

        m_section = _RE_SECTION.match(line)
        if m_section:
            flush()
            current_section = line
            continue

        m_article = _RE_ARTICLE.match(line)
        if m_article:
            flush()
            article_no = m_article.group(1)
            heading = m_article.group(2).strip() or None
            if heading:
                body.append(heading)
            continue

        if article_no is not None:
            body.append(line)
        elif articles:
            body.append(line)
        else:
            preamble.append(line)

    if article_no is not None or body:
        flush()

    if articles:
        if preamble:
            first = articles[0]
            pre = _join_body(preamble)
            if pre:
                first.text = (pre + "\n\n" + first.text).strip()
        return articles

    # 没有“第X条”：退化为“一、二、三、”编号段落。
    enum_articles: list[CorpusArticle] = []
    cur_head: str | None = None
    cur_no: str | None = None
    cur_body: list[str] = []
    pre: list[str] = []

    def flush_enum() -> None:
        nonlocal cur_body, cur_no, cur_head
        if cur_no is None and not cur_body:
            return
        enum_articles.append(
            CorpusArticle(
                article_id="",
                doc_id="",
                ordinal=len(enum_articles),
                text=_join_body(cur_body),
                chapter_path=None,
                article_no=cur_no,
                heading=cur_head,
            )
        )
        cur_body = []
        cur_no = None
        cur_head = None

    for line in (ln.strip() for ln in lines):
        if not line:
            if cur_no is not None or cur_body:
                cur_body.append("")
            continue
        m_enum = _RE_ENUM.match(line) or _RE_INT_ENUM.match(line)
        if m_enum:
            flush_enum()
            cur_no = m_enum.group(1)
            cur_head = m_enum.group(2).strip() or None
            if cur_head:
                cur_body.append(cur_head)
            continue
        if cur_no is not None:
            cur_body.append(line)
        else:
            pre.append(line)

    if cur_no is not None or cur_body:
        flush_enum()

    if enum_articles:
        if pre:
            p = _join_body(pre)
            if p:
                enum_articles[0].text = (p + "\n\n" + enum_articles[0].text).strip()
        return enum_articles

    # 完全没有可识别编号：整篇作为一条。
    whole = _join_body([ln for ln in lines])
    if not whole:
        return []
    return [
        CorpusArticle(
            article_id="",
            doc_id="",
            ordinal=0,
            text=whole,
            chapter_path=None,
            article_no=None,
            heading=None,
        )
    ]
