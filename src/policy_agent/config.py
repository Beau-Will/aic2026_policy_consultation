"""运行时配置：统一从环境变量读取（`.env` 由使用方自行注入）。

约定：
- 模型相关复用 `OPENAI_*`（DeepSeek 走 OpenAI 兼容协议）。
- ACPs 账号由框架读取 `ACPS_USERNAME` / `ACPS_PASSWORD`。
- `POLICY_*` 为本项目自有配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_AGENT_ID = "official-policy-execution-partner"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    raw = _env(name)
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    """一次进程运行所使用的全部配置。"""

    agent_id: str = DEFAULT_AGENT_ID
    agent_display_name: str = "官方政策执行解读智能体"
    agent_version: str = "0.1.0"
    organization: str | None = None
    country_code: str = "CN"

    corpus_db_path: Path = field(default_factory=lambda: Path("data/corpus.db"))
    docs_dir: Path = field(default_factory=lambda: Path("data/docs"))
    workspace_dir: Path = field(default_factory=lambda: Path(".wit"))

    public_endpoint: str | None = None
    bind_host: str = "0.0.0.0"
    bind_port: int = 8443
    cert_dns: list[str] = field(default_factory=list)
    cert_validity_days: int = 365

    model_name: str = DEFAULT_MODEL
    openai_api_key: str | None = None
    openai_base_url: str = DEFAULT_BASE_URL

    acps_profile: str = "ioa"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            agent_id=_env("POLICY_AGENT_ID", DEFAULT_AGENT_ID) or DEFAULT_AGENT_ID,
            agent_display_name=_env("POLICY_AGENT_DISPLAY_NAME", "官方政策执行解读智能体")
            or "官方政策执行解读智能体",
            agent_version=_env("POLICY_AGENT_VERSION", "0.1.0") or "0.1.0",
            organization=_env("POLICY_ORGANIZATION"),
            country_code=_env("POLICY_COUNTRY_CODE", "CN") or "CN",
            corpus_db_path=Path(_env("POLICY_CORPUS_DB", "data/corpus.db") or "data/corpus.db"),
            docs_dir=Path(_env("POLICY_DOCS_DIR", "data/docs") or "data/docs"),
            workspace_dir=Path(_env("POLICY_WORKSPACE", ".wit") or ".wit"),
            public_endpoint=_env("POLICY_PUBLIC_ENDPOINT"),
            bind_host=_env("POLICY_BIND_HOST", "0.0.0.0") or "0.0.0.0",
            bind_port=_env_int("POLICY_BIND_PORT", 8443),
            cert_dns=_env_list("POLICY_CERT_DNS"),
            cert_validity_days=_env_int("POLICY_CERT_VALIDITY_DAYS", 365),
            model_name=_env("OPENAI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
            openai_api_key=_env("OPENAI_API_KEY"),
            openai_base_url=_env("OPENAI_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL,
            acps_profile=_env("ACPS_PROFILE", "ioa") or "ioa",
        )

    def agent_workspace(self) -> Path:
        """该 Agent 在 workspace 下的独立工作区目录。"""
        return self.workspace_dir / self.agent_id
