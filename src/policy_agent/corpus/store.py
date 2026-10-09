"""本地语料库：SQLite 存储 + FTS5 全文索引 + jieba 分词 + BM25 排序。

检索完全在本地完成，不依赖任何外部服务；引用必须能回指到真实条文。
"""

from __future__ import annotations

import math
import re
import sqlite3
import threading
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import jieba

from .models import CorpusDocument

_MAX_QUERY_TOKENS = 64
_FTS_WEIGHTS = (0.0, 0.0, 3.0, 2.0, 1.0)  # article_id, doc_id, title, heading, body

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    issuer        TEXT,
    doc_number    TEXT,
    publish_date  TEXT,
    effective_date TEXT,
    region        TEXT,
    source_url    TEXT,
    source_hash   TEXT,
    raw_text      TEXT,
    imported_at   TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS articles (
    article_id   TEXT PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    ordinal      INTEGER NOT NULL,
    chapter_path TEXT,
    article_no   TEXT,
    heading      TEXT,
    text         TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_articles_doc ON articles(doc_id);
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    article_id UNINDEXED,
    doc_id UNINDEXED,
    title,
    heading,
    body,
    tokenize='unicode61'
);
"""


def normalize_for_match(text: str) -> str:
    """用于引文核验的归一化：去掉空白与全部标点/符号，只保留文字与字母数字。"""
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            continue
        category = unicodedata.category(ch)
        if category.startswith("P") or category.startswith("S") or category.startswith("Z"):
            continue
        out.append(ch.casefold())
    return "".join(out)


def tokenize(text: str) -> list[str]:
    """中文分词，过滤掉纯空白/标点 token。"""
    tokens: list[str] = []
    for token in jieba.lcut(text or ""):
        token = token.strip()
        if not token:
            continue
        if all(unicodedata.category(c).startswith(("P", "S", "Z")) for c in token):
            continue
        tokens.append(token)
    return tokens


_STOPWORDS = {
    "如何", "什么", "哪些", "怎样", "怎么", "需要", "请问", "关于", "以及", "我们",
    "可以", "是否", "应该", "多少", "为什么", "这个", "那个", "一个", "进行", "相关",
    "有关", "对于", "如果", "并且", "或者", "但是",
}
_STOP_CHARS = set("的了和与及等是在为有或对从到以之其该本者我你他她它们这那多少")


def query_tokens(text: str) -> list[str]:
    """检索用 query token：过滤常见虚词，避免被“的/是/有”这类词误命中。"""
    out: list[str] = []
    for token in tokenize(text):
        if token in _STOPWORDS:
            continue
        if len(token) == 1 and token in _STOP_CHARS:
            continue
        out.append(token)
    return out


def _fts_query(tokens: Iterable[str], joiner: str = " OR ") -> str:
    parts = []
    for token in list(tokens)[:_MAX_QUERY_TOKENS]:
        escaped = token.replace('"', '""')
        parts.append(f'"{escaped}"')
    return joiner.join(parts)


def _snippet(text: str, tokens: list[str], width: int = 120) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= width * 2:
        return text
    pos = -1
    for token in tokens:
        if len(token) < 2:
            continue
        found = text.find(token)
        if found >= 0:
            pos = found
            break
    if pos < 0:
        return text[: width * 2] + "…"
    start = max(0, pos - width // 2)
    end = min(len(text), pos + width)
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


class CorpusStore:
    """语料库读写句柄。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- 写入
    def add_document(self, doc: CorpusDocument) -> int:
        """写入/覆盖一份文档及其条文，返回写入的条文数。"""
        with self._lock:
            cur = self._conn
            cur.execute("DELETE FROM articles_fts WHERE doc_id = ?", (doc.doc_id,))
            cur.execute("DELETE FROM articles WHERE doc_id = ?", (doc.doc_id,))
            cur.execute(
                """
                INSERT INTO documents
                    (doc_id, title, issuer, doc_number, publish_date, effective_date,
                     region, source_url, source_hash, raw_text, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(doc_id) DO UPDATE SET
                    title=excluded.title, issuer=excluded.issuer,
                    doc_number=excluded.doc_number, publish_date=excluded.publish_date,
                    effective_date=excluded.effective_date, region=excluded.region,
                    source_url=excluded.source_url, source_hash=excluded.source_hash,
                    raw_text=excluded.raw_text, imported_at=datetime('now')
                """,
                (
                    doc.doc_id,
                    doc.title,
                    doc.issuer,
                    doc.doc_number,
                    doc.publish_date,
                    doc.effective_date,
                    doc.region,
                    doc.source_url,
                    doc.source_hash,
                    doc.raw_text,
                ),
            )
            for article in doc.articles:
                cur.execute(
                    """
                    INSERT INTO articles
                        (article_id, doc_id, ordinal, chapter_path, article_no, heading, text)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.article_id,
                        article.doc_id,
                        article.ordinal,
                        article.chapter_path,
                        article.article_no,
                        article.heading,
                        article.text,
                    ),
                )
                heading_tokens = " ".join(tokenize(article.heading or ""))
                body_tokens = " ".join(tokenize(article.text))
                cur.execute(
                    """
                    INSERT INTO articles_fts (article_id, doc_id, title, heading, body)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (article.article_id, doc.doc_id, " ".join(tokenize(doc.title)),
                     heading_tokens, body_tokens),
                )
            self._conn.commit()
        return len(doc.articles)

    def reset(self) -> None:
        """清空整个语料库（保留表结构），用于重新导入/重建索引。"""
        with self._lock:
            self._conn.executescript(
                "DROP TABLE IF EXISTS articles_fts;"
                "DROP TABLE IF EXISTS articles;"
                "DROP TABLE IF EXISTS documents;"
            )
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def has_document(self, doc_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM documents WHERE doc_id = ? LIMIT 1", (doc_id,)
            ).fetchone()
        return row is not None

    # ---------------------------------------------------------------- 查询
    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        tokens = query_tokens(query)
        if not tokens:
            return []
        limit = max(1, min(int(limit), 50))
        candidates = max(limit * 5, 20)

        rows = self._match(tokens, " AND ", candidates)
        used_and = bool(rows)
        if not rows:
            rows = self._match(tokens, " OR ", candidates)

        scored: list[tuple[int, sqlite3.Row]] = []
        for row in rows:
            body_tokens = set(tokenize(row["text"]))
            matched = sum(1 for token in tokens if token in body_tokens)
            scored.append((matched, row))

        if used_and:
            kept = [row for _m, row in scored]
        else:
            need = 1 if len(tokens) == 1 else max(2, math.ceil(len(tokens) * 0.5))
            kept = [row for matched, row in scored if matched >= need]

        return [self._hit_from_row(row, tokens) for row in kept[:limit]]

    def _match(self, tokens: list[str], joiner: str, limit: int) -> list[sqlite3.Row]:
        sql = f"""
            SELECT a.article_id, a.doc_id, a.ordinal, a.chapter_path, a.article_no,
                   a.heading, a.text,
                   d.title AS doc_title, d.issuer, d.doc_number, d.publish_date,
                   d.effective_date, d.region, d.source_url, d.source_hash,
                   bm25(articles_fts, {", ".join(str(w) for w in _FTS_WEIGHTS)}) AS score
            FROM articles_fts
            JOIN articles a ON a.article_id = articles_fts.article_id
            JOIN documents d ON d.doc_id = a.doc_id
            WHERE articles_fts MATCH ?
            ORDER BY score ASC, a.ordinal ASC
            LIMIT ?
        """
        with self._lock:
            return self._conn.execute(sql, (_fts_query(tokens, joiner), limit)).fetchall()

    def get_article(self, citation_id: str) -> dict[str, Any] | None:
        sql = """
            SELECT a.article_id, a.doc_id, a.ordinal, a.chapter_path, a.article_no,
                   a.heading, a.text,
                   d.title AS doc_title, d.issuer, d.doc_number, d.publish_date,
                   d.effective_date, d.region, d.source_url, d.source_hash
            FROM articles a JOIN documents d ON d.doc_id = a.doc_id
            WHERE a.article_id = ?
        """
        with self._lock:
            row = self._conn.execute(sql, (citation_id,)).fetchone()
        if row is None:
            return None
        return self._hit_from_row(row, [])

    def find_quote(self, text: str, limit: int = 10) -> list[dict[str, Any]]:
        """在库内查找包含该引文的条文（归一化后包含判定）。"""
        target = normalize_for_match(text)
        if not target:
            return []
        candidates: list[sqlite3.Row] = []
        tokens = tokenize(text)
        if tokens:
            sql = f"""
                SELECT a.article_id, a.doc_id, a.ordinal, a.chapter_path, a.article_no,
                       a.heading, a.text,
                       d.title AS doc_title, d.issuer, d.doc_number, d.publish_date,
                       d.effective_date, d.region, d.source_url, d.source_hash
                FROM articles_fts
                JOIN articles a ON a.article_id = articles_fts.article_id
                JOIN documents d ON d.doc_id = a.doc_id
                WHERE articles_fts MATCH ?
                ORDER BY bm25(articles_fts, {', '.join(str(w) for w in _FTS_WEIGHTS)}) ASC
                LIMIT 200
            """
            with self._lock:
                candidates = self._conn.execute(sql, (_fts_query(tokens),)).fetchall()
        if not candidates:
            sql_all = """
                SELECT a.article_id, a.doc_id, a.ordinal, a.chapter_path, a.article_no,
                       a.heading, a.text,
                       d.title AS doc_title, d.issuer, d.doc_number, d.publish_date,
                       d.effective_date, d.region, d.source_url, d.source_hash
                FROM articles a JOIN documents d ON d.doc_id = a.doc_id
            """
            with self._lock:
                candidates = self._conn.execute(sql_all).fetchall()

        matches: list[dict[str, Any]] = []
        for row in candidates:
            if target in normalize_for_match(row["text"]):
                matches.append(self._hit_from_row(row, tokenize(text)))
                if len(matches) >= max(1, min(limit, 50)):
                    break
        return matches

    def documents_scope(self, doc_ids: Iterable[str]) -> list[str]:
        ids = list(dict.fromkeys(doc_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        sql = f"SELECT doc_id, title, doc_number FROM documents WHERE doc_id IN ({placeholders})"
        with self._lock:
            rows = self._conn.execute(sql, ids).fetchall()
        by_id = {r["doc_id"]: r for r in rows}
        scope = []
        for doc_id in ids:
            row = by_id.get(doc_id)
            if row is None:
                continue
            number = f"（{row['doc_number']}）" if row["doc_number"] else ""
            scope.append(f"{row['title']}{number}")
        return scope

    def stats(self) -> dict[str, int]:
        with self._lock:
            docs = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            articles = self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        return {"documents": int(docs), "articles": int(articles)}

    @staticmethod
    def _hit_from_row(row: sqlite3.Row, tokens: list[str]) -> dict[str, Any]:
        keys = set(row.keys())
        score = row["score"] if "score" in keys else None
        text = row["text"]
        return {
            "citation_id": row["article_id"],
            "doc_id": row["doc_id"],
            "doc_title": row["doc_title"],
            "issuer": row["issuer"],
            "doc_number": row["doc_number"],
            "publish_date": row["publish_date"],
            "effective_date": row["effective_date"],
            "region": row["region"],
            "source_url": row["source_url"],
            "source_hash": row["source_hash"],
            "chapter_path": row["chapter_path"],
            "article_no": row["article_no"],
            "heading": row["heading"],
            "article_text": text,
            "snippet": _snippet(text, tokens),
            "score": score,
        }


_STORE: CorpusStore | None = None
_STORE_PATH: str | None = None


def get_store(db_path: str | Path | None = None) -> CorpusStore:
    """获取进程级语料库句柄；切换路径或调用 reset_store() 会重建。"""
    global _STORE, _STORE_PATH
    from ..config import Settings

    path = Path(db_path) if db_path is not None else Settings.from_env().corpus_db_path
    key = str(path)
    if _STORE is None or _STORE_PATH != key:
        if _STORE is not None:
            _STORE.close()
        _STORE = CorpusStore(path)
        _STORE_PATH = key
    return _STORE


def reset_store() -> None:
    """关闭并清空缓存的句柄（测试用）。"""
    global _STORE, _STORE_PATH
    if _STORE is not None:
        _STORE.close()
    _STORE = None
    _STORE_PATH = None
