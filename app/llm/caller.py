import asyncio
import logging
from typing import AsyncGenerator
from app.llm.providers import (
    get_openai, get_anthropic, get_groq, get_ollama, get_gemini, PROVIDER_MODELS
)
from app.core.config import settings

logger = logging.getLogger(__name__)


async def complete(
    messages: list[dict],
    provider: str = None,
    model: str = None,
    temperature: float = 0.7,
) -> str:
    provider = (provider or settings.DEFAULT_PROVIDER).lower()
    model    = model    or settings.DEFAULT_MODEL

    if provider in ("openai", "ollama"):
        client = get_openai() if provider == "openai" else get_ollama()
        resp = await client.chat.completions.create(
            model=model, messages=messages, temperature=temperature,
        )
        return resp.choices[0].message.content

    if provider == "anthropic":
        client = get_anthropic()
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        resp = await client.messages.create(
            model=model, max_tokens=4096,
            system=system, messages=user_msgs, temperature=temperature,
        )
        return resp.content[0].text

    if provider == "groq":
        resp = await get_groq().chat.completions.create(
            model=model, messages=messages, temperature=temperature,
        )
        return resp.choices[0].message.content

    if provider == "gemini":
        genai = get_gemini()
        gemini_model = genai.GenerativeModel(model)
        prompt = "\n".join(m["content"] for m in messages)
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, gemini_model.generate_content, prompt)
        return resp.text

    raise ValueError(f"Unknown provider: {provider}")


async def stream(
    messages: list[dict],
    provider: str = None,
    model: str = None,
    temperature: float = 0.7,
) -> AsyncGenerator[str, None]:
    provider = (provider or settings.DEFAULT_PROVIDER).lower()
    model    = model    or settings.DEFAULT_MODEL

    if provider in ("openai", "ollama"):
        client = get_openai() if provider == "openai" else get_ollama()
        async with await client.chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, stream=True,
        ) as s:
            async for chunk in s:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return

    if provider == "groq":
        s = await get_groq().chat.completions.create(
            model=model, messages=messages,
            temperature=temperature, stream=True,
        )
        async for chunk in s:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        return

    # Anthropic + Gemini — no native streaming, yield full response as one chunk
    yield await complete(messages, provider, model, temperature)


def list_models() -> dict:
    return PROVIDER_MODELS
