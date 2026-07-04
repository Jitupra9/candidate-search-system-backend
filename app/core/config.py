from pydantic_settings import BaseSettings, SettingsConfigDict

import os
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )

    # ── APP ──────────────────────────────────────────────────
    APP_NAME: str
    APP_ENV: str
    DEBUG: bool = os.getenv('DEBUG')
    SECRET_KEY: str
    FRONTEND_URL: str = os.getenv('FRONTEND_URL')

    # ── DATABASE ─────────────────────────────────────────────
    DATABASE_URL: str   = os.getenv('DATABASE_URL')   

    # ── REDIS ─────────────────────────────────────────────────
    REDIS_URL: str = os.getenv('REDIS_URL') 

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET_KEY: str = os.getenv('JWT_SECRET_KEY') 
    JWT_ALGORITHM: str = os.getenv('JWT_ALGORITHM') 
    JWT_ACCESS_TOKEN_EXPIRES: int = os.getenv('JWT_ACCESS_TOKEN_EXPIRES')   # minutes
    JWT_REFRESH_TOKEN_EXPIRES: int =os.getenv('JWT_REFRESH_TOKEN_EXPIRES')   # minutes (12 hours)

    # ── EMAIL ─────────────────────────────────────────────────
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: str

    # ── AWS S3 ────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY: str =os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_REGION: str = os.getenv('AWS_REGION')
    AWS_S3_BUCKET:str =os.getenv('AWS_S3_BUCKET')
    MAX_FILE_SIZE_MB:int = 50

    OPENAI_API_KEY    : str = ""
    ANTHROPIC_API_KEY : str = ""
    GEMINI_API_KEY    : str = os.getenv('GEMINI_API_KEY')
    GROQ_API_KEY      : str = ""
    OLLAMA_BASE_URL   : str = "http://localhost:11434"
    EMBEDDING_MODEL   : str = "nomic-embed-text"

    # Default LLM — set in .env
    # development : DEFAULT_PROVIDER=ollama  DEFAULT_MODEL=llama3.2
    # production  : DEFAULT_PROVIDER=groq    DEFAULT_MODEL=llama-3.3-70b-versatile
    DEFAULT_PROVIDER  : str = "ollama"
    DEFAULT_MODEL     : str = "tinyllama"

    # ChromaDB
    CHROMA_HOST : str = "localhost"
    CHROMA_PORT : int = 8000


settings = Settings()