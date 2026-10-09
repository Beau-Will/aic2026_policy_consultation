"""Agent 装配与 ACS 草稿测试（离线，不调用模型）。"""

from __future__ import annotations

from wit import AcpsConfig, AgentCertificateRequest, AgentProviderProfile

from policy_agent.agent import build_agent
from policy_agent.provider import OfflineProvider


def _acps() -> AcpsConfig:
    return AcpsConfig.ioa_pub(
        provider=AgentProviderProfile(organization="示例机构", country_code="CN"),
        certificate=AgentCertificateRequest(dns=("policy.example.com",), requested_validity=365),
        public_endpoint="https://policy.example.com/acps/aip/v1",
    )


def test_compile_has_no_diagnostics(tmp_path):
    agent = build_agent(provider=OfflineProvider("offline"))
    compiled = agent.compile(workspace=tmp_path / "ws", acps=_acps())
    assert compiled.diagnostics == []
    assert compiled.agent_id == "official-policy-execution-partner"


def test_all_capabilities_are_public_skills_and_tools(tmp_path):
    agent = build_agent(provider=OfflineProvider("offline"))
    compiled = agent.compile(workspace=tmp_path / "ws", acps=_acps())

    tool_names = {t.name for t in compiled.tools}
    assert tool_names == {
        "policy_corpus_search",
        "policy_article_read",
        "policy_quote_verify",
        "policy_brief_assemble",
    }

    skill_ids = {p.capability_id for p in compiled.capability_matrix.projections}
    assert skill_ids == {
        "policy.corpus_search",
        "policy.article_read",
        "policy.quote_verify",
        "policy.brief_assemble",
    }
    for projection in compiled.capability_matrix.projections:
        assert projection.acps_skill is not None


def test_acs_draft_has_skills_and_mtls_endpoint(tmp_path):
    agent = build_agent(provider=OfflineProvider("offline"))
    compiled = agent.compile(workspace=tmp_path / "ws", acps=_acps())
    acs = compiled.acs_draft
    assert acs is not None
    assert {s["id"] for s in acs["skills"]} == {
        "policy.corpus_search",
        "policy.article_read",
        "policy.quote_verify",
        "policy.brief_assemble",
    }
    endpoints = acs["endPoints"]
    assert endpoints and endpoints[0]["transport"] == "JSONRPC"
    assert endpoints[0]["url"].startswith("https://policy.example.com/acps/aip/v1")
    assert {d for d in acs["certificate"]["altNames"]["dns"]} == {"policy.example.com"}


def test_brief_assemble_schema_exposes_draft_and_evidence(tmp_path):
    agent = build_agent(provider=OfflineProvider("offline"))
    compiled = agent.compile(workspace=tmp_path / "ws", acps=_acps())
    tool = next(t for t in compiled.tools if t.name == "policy_brief_assemble")
    schema = tool.model_schema()
    props = schema["parameters"]["properties"]
    assert set(props) >= {"query", "draft", "evidence"}
    assert "applicable_subjects" in props["draft"]["properties"]
