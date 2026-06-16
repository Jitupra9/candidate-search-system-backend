from app.core.config import settings

# ── Model registry — add new models here only ─────────────────────────────────
PROVIDER_MODELS = {
    "openai":    ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    "groq":      ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
    "ollama":    ["llama3.2", "mistral", "phi3"],
    "gemini":    ["gemini-1.5-pro", "gemini-1.5-flash"],
}


def get_openai():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


def get_anthropic():
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def get_groq():
    from groq import AsyncGroq
    return AsyncGroq(api_key=settings.GROQ_API_KEY)


def get_ollama():
    from openai import AsyncOpenAI
    return AsyncOpenAI(base_url=f"{settings.OLLAMA_BASE_URL}/v1", api_key="ollama")


def get_gemini():
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai
