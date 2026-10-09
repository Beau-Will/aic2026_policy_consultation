"""把结构化执行说明渲染为人工可读的 Markdown 报告。"""

from __future__ import annotations

from .schema import ExecutionBrief


def _cite_ref(citation, index: int) -> str:
    parts: list[str] = []
    if citation.article_no:
        parts.append(citation.article_no)
    elif citation.heading:
        parts.append(citation.heading)
    if citation.chapter_path:
        parts.append(citation.chapter_path)
    label = " ".join(parts) if parts else citation.citation_id
    return f"[{index}] {citation.doc_title}（{label}）"


def render_markdown(brief: ExecutionBrief) -> str:
    lines: list[str] = []
    lines.append(f"# 政策执行说明")
    lines.append("")
    lines.append(f"**查询：** {brief.query}")
    lines.append("")

    if not brief.grounded or not brief.citations:
        lines.append(
            "> ⚠️ **未找到可作为依据的权威原文。** 以下内容仅供参考，"
            "请勿据此直接办事；请补录相关原文后重新生成。"
        )
        lines.append("")

    lines.append("## 一、政策适用对象")
    if brief.applicable_subjects:
        lines.extend(f"- {item}" for item in brief.applicable_subjects)
    else:
        lines.append("- （未明确）")
    lines.append("")

    lines.append("## 二、通俗解释")
    lines.append(brief.plain_explanation or "（未提供）")
    lines.append("")

    lines.append("## 三、需完成的事项")
    if brief.action_items:
        for i, item in enumerate(brief.action_items, start=1):
            lines.append(f"{i}. {item}")
    else:
        lines.append("1. （未明确）")
    lines.append("")

    lines.append("## 四、时间节点")
    if brief.timeline:
        lines.append("| 节点 | 时间 | 说明 |")
        lines.append("| --- | --- | --- |")
        for node in brief.timeline:
            date = node.date or "—"
            desc = (node.description or "").replace("|", "\\|")
            lines.append(f"| {node.label} | {date} | {desc} |")
    else:
        lines.append("（未明确）")
    lines.append("")

    lines.append("## 五、材料要求")
    if brief.required_materials:
        lines.extend(f"- {item}" for item in brief.required_materials)
    else:
        lines.append("- （未明确）")
    lines.append("")

    lines.append("## 六、风险提示")
    if brief.risk_notes:
        lines.extend(f"- {item}" for item in brief.risk_notes)
    else:
        lines.append("- （未明确）")
    lines.append("")

    lines.append("## 七、条文依据")
    if brief.citations:
        for i, citation in enumerate(brief.citations, start=1):
            lines.append(f"**{_cite_ref(citation, i)}**")
            if citation.doc_number:
                lines.append(f"- 发文字号：{citation.doc_number}")
            if citation.publish_date:
                lines.append(f"- 发布日期：{citation.publish_date}")
            if citation.effective_date:
                lines.append(f"- 施行/生效日期：{citation.effective_date}")
            if citation.source_url:
                lines.append(f"- 来源：{citation.source_url}")
            if citation.quote:
                lines.append(f"- 引文：{citation.quote}")
            lines.append(f"- 原文：{citation.article_text}")
            lines.append("")
    else:
        lines.append("（无可回溯条文依据）")
        lines.append("")

    if brief.warnings:
        lines.append("## 附：核验提示")
        lines.extend(f"- {w}" for w in brief.warnings)
        lines.append("")

    if brief.corpus_scope:
        lines.append("---")
        lines.append("**语料范围：** " + "；".join(brief.corpus_scope))
    lines.append("")
    lines.append(f"_生成时间：{brief.generated_at}_")
    return "\n".join(lines).strip() + "\n"
