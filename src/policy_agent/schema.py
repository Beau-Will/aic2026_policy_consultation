"""领域模型：执行说明（ExecutionBrief）与条文级引用。

设计要点：所有引用都必须落到本地语料库中真实存在的条文，
`citations` 只能由 `policy.brief_assemble` 依据语料库补齐，模型不能自造。
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def now_iso() -> str:
    """当前时间的 ISO8601（UTC）字符串。"""
    return datetime.now(timezone.utc).isoformat()


class TimelineNode(BaseModel):
    """时间节点。"""

    label: str = Field(description="节点名称，例如：申报开始、材料补正截止、公示期")
    date: str = Field(
        default="",
        description="日期或期限，尽量写 YYYY-MM-DD；原文只有相对表述时写原文措辞，如“受理后20个工作日内”",
    )
    description: str = Field(default="", description="该节点的补充说明")


class EvidenceClaim(BaseModel):
    """模型给出的一条证据主张：指向某条文，并附上原文摘录。"""

    citation_id: str = Field(
        description="来自 policy.corpus_search / policy.article_read 的条文引用 ID（citation_id）"
    )
    quote: str = Field(
        description="必须与所选条文原文一致（允许空白/标点差异）；用于核验引用是否成立"
    )
    note: str | None = Field(
        default=None, description="该条文支撑结论中的哪一项（可选）"
    )


class BriefDraft(BaseModel):
    """模型起草的执行说明正文（不含引用元数据，引用由落地点补齐）。"""

    applicable_subjects: list[str] = Field(
        description="政策适用对象：哪些主体/情形适用，尽量具体"
    )
    plain_explanation: str = Field(description="通俗解释：把政策/制度讲清楚，避免法言法语")
    action_items: list[str] = Field(description="需完成的事项：可执行的动作清单")
    timeline: list[TimelineNode] = Field(
        default_factory=list, description="时间节点：申报、补正、公示、生效等关键时点"
    )
    required_materials: list[str] = Field(
        default_factory=list, description="材料要求：需要准备/提交的材料清单"
    )
    risk_notes: list[str] = Field(
        default_factory=list, description="风险提示：逾期、材料不全、口径差异等"
    )


class ArticleCitation(BaseModel):
    """可回溯的条文级引用；字段全部来自本地语料库的权威元数据。"""

    citation_id: str
    doc_id: str
    doc_title: str
    issuer: str | None = None
    doc_number: str | None = None
    publish_date: str | None = None
    effective_date: str | None = None
    chapter_path: str | None = None
    article_no: str | None = None
    article_text: str
    source_url: str | None = None
    source_hash: str | None = None
    quote: str | None = Field(default=None, description="经核验通过的引文摘录")


class ExecutionBrief(BaseModel):
    """最终交付物：结构化执行说明。"""

    query: str
    generated_at: str = Field(default_factory=now_iso)
    corpus_scope: list[str] = Field(
        default_factory=list, description="本次结论所依据的语料文件（doc_id/标题）"
    )
    applicable_subjects: list[str] = Field(default_factory=list)
    plain_explanation: str = ""
    action_items: list[str] = Field(default_factory=list)
    timeline: list[TimelineNode] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    citations: list[ArticleCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    grounded: bool = Field(
        default=True,
        description="是否存在至少一条通过核验的条文依据；False 表示未找到可支撑结论的权威原文",
    )
