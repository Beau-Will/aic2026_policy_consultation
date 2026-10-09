"""模型 Provider：DeepSeek（OpenAI 兼容）+ 本地离线占位 Provider。"""

from __future__ import annotations

from typing import Any

from wit import OpenAIChatProvider

from .config import Settings


class OfflineProvider:
    """占位 Provider：仅用于本地编译/生成 ACS，不发起任何模型调用。"""

    def __init__(self, model: str) -> None:
        self.model = model

    def settings(self) -> dict[str, Any]:
        return {"model": self.model, "offline": True}

    async def aclose(self) -> None:
        return None


def build_provider(settings: Settings | None = None, *, required: bool = True) -> Any:
    """构造模型 Provider。

    required=True 时必须提供 API Key（真正跑 Agent 时）；
    required=False 时缺少 Key 会退化为 OfflineProvider（仅编译/生成 ACS 用）。
    """
    settings = settings or Settings.from_env()
    if not settings.openai_api_key:
        if required:
            raise RuntimeError(
                "缺少 OPENAI_API_KEY（DeepSeek API Key）。请复制 .env.example 为 .env 并填入。"
            )
        return OfflineProvider(settings.model_name)
    return OpenAIChatProvider(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )
