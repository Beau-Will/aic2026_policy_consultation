"""ACPs 接入：构造 AcpsConfig、推进注册、启动 Direct Partner listener。

接入几乎全部由 wit 托管：`up_until_ready()` 走完
登录 → 提交 ACS → 等待审核 → 取得 AIC → 签发 mTLS 证书 → 落地身份；
`serve_direct_partner()` 用已验证的身份启动 mTLS listener。
"""

from __future__ import annotations

import asyncio
import ipaddress
import sys
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

PUBLIC_ENDPOINT_HELP = """\
POLICY_PUBLIC_ENDPOINT 是“平台（梧桐）用来访问你这个智能体”的对外地址，必须：
  1) 以 https:// 开头（严格互操作模式强制）；
  2) 以 /acps/aip/v1 结尾；
  3) 主机名/IP 能被平台侧访问到（公网可达，或平台内网可达）。

示例：
  公网域名      : https://agent.example.com/acps/aip/v1
  云服务器公网IP : https://203.0.113.10/acps/aip/v1
  内网穿透(隧道) : https://<隧道分配的主机名>/acps/aip/v1

POLICY_CERT_DNS 可以留空：会自动取上面地址的主机名写入证书 SAN。
（若地址用的是 IP，会自动写入证书的 IP SAN。）"""


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


def _split_cert_hosts(hosts: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """把主机名与 IP 分开，分别写入证书的 DNS SAN 与 IP SAN。"""
    dns: list[str] = []
    ips: list[str] = []
    for host in hosts:
        host = (host or "").strip()
        if not host:
            continue
        try:
            ipaddress.ip_address(host)
        except ValueError:
            dns.append(host)
        else:
            ips.append(host)
    return tuple(dns), tuple(ips)


def _cert_hosts(settings: Settings) -> tuple[tuple[str, ...], tuple[str, ...]]:
    hosts: list[str] = list(settings.cert_dns)
    if not hosts and settings.public_endpoint:
        host = urlparse(settings.public_endpoint).hostname
        if host:
            hosts.append(host)
    return _split_cert_hosts(hosts)


def require_public_endpoint(settings: Settings) -> None:
    """注册/上线前校验对外地址，给出人类可读的说明而不是晦涩报错。"""
    endpoint = (settings.public_endpoint or "").strip()
    if not endpoint:
        raise RuntimeError("缺少 POLICY_PUBLIC_ENDPOINT。\n" + PUBLIC_ENDPOINT_HELP)
    if not endpoint.startswith("https://"):
        raise RuntimeError("POLICY_PUBLIC_ENDPOINT 必须以 https:// 开头。\n" + PUBLIC_ENDPOINT_HELP)
    if not urlparse(endpoint).hostname:
        raise RuntimeError("POLICY_PUBLIC_ENDPOINT 解析不出主机名。\n" + PUBLIC_ENDPOINT_HELP)


def build_acps_config(settings: Settings) -> AcpsConfig:
    """按 profile 构造 ACPs 配置；默认走 ioa.pub 固定基础设施。"""
    provider = AgentProviderProfile(
        organization=settings.organization,
        country_code=settings.country_code,
    )
    dns, ips = _cert_hosts(settings)
    certificate = AgentCertificateRequest(
        dns=dns,
        ip=ips,
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
    if not (settings.public_endpoint or "").strip():
        print(
            "[提示] 尚未设置 POLICY_PUBLIC_ENDPOINT，ACS 草稿里不会包含对外端点。\n"
            + PUBLIC_ENDPOINT_HELP,
            file=sys.stderr,
        )
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
    dns, ips = _cert_hosts(settings)
    return {
        "agent_id": compiled.agent_id,
        "valid": not compiled.diagnostics,
        "diagnostics": [d.to_dict() for d in compiled.diagnostics],
        "skills": [p.capability_id for p in compiled.capability_matrix.projections],
        "tools": [t.name for t in compiled.tools],
        "protocols": [p.id for p in compiled.protocols],
        "public_endpoint": settings.public_endpoint,
        "certificate_san": {"dns": list(dns), "ip": list(ips)},
    }


async def register(settings: Settings | None = None) -> dict[str, Any]:
    """推进注册状态机（停在 waiting_for_review 属正常）。"""
    settings = settings or Settings.from_env()
    require_public_endpoint(settings)
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
    settings = settings or Settings.from_env()
    require_public_endpoint(settings)
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
