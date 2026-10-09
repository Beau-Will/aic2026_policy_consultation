"""语料库领域模型。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CorpusArticle:
    """一条条文级记录。"""

    article_id: str
    doc_id: str
    ordinal: int
    text: str
    chapter_path: str | None = None
    article_no: str | None = None
    heading: str | None = None


@dataclass
class CorpusDocument:
    """一份权威原文（政策、法规、公告、申报指南等）。"""

    doc_id: str
    title: str
    raw_text: str
    source_hash: str
    issuer: str | None = None
    doc_number: str | None = None
    publish_date: str | None = None
    effective_date: str | None = None
    region: str | None = None
    source_url: str | None = None
    articles: list[CorpusArticle] = field(default_factory=list)
