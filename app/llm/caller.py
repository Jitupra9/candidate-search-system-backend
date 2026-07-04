import logging
from typing import AsyncGenerator

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
)

from app.core.config import settings
from app.llm.providers import get_llm
from app.llm.providers import PROVIDER_MODELS

logger = logging.getLogger(__name__)


def _convert_messages(messages: list[dict]):
    """Convert OpenAI-style messages to LangChain messages."""
    converted = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "user":
            converted.append(HumanMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            raise ValueError(f"Unknown role: {role}")

    return converted

def validate_provider_model(provider: str, model: str) -> None:
    provider = provider.lower()

    if provider not in PROVIDER_MODELS:
        raise ValueError(f"Unknown provider: {provider}")

    if model not in PROVIDER_MODELS[provider]:
        raise ValueError(
            f"Model '{model}' does not belong to provider '{provider}'. "
            f"Available models: {', '.join(PROVIDER_MODELS[provider])}"
        )
async def complete(
    messages: list[dict],
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
) -> str:
    provider = (provider or settings.DEFAULT_PROVIDER).lower()
    model = model or settings.DEFAULT_MODEL
    validate_provider_model(provider, model)
    logger.debug(
        "complete provider=%s model=%s",
        provider,
        model,
    )

    llm = get_llm(
        provider=provider,
        model=model,
        temperature=temperature,
    )

    response = await llm.ainvoke(_convert_messages(messages))

    return response.content


async def stream(
    messages: list[dict],
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:

    provider = (provider or settings.DEFAULT_PROVIDER).lower()
    model = model or settings.DEFAULT_MODEL
    validate_provider_model(provider, model)
    llm = get_llm(
        provider=provider,
        model=model,
        temperature=temperature,
    )

    async for chunk in llm.astream(_convert_messages(messages)):
        if chunk.content:
            yield chunk.content


def list_models():
    return PROVIDER_MODELS