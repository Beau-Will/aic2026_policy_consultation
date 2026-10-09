"""执行说明落地点（brief_assemble）与渲染测试。"""

from __future__ import annotations

from policy_agent.capabilities import assemble_brief
from policy_agent.render import render_markdown
from policy_agent.schema import BriefDraft, EvidenceClaim, TimelineNode

SEVEN_SECTIONS = ["政策适用对象", "通俗解释", "需完成的事项", "时间节点", "材料要求", "风险提示", "条文依据"]


def _draft() -> BriefDraft:
    return BriefDraft(
        applicable_subjects=["在本市依法登记注册、正常经营满6个月的小微企业"],
        plain_explanation="符合条件的小微企业可申请创业补贴。",
        action_items=["准备营业执照复印件", "开具社保缴纳证明"],
        timeline=[TimelineNode(label="申报期", date="每年4月1日-4月30日")],
        required_materials=["营业执照复印件", "近6个月社保缴纳证明"],
        risk_notes=["逾期不再受理"],
    )


def test_assemble_accepts_valid_rejects_invalid(populated_store):
    hits = populated_store.search("申报时间", limit=1)
    good_id = hits[0]["citation_id"]
    good_quote = "申报时间为每年4月1日至4月30日，逾期不再受理。"

    evidence = [
        EvidenceClaim(citation_id=good_id, quote=good_quote),
        EvidenceClaim(citation_id="does-not-exist#0000", quote="不存在的条文"),
        EvidenceClaim(citation_id=good_id, quote="与原文完全不符的一段引文"),
    ]
    brief = assemble_brief("小微企业如何申报创业补贴？", _draft(), evidence, store=populated_store)

    assert brief.grounded is True
    assert len(brief.citations) == 1
    assert brief.citations[0].citation_id == good_id
    assert brief.citations[0].article_no == "第四条"
    assert brief.citations[0].quote == good_quote
    assert brief.citations[0].doc_number == "示政办发〔2024〕12号"
    assert any("不在本地语料库" in w for w in brief.warnings)
    assert any("原文不符" in w for w in brief.warnings)
    assert brief.corpus_scope and "示例市" in brief.corpus_scope[0]


def test_assemble_marks_ungrounded_when_no_valid_evidence(populated_store):
    evidence = [EvidenceClaim(citation_id="missing#0000", quote="x")]
    brief = assemble_brief("查询", _draft(), evidence, store=populated_store)
    assert brief.grounded is False
    assert brief.citations == []
    assert any("不可追溯" in w for w in brief.warnings)


def test_assemble_tolerates_whitespace_differences(populated_store):
    hits = populated_store.search("申报时间", limit=1)
    cid = hits[0]["citation_id"]
    quote = "申报时间为每年 4月1日 至 4月30日"
    brief = assemble_brief("q", _draft(), [EvidenceClaim(citation_id=cid, quote=quote)], store=populated_store)
    assert brief.grounded is True


def test_render_contains_all_seven_sections(populated_store):
    hits = populated_store.search("申报时间", limit=1)
    brief = assemble_brief(
        "小微企业如何申报？",
        _draft(),
        [EvidenceClaim(citation_id=hits[0]["citation_id"], quote=hits[0]["article_text"][:20])],
        store=populated_store,
    )
    md = render_markdown(brief)
    for section in SEVEN_SECTIONS:
        assert section in md
    assert "第四条" in md


def test_render_marks_ungrounded(populated_store):
    brief = assemble_brief("查询", _draft(), [], store=populated_store)
    md = render_markdown(brief)
    assert "未找到可作为依据的权威原文" in md
    assert "无可回溯条文依据" in md
