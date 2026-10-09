"""ACPs 接入：构造 AcpsConfig、推进注册、启动 Direct Partner listener。

接入几乎全部由 wit 托管：`up_until_ready()` 走完
登录 → 提交 ACS → 等待审核 → 取得 AIC → 签发 mTLS 证书 → 落地身份；
`serve_direct_partner()` 用已验证的身份启动 mTLS listener。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from wit import (
    AcpsConfig,
    AcpsRegistration,
    AgentCertificateRequest,
    AgentProviderProfile,
    RegistryPasswordCredentials,
    WitRuntime,
)

from .agent import build_agent
from .config import Settings
from .provider import build_provider


@dataclass
class AgentRuntimeHandle:
    """把运行时与其依赖打包，便于统一关闭。"""

    runtime: WitRuntime
    provider: Any
    settings: Settings

    async def aclose(self) -> None:
        try:
            await self.runtime.stop_serving()
        except Exception:
            pass
        try:
            await self.provider.aclose()
        except Exception:
            pass


def _derive_dns(settings: Settings) -> tuple[str, ...]:
    if settings.cert_dns:
        return tuple(settings.cert_dns)
    if settings.public_endpoint:
        host = urlparse(settings.public_endpoint).hostname
        if host:
            return (host,)
    return ()


def build_acps_config(settings: Settings) -> AcpsConfig:
    """按 profile 构造 ACPs 配置；默认走 ioa.pub 固定基础设施。"""
    provider = AgentProviderProfile(
        organization=settings.organization,
        country_code=settings.country_code,
    )
    certificate = AgentCertificateRequest(
        dns=_derive_dns(settings),
        requested_validity=settings.cert_validity_days,
    )
    if settings.acps_profile.lower() in ("ioa", "ioa_pub", "ioapub"):
        return AcpsConfig.ioa_pub(
            provider=provider,
            certificate=certificate,
            public_endpoint=settings.public_endpoint,
            registration=AcpsRegistration.integrated(),
        )
    # 非 ioa 环境：由 ACPS_* 环境变量提供基础设施地址。
    return AcpsConfig.from_env(
        provider=provider,
        certificate=certificate,
        registration=AcpsRegistration.integrated(),
    )


def build_runtime(settings: Settings | None = None, *, required_provider: bool = True) -> AgentRuntimeHandle:
    """构造运行时句柄（不联网）。"""
    settings = settings or Settings.from_env()
    settings.agent_workspace().mkdir(parents=True, exist_ok=True)
    provider = build_provider(settings, required=required_provider)
    agent = build_agent(settings, provider)
    acps = build_acps_config(settings)
    runtime = WitRuntime(agent, workspace=settings.agent_workspace(), acps=acps)
    return AgentRuntimeHandle(runtime=runtime, provider=provider, settings=settings)


def save_acs_draft(settings: Settings | None = None, path: str | Path | None = None) -> Path:
    """生成并保存 ACS 草稿（本地，无需联网、无需 API Key）。"""
    settings = settings or Settings.from_env()
    settings.agent_workspace().mkdir(parents=True, exist_ok=True)
    provider = build_provider(settings, required=False)
    agent = build_agent(settings, provider)
    runtime = WitRuntime(agent, workspace=settings.agent_workspace(), acps=build_acps_config(settings))
    return runtime.save_acs(path)


def validate_agent(settings: Settings | None = None) -> dict[str, Any]:
    """本地校验：编译诊断、能力投影与协议绑定（无需联网、无需 API Key）。"""
    settings = settings or Settings.from_env()
    settings.agent_workspace().mkdir(parents=True, exist_ok=True)
    provider = build_provider(settings, required=False)
    agent = build_agent(settings, provider)
    acps = build_acps_config(settings)
    compiled = agent.compile(workspace=settings.agent_workspace(), acps=acps)
    return {
        "agent_id": compiled.agent_id,
        "valid": not compiled.diagnostics,
        "diagnostics": [d.to_dict() for d in compiled.diagnostics],
        "skills": [p.capability_id for p in compiled.capability_matrix.projections],
        "tools": [t.name for t in compiled.tools],
        "protocols": [p.id for p in compiled.protocols],
    }


async def register(settings: Settings | None = None) -> dict[str, Any]:
    """推进注册状态机（停在 waiting_for_review 属正常）。"""
    handle = build_runtime(settings, required_provider=False)
    try:
        draft_path = handle.runtime.save_acs()
        credentials = RegistryPasswordCredentials.from_env()
        result = await handle.runtime.up_until_ready(credentials=credentials)
        payload = result.to_dict()
        payload["acs_draft_path"] = str(draft_path)
        payload["summary"] = result.summary()
        return payload
    finally:
        await handle.aclose()


async def serve(settings: Settings | None = None, *, block: bool = True) -> dict[str, Any]:
    """注册到位后启动 Direct Partner listener（mTLS + AMP）。"""
    handle = build_runtime(settings, required_provider=True)
    settings = handle.settings
    try:
        draft_path = handle.runtime.save_acs()
        credentials = RegistryPasswordCredentials.from_env()
        result = await handle.runtime.up_until_ready(credentials=credentials)

        base: dict[str, Any] = {
            "summary": result.summary(),
            "status": result.status,
            "ready": result.ready,
            "waiting_for_review": result.waiting_for_review,
            "blocked": result.blocked,
            "next_action": result.next_action,
            "acs_draft_path": str(draft_path),
        }
        if not result.ready:
            base["message"] = (
                "尚未就绪；若为 waiting_for_review，请等平台管理员审核通过后重跑本命令。"
            )
            return base

        status = await handle.runtime.serve_direct_partner(
            host=settings.bind_host,
            port=settings.bind_port,
            amp=True,
            amp_periodic_logs=("heartbeat", "system", "metrics"),
        )
        base["serving"] = status.to_dict()
        if not block:
            return base

        await asyncio.Event().wait()
        return base
    finally:
        await handle.aclose()
