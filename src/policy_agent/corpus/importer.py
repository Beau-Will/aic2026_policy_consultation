"""语料导入：支持 md / txt / html / pdf / docx → 归一化文本 + 元数据猜测。"""

from __future__ import annotations

import re
from pathlib import Path

from .models import CorpusDocument, sha256_text
from .split import normalize_text, split_articles

SUPPORTED_SUFFIXES = (".md", ".markdown", ".txt", ".html", ".htm", ".pdf", ".docx")

_RE_DOC_NUMBER = re.compile(
    r"[\u4e00-\u9fa5A-Za-z]{0,12}[〔\[（(](?:19|20)\d{2}[〕\]）)]\s*第?\s*\d+\s*号"
)
_RE_DATE = re.compile(r"((?:19|20)\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?")
_RE_ISSUER = re.compile(
    r"^[\u4e00-\u9fa5]{2,30}(?:部|委|局|厅|署|办|办公室|政府|人民法院|人民检察院)$"
)


def _fmt_date(m: re.Match[str]) -> str:
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


_RE_MARKER_LINE = re.compile(r"^(第[一二三四五六七八九十百零〇两0-9]+[章节条]|[一二三四五六七八九十]+[、.．])")


def _looks_like_marker(line: str) -> bool:
    return bool(_RE_MARKER_LINE.match(line))


def _read_md_txt(path: Path) -> tuple[str, str | None]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    title = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            break
        # 跳过章节/条号行，避免把“第一章 总则”误当成标题
        if _looks_like_marker(stripped):
            continue
        title = stripped
        break
    return text, title


def _read_html(path: Path) -> tuple[str, str | None]:
    from bs4 import BeautifulSoup

    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else None
    text = soup.get_text("\n")
    return text, title


def _read_pdf(path: Path) -> tuple[str, str | None]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    meta_title = None
    try:
        if reader.metadata and reader.metadata.title:
            meta_title = str(reader.metadata.title).strip() or None
    except Exception:
        meta_title = None
    return "\n\n".join(pages), meta_title


def _read_docx(path: Path) -> tuple[str, str | None]:
    import docx

    document = docx.Document(str(path))
    paragraphs = [p.text for p in document.paragraphs]
    text = "\n".join(paragraphs)
    title = next((p.strip() for p in paragraphs if p.strip()), None)
    return text, title


def load_text(path: Path) -> tuple[str, str | None]:
    """按扩展名读取文件，返回 (原文文本, 猜测的标题)。"""
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown", ".txt"):
        return _read_md_txt(path)
    if suffix in (".html", ".htm"):
        return _read_html(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    raise ValueError(f"不支持的文件格式：{suffix}（支持 {'/'.join(SUPPORTED_SUFFIXES)}）")


def guess_metadata(text: str) -> dict[str, str | None]:
    """从原文正文中尽力猜测发文字号、发文机关与日期。"""
    result: dict[str, str | None] = {
        "doc_number": None,
        "issuer": None,
        "publish_date": None,
        "effective_date": None,
    }
    m = _RE_DOC_NUMBER.search(text)
    if m:
        result["doc_number"] = re.sub(r"\s+", "", m.group(0))

    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if _RE_ISSUER.match(stripped):
            result["issuer"] = stripped
            break

    dates = [_fmt_date(m) for m in _RE_DATE.finditer(text[:4000])]
    if dates:
        result["publish_date"] = dates[0]
        result["effective_date"] = dates[-1] if len(dates) > 1 else None
    return result


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fa5-]+", "-", name).strip("-")
    return slug[:60] or "doc"


def build_document(
    path: Path,
    *,
    title: str | None = None,
    issuer: str | None = None,
    doc_number: str | None = None,
    publish_date: str | None = None,
    effective_date: str | None = None,
    region: str | None = None,
    source_url: str | None = None,
) -> CorpusDocument:
    """读取文件并构建条文级语料文档。显式传入的元数据优先于自动猜测。"""
    text, guessed_title = load_text(path)
    text = normalize_text(text)
    if not text:
        raise ValueError(f"文件内容为空或无法解析：{path}")

    guessed = guess_metadata(text)
    content_hash = sha256_text(text)
    # doc_id 由文件名派生：同一份文件重新导入会覆盖旧版本（便于政策更新）。
    doc_id = _slugify(path.stem)

    articles = split_articles(text)
    for index, article in enumerate(articles):
        article.doc_id = doc_id
        article.article_id = f"{doc_id}#{index:04d}"

    return CorpusDocument(
        doc_id=doc_id,
        title=(title or guessed_title or path.stem).strip(),
        raw_text=text,
        source_hash=content_hash,
        issuer=issuer or guessed["issuer"],
        doc_number=doc_number or guessed["doc_number"],
        publish_date=publish_date or guessed["publish_date"],
        effective_date=effective_date or guessed["effective_date"],
        region=region,
        source_url=source_url,
        articles=articles,
    )
