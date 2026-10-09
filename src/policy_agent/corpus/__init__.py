"""本地权威语料库：导入 → 条文切分 → 索引 → 检索。"""

from .importer import SUPPORTED_SUFFIXES, build_document, guess_metadata, load_text
from .models import CorpusArticle, CorpusDocument, sha256_text
from .split import normalize_text, split_articles
from .store import CorpusStore, get_store, normalize_for_match, reset_store, tokenize

__all__ = [
    "CorpusArticle",
    "CorpusDocument",
    "CorpusStore",
    "SUPPORTED_SUFFIXES",
    "build_document",
    "get_store",
    "guess_metadata",
    "load_text",
    "normalize_for_match",
    "normalize_text",
    "reset_store",
    "sha256_text",
    "split_articles",
    "tokenize",
]
