"""对外端点与证书 SAN 的解析测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from policy_agent.config import Settings
from policy_agent.serving import _cert_hosts, build_acps_config, require_public_endpoint


def _settings(**kw) -> Settings:
    return replace(Settings.from_env(), **kw)


def test_domain_endpoint_goes_to_dns_san():
    settings = _settings(public_endpoint="https://agent.example.com/acps/aip/v1", cert_dns=[])
    dns, ips = _cert_hosts(settings)
    assert dns == ("agent.example.com",)
    assert ips == ()


def test_ip_endpoint_goes_to_ip_san():
    settings = _settings(public_endpoint="https://203.0.113.10/acps/aip/v1", cert_dns=[])
    dns, ips = _cert_hosts(settings)
    assert dns == ()
    assert ips == ("203.0.113.10",)


def test_explicit_cert_dns_overrides_endpoint_host():
    settings = _settings(
        public_endpoint="https://agent.example.com/acps/aip/v1",
        cert_dns=["alt.example.com"],
    )
    dns, ips = _cert_hosts(settings)
    assert dns == ("alt.example.com",)
    assert ips == ()


def test_mixed_hosts_split_correctly():
    settings = _settings(
        public_endpoint="https://agent.example.com/acps/aip/v1",
        cert_dns=["agent.example.com", "203.0.113.10"],
    )
    dns, ips = _cert_hosts(settings)
    assert set(dns) == {"agent.example.com"}
    assert set(ips) == {"203.0.113.10"}


def test_build_acps_config_embeds_ip_san():
    settings = _settings(public_endpoint="https://203.0.113.10/acps/aip/v1", cert_dns=[])
    acps = build_acps_config(settings)
    assert acps.public_endpoint == "https://203.0.113.10/acps/aip/v1"
    assert acps.certificate is not None
    assert acps.certificate.ip == ("203.0.113.10",)
    assert acps.certificate.dns == ()


@pytest.mark.parametrize(
    "bad",
    [None, "", "http://agent.example.com/acps/aip/v1", "https:///acps/aip/v1"],
)
def test_require_public_endpoint_rejects_bad_values(bad):
    with pytest.raises(RuntimeError) as exc:
        require_public_endpoint(_settings(public_endpoint=bad))
    assert "POLICY_PUBLIC_ENDPOINT" in str(exc.value)


def test_require_public_endpoint_accepts_valid():
    require_public_endpoint(_settings(public_endpoint="https://agent.example.com/acps/aip/v1"))
