import logging
import threading
import time
from langchain_ollama import OllamaEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:                     
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_model()
        return cls._instance

    def _init_model(self):
        self.model = OllamaEmbeddings(
            model=settings.EMBEDDING_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )
        logger.info("Embedding model initialized: %s", settings.EMBEDDING_MODEL)

    def get_vector(self, query: str) -> list[float]:
        if not query or not query.strip():
            raise ValueError("Query must be a non-empty string")

        last_error = None
        for attempt in range(3):
            try:
                return self.model.embed_query(query)
            except Exception as e:
                last_error = e
                logger.warning("Embedding attempt %d failed: %s", attempt + 1, e)
                time.sleep(2 ** attempt)

        raise RuntimeError(f"Embedding failed after 3 attempts: {last_error}")
