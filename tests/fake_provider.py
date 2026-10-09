"""离线确定性假 Provider：按脚本驱动 能力调用链，不联网。

用途：在 CI 中验证 Agent 会按流程调用 policy.corpus_search →
policy.article_read → policy.brief_assemble，并产出合法、可核验的执行说明。
"""

from __future__ import annotations

import json
from typing import Any

from wit import ModelResponse, ProviderCapabilities, ToolCall


def _tool_payloads(request) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for message in request.messages:
        if getattr(message, "role", None) != "tool":
            continue
        text = message.text() if hasattr(message, "text") else ""
        try:
            data = json.loads(text)
        except Exception:
            payloads.append({"raw": text})
            continue
        # wit 把工具结果包在 {toolCallId, tool, status, result} 信封里，这里取出 result。
        if isinstance(data, dict) and isinstance(data.get("result"), dict):
            data = data["result"]
        payloads.append(data)
    return payloads


class FakePolicyProvider:
    """一个确定性的“模型”，用于离线验证能力链路。"""

    capabilities = ProviderCapabilities(
        provider="fake",
        api="chat",
        input_modalities=frozenset(),
        output_modalities=frozenset(),
        streaming=False,
        tools=True,
    )

    def __init__(self, query: str) -> None:
        self.query = query

    def supports_content(self, part, *, role: str) -> tuple[bool, str | None]:
        return True, None

    async def complete(self, request) -> ModelResponse:
        results = _tool_payloads(request)
        step = len(results)

        if step == 0:
            return ModelResponse.tools(
                [ToolCall(id="c1", name="policy_corpus_search", arguments={"query": self.query, "limit": 3})]
            )

        search = results[0]
        if not search.get("hits"):
            # 没有命中：如实返回，不编造，也不进入 brief_assemble。
            return ModelResponse.final("未在本地语料库中找到可作为依据的官方原文。请在库中补录相关原文后重试。")

        if step == 1:
            citation_id = search["hits"][0]["citation_id"]
            return ModelResponse.tools(
                [ToolCall(id="c2", name="policy_article_read", arguments={"citation_id": citation_id})]
            )

        article = results[1]
        if step == 2:
            quote = (article.get("article_text") or "").strip().split("\n")
            quote = next((line for line in quote if line.strip()), "")
            draft = {
                "applicable_subjects": ["在本市依法登记注册、正常经营满6个月的小微企业"],
                "plain_explanation": "符合条件的小微企业可以申请创业补贴。",
                "action_items": ["准备营业执照复印件", "开具社保缴纳证明"],
                "timeline": [{"label": "申报期", "date": "每年4月1日-4月30日", "description": ""}],
                "required_materials": ["营业执照复印件", "近6个月社保缴纳证明"],
                "risk_notes": ["逾期不再受理"],
            }
            return ModelResponse.tools(
                [
                    ToolCall(
                        id="c3",
                        name="policy_brief_assemble",
                        arguments={
                            "query": self.query,
                            "draft": draft,
                            "evidence": [{"citation_id": article["citation_id"], "quote": quote}],
                        },
                    )
                ]
            )

        assembled = results[-1]
        markdown = assembled.get("markdown") or ""
        return ModelResponse.final(markdown or "生成失败。")
