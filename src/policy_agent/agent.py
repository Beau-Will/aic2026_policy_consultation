"""装配 WitAgent：声明模型、指令、能力与 ACPs Direct 协议绑定。"""

from __future__ import annotations

from typing import Any

from wit import AcpsDirect, AmpAccessLoggingHooks, WitAgent

from .capabilities import PUBLIC_CAPABILITIES
from .config import Settings
from .provider import build_provider

INSTRUCTIONS = """你是“官方政策执行解读智能体”，面向政府网站、法规数据库与官方公告中的政策、制度、通知与申报指南。

你的唯一事实来源是本地权威语料库，绝不编造。工作流程必须严格遵守：

1) 先用 policy_corpus_search 检索与用户问题相关的条文。
   - 若返回 count = 0：说明本地语料库中没有可支撑结论的权威原文。此时如实回复
     “未在本地语料库中找到可作为依据的官方原文”，并说明建议补录哪类原文；
     不要编造，也不要调用 policy_brief_assemble。
2) 对候选条文调用 policy_article_read 读取完整原文，只依据读到的原文下结论。
3) 需要核对某句引文时调用 policy_quote_verify。
4) 起草六项内容：政策适用对象、通俗解释、需完成的事项、时间节点、材料要求、风险提示。
5) 调用 policy_brief_assemble，参数为：
   - query：用户原始问题；
   - draft：上面起草的六项内容（其中 timeline 每条写成 `节点 | 时间 | 说明` 的字符串）；
   - evidence：列表，每项包含 citation_id 与 quote（quote 必须逐字来自 policy_article_read 读到的原文）。
6) 把 policy_brief_assemble 返回的 markdown 原样作为最终回答输出。

硬性要求：
- 只允许引用 policy_article_read 读到的条文；引用必须逐字来自原文，不得改写、拼接或想象。
- 时间节点、材料清单、金额、比例等具体信息，原文没有就不要写，或明确标注“原文未规定”。
- 不要自行改写最终报告中的“条文依据”部分，一切以 policy_brief_assemble 的核验结果为准。
- 回答使用简体中文，先给结论再给依据。"""


def build_agent(
    settings: Settings | None = None,
    provider: Any | None = None,
    *,
    include_acps: bool = True,
) -> WitAgent:
    """构造智能体声明（不触发联网/注册）。

    include_acps=False 时只声明本地能力，不绑定 ACPs 协议，供离线测试使用。
    """
    settings = settings or Settings.from_env()
    model = provider if provider is not None else build_provider(settings)
    return WitAgent(
        id=settings.agent_id,
        display_name=settings.agent_display_name,
        version=settings.agent_version,
        description=(
            "以本地权威原文为核心，把政策/法规/通知转化为可直接使用的执行说明，"
            "并提供条文级、可回溯的引用依据。"
        ),
        instructions=INSTRUCTIONS,
        model=model,
        capabilities=list(PUBLIC_CAPABILITIES),
        # AMP Access 日志：ACPs Direct 传输边界的调用/被调用记录，
        # 平台按 access 日志（correlationId = taskId）统计调用次数与排名。
        amp_hooks=[AmpAccessLoggingHooks()],
        protocols=[AcpsDirect(modes=("rpc", "stream"))] if include_acps else [],
        metadata={
            "domain": "政策法规执行解读",
            "language": "zh-CN",
            "source": "local-authoritative-corpus",
        },
    )
