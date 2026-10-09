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


# 结构性行首：这些标记必须保持“另起一行”，不能被软换行合并掉
_RE_STRUCT_START = re.compile(
    rf"^(第{_NUM}[章节条]|[一二三四五六七八九十]+[、.．]|（[一二三四五六七八九十]+）|\d+[、.．])"
)

# 元数据行（发文字号 / 日期）：通常独立成行，不能被上一行吞掉
_RE_META_LINE = re.compile(
    r"^(?:[\u4e00-\u9fa5A-Za-z]{0,12}[〔\[（(](?:19|20)\d{2}[〕\]）)]\s*第?\s*\d+\s*号"
    r"|(?:19|20)\d{2}\s*[年./-])"
)

# 只有足够长的行才可能来自 PDF 的软换行（标题行通常较短）
_MIN_WRAP_LEN = 12

# PDF 页眉/页脚：整行只是页码的行，直接丢弃（避免混入条文原文与引用）
_PAGE_LINE_PATTERNS = (
    re.compile(r"^[-—–]+\s*\d{1,4}\s*[-—–]+$"),          # - 1 - / — 12 —
    re.compile(r"^第\s*\d{1,4}\s*页\s*(?:/\s*共\s*\d+\s*页)?$"),  # 第 1 页 / 第1页/共20页
    re.compile(r"^共\s*\d{1,4}\s*页$"),                    # 共 20 页
)


def _is_page_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and any(p.match(stripped) for p in _PAGE_LINE_PATTERNS)


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _join_soft_wrapped_lines(lines: list[str]) -> list[str]:
    """合并 PDF 软换行：把“教育培 / 训机构”这种被换行切断的汉字重新接上。

    仅在**前一行末字符与后一行首字符都是汉字**、且后一行不是结构标记行时合并，
    因此不会破坏“第X条 / 一、”这类真正另起一行的结构。
    """
    out: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if out and out[-1] and stripped:
            prev = out[-1]
            if (
                _is_cjk(prev[-1])
                and _is_cjk(stripped[0])
                and len(prev) >= _MIN_WRAP_LEN
                and not _RE_STRUCT_START.match(stripped)
                and not _RE_META_LINE.match(stripped)
            ):
                out[-1] = prev + stripped
                continue
        out.append(line)
    return out


def normalize_text(text: str) -> str:
    """统一换行与空白，合并 PDF 软换行，保留段落结构。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.rstrip() for line in text.split("\n")]
    lines = [line for line in lines if not _is_page_line(line)]
    lines = _join_soft_wrapped_lines(lines)
    text = "\n".join(lines)
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
