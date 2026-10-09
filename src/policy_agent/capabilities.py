"""对外公开的 ACPs 能力（Capability）。

四个能力都 `public=True, acps_skill=True`，即会进入 ACS 技能清单：
- policy.corpus_search  ：本地语料检索（返回候选条文）
- policy.article_read   ：读取某条原文
- policy.quote_verify   ：核对一段引文是否真实存在于库中
- policy.brief_assemble ：唯一强制落地点，核验并补齐条文级引用后产出执行说明
"""

from __future__ import annotations

from typing import Any

from wit import capability

from .corpus.store import get_store, normalize_for_match
from .render import render_markdown
from .schema import ArticleCitation, BriefDraft, EvidenceClaim, ExecutionBrief


def _store():
    return get_store()


def _citation_from_hit(hit: dict[str, Any], quote: str | None) -> ArticleCitation:
    return ArticleCitation(
        citation_id=hit["citation_id"],
        doc_id=hit["doc_id"],
        doc_title=hit["doc_title"],
        issuer=hit.get("issuer"),
        doc_number=hit.get("doc_number"),
        publish_date=hit.get("publish_date"),
        effective_date=hit.get("effective_date"),
        chapter_path=hit.get("chapter_path"),
        article_no=hit.get("article_no"),
        article_text=hit.get("article_text") or "",
        source_url=hit.get("source_url"),
        source_hash=hit.get("source_hash"),
        quote=(quote.strip() if isinstance(quote, str) and quote.strip() else None),
    )


def _coerce_draft(draft: BriefDraft | dict[str, Any]) -> BriefDraft:
    return draft if isinstance(draft, BriefDraft) else BriefDraft.model_validate(draft)


def _coerce_evidence(evidence) -> list[EvidenceClaim]:
    out: list[EvidenceClaim] = []
    for item in evidence or []:
        out.append(item if isinstance(item, EvidenceClaim) else EvidenceClaim.model_validate(item))
    return out


def assemble_brief(
    query: str,
    draft: BriefDraft | dict[str, Any],
    evidence: list[EvidenceClaim] | list[dict[str, Any]],
    *,
    store=None,
) -> ExecutionBrief:
    """核验证据并生成 ExecutionBrief。

    规则（硬约束）：
    - 只接受能在本地语料库中定位到的 citation_id；
    - 引文必须能在该条文原文中找到（归一化后包含）；
    - 任何无法核验的引用都会被剔除并记入 warnings；
    - 若最终没有任何有效引用，grounded=False。
    """
    store = store if store is not None else _store()
    draft = _coerce_draft(draft)
    evidence = _coerce_evidence(evidence)
    citations: list[ArticleCitation] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for claim in evidence:
        hit = store.get_article(claim.citation_id)
        if hit is None:
            warnings.append(f"引用 {claim.citation_id} 不在本地语料库中，已剔除。")
            continue
        label = hit.get("article_no") or hit.get("citation_id")
        quote = (claim.quote or "").strip()
        if not quote:
            warnings.append(f"引用 {label} 未提供原文摘录，已剔除。")
            continue
        if normalize_for_match(quote) not in normalize_for_match(hit.get("article_text") or ""):
            warnings.append(f"引文与 {label} 原文不符，已剔除：{quote[:40]}…")
            continue
        if claim.citation_id in seen:
            continue
        seen.add(claim.citation_id)
        citations.append(_citation_from_hit(hit, quote))

    grounded = bool(citations)
    if not grounded:
        warnings.append("未在本地语料库中核验到任何有效条文依据，结论不可追溯。")

    return ExecutionBrief(
        query=query,
        corpus_scope=store.documents_scope([c.doc_id for c in citations]),
        applicable_subjects=draft.applicable_subjects,
        plain_explanation=draft.plain_explanation,
        action_items=draft.action_items,
        timeline=draft.timeline,
        required_materials=draft.required_materials,
        risk_notes=draft.risk_notes,
        citations=citations,
        warnings=warnings,
        grounded=grounded,
    )


@capability(
    id="policy.corpus_search",
    description=(
        "在本地权威语料库中做条文级检索，返回候选条文（含 citation_id、文件标题、发文字号、"
        "章节、条号、原文片段）。返回的结果是后续读取原文与引用的唯一入口。"
    ),
    public=True,
    acps_skill=True,
    tags=["政策", "法规", "检索", "条文"],
    examples=["查询小微企业申请创业补贴需要满足哪些条件"],
)
def corpus_search(query: str, limit: int = 5) -> dict[str, Any]:
    store = _store()
    hits = store.search(query, limit=limit)
    return {
        "query": query,
        "count": len(hits),
        "hits": hits,
        "note": "如 count=0，表示本地语料库中没有可支撑结论的权威原文，不得编造。",
    }


@capability(
    id="policy.article_read",
    description="按 citation_id 读取某条条文的完整原文与文件元数据（标题、发文字号、日期、来源）。",
    public=True,
    acps_skill=True,
    tags=["政策", "法规", "原文", "条文"],
)
def article_read(citation_id: str) -> dict[str, Any]:
    hit = _store().get_article(citation_id)
    if hit is None:
        return {
            "found": False,
            "citation_id": citation_id,
            "message": "本地语料库中不存在该条文，请先用 policy.corpus_search 检索。",
        }
    return {"found": True, **hit}


@capability(
    id="policy.quote_verify",
    description="核对一段引文是否真实存在于本地语料库的某条原文中，用于避免引用编造或断章取义。",
    public=True,
    acps_skill=True,
    tags=["政策", "核对", "引用", "溯源"],
)
def quote_verify(text: str) -> dict[str, Any]:
    matches = _store().find_quote(text)
    return {
        "verified": bool(matches),
        "count": len(matches),
        "matches": matches[:5],
        "message": "verified=true 表示该引文在语料库中存在；false 表示查无此文。",
    }


@capability(
    id="policy.brief_assemble",
    description=(
        "生成最终执行说明：提交起草好的七字段内容与证据列表（citation_id + 原文摘录），"
        "系统会逐条核验引用、剔除无法核验的引用，并补齐权威元数据，返回结构化 JSON 与 Markdown 报告。"
        "这是唯一允许产出引用依据的出口。"
    ),
    public=True,
    acps_skill=True,
    tags=["政策", "执行说明", "清单", "条文依据"],
    examples=["生成某政策的适用对象、办事清单、时间节点、材料要求与风险提示"],
)
def brief_assemble(
    query: str,
    draft: BriefDraft,
    evidence: list[EvidenceClaim],
) -> dict[str, Any]:
    brief = assemble_brief(query, draft, evidence)
    return {
        "grounded": brief.grounded,
        "brief": brief.model_dump(),
        "markdown": render_markdown(brief),
    }


PUBLIC_CAPABILITIES = [
    corpus_search,
    article_read,
    quote_verify,
    brief_assemble,
]
