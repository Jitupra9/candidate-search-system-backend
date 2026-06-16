import logging
import threading
import chromadb
from chromadb.config import Settings
from app.core.config import settings

logger = logging.getLogger(__name__)


class ChromaClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=Settings(anonymized_telemetry=False),
        )
        # Single collection — child chunk text is embedded and searched,
        # parent_content is stored inside metadata — no second collection needed
        self.collection = self._client.get_or_create_collection(
            name="candidate_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB connected")

    def health(self) -> bool:
        try:
            self._client.heartbeat()
            return True
        except Exception:
            return False


chroma = ChromaClient()
