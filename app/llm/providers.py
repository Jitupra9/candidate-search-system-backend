from app.core.config import settings

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
PROVIDER_MODELS = {
    "openai":    ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
    "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    "groq":      ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
    "ollama":    ["llama3.2","tinyllama"],
    "gemini":    ["gemini-1.5-pro", "gemini-1.5-flash","gemini-2.5-flash","gemini-3.1-flash-lite-preview"],
}
def get_llm(provider: str, model: str, temperature: float = 0.0):
    if provider == "openai":
        return ChatOpenAI(
            model=model,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
        )

    if provider == "anthropic":
        return ChatAnthropic(
            model=model,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
        )

    if provider == "groq":
        return ChatGroq(
            model=model,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
        )

    if provider == "ollama":
        return ChatOllama(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
        )

    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )

    raise ValueError(f"Unknown provider: {provider}")