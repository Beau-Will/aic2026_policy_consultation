"""离线端到端：用假 Provider 驱动真实的能力调用链。"""

from __future__ import annotations

from wit import RunConfig, WitRuntime

from policy_agent.agent import build_agent
from fake_provider import FakePolicyProvider


def _brief_from(observations) -> dict | None:
    for item in reversed(observations):
        payload = item.get("result", item) if isinstance(item, dict) else None
        if isinstance(payload, dict) and "brief" in payload:
            return payload
    return None


async def test_agent_flow_produces_grounded_brief(populated_store):
    query = "小微企业如何申报创业补贴，需要什么材料？"
    provider = FakePolicyProvider(query)
    agent = build_agent(provider=provider, include_acps=False)
    runtime = WitRuntime(agent)

    result = await runtime.run(query, RunConfig(max_steps=8))

    assert "政策适用对象" in result.final_text
    assert "条文依据" in result.final_text

    payload = _brief_from(result.observations)
    assert payload is not None
    assert payload["grounded"] is True
    citations = payload["brief"]["citations"]
    assert len(citations) == 1
    assert citations[0]["article_no"]
    assert citations[0]["doc_number"] == "示政办发〔2024〕12号"


async def test_agent_flow_reports_when_no_source(populated_store):
    query = "关于深海矿产开发的税收优惠有哪些？"
    provider = FakePolicyProvider(query)
    agent = build_agent(provider=provider, include_acps=False)
    runtime = WitRuntime(agent)

    result = await runtime.run(query, RunConfig(max_steps=8))
    assert "未在本地语料库中找到" in result.final_text
    assert _brief_from(result.observations) is None
