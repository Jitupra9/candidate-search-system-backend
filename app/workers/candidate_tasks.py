import asyncio
import json
import logging
from datetime import date
import uuid
from app.workers.celery_app import celery_app
from app.services.s3_processor import s3_file_as_temp
from app.services.DocumentLoader import document_Loader
from app.services.text_spliter import DocumentSpliter
from app.services.Embadding import EmbeddingService
from app.core.chroma_client import chroma
from app.core.config import settings
from app.llm.prompts import RESUME_EXTRACTION_PROMPT
from app.llm.providers import get_llm
from app.schemas.candidate import CandidateExtraction
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.candidate_utils import update_candidate_from_task
logger = logging.getLogger(__name__)


def _extract_candidate_data(resume_text: str) -> dict:
    provider = settings.DEFAULT_PROVIDER
    model = settings.DEFAULT_MODEL
    llm = get_llm(provider, model).with_structured_output(CandidateExtraction)
    messages = [
        SystemMessage(
            content=RESUME_EXTRACTION_PROMPT["system"].format(today=date.today().isoformat())
        ),
        HumanMessage(
            content=RESUME_EXTRACTION_PROMPT["user"].format(
                resume_text=resume_text
            )
        ),
    ]
    response = llm.invoke(messages)
    return response





@celery_app.task(bind=True, name="process_candidate_resume", max_retries=2)
def process_candidate_resume(self, resume_url: str, candidate_id: str):
    """
    Full background pipeline:
      1. Download file from S3
      2. Load + parse document (PDF/DOCX/CSV/XLSX/TXT)
      3. Parent-child chunk split
      4. Embed child chunks → store in ChromaDB (vector search)
      5. LLM extracts structured data from full resume text
      6. Update Candidate row in PostgreSQL with extracted data + status=done
    """
    try:
        logger.info("Processing resume candidate=%s", candidate_id)

        # ── 1 & 2: Download + Load ────────────────────────────────────────────
        with s3_file_as_temp(resume_url) as tmp_path:
            loaded_docs = document_Loader(str(tmp_path))

        # ── 3: Prepare chunks (auto: short resume = 1 chunk, long CV = split) ──
        chunks = DocumentSpliter.smart_split(loaded_docs)
        if not chunks:
            raise ValueError("No chunks generated from document")

        # ── 4: Embed + Store in ChromaDB ──────────────────────────────────────
        embedder = EmbeddingService()
        texts = [chunk.page_content for chunk in chunks]

        if hasattr(embedder, "get_vectors"):
            vectors = embedder.get_vectors(texts)
        else:
            vectors = [embedder.get_vector(t) for t in texts]

        ids, embeddings, docs, metas = [], [], [], []
        for chunk, vector in zip(chunks, vectors):
            ids.append(str(uuid.uuid4()))
            embeddings.append(vector)
            docs.append(chunk.page_content)
            metas.append({
                "candidate_id":  candidate_id,
                "content_index": chunk.metadata["content_index"],
                "content":       chunk.metadata["content"],
                "file_type":     chunk.metadata.get("file_type", ""),
                "resume_url":    resume_url,
            })

        chroma.collection.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        logger.info("Stored %d chunks in ChromaDB for candidate=%s", len(ids), candidate_id)

        # ── 5: LLM extracts structured candidate data from full resume text ───
        full_text = " ".join(doc.page_content for doc in loaded_docs)
        extracted = _extract_candidate_data(full_text)
        # logger.info("Extracted candidate data: %s", extracted.get("name"))

        # ── 6: Update PostgreSQL candidate row ────────────────────────────────
        update_candidate_from_task(candidate_id, extracted, status="done")
        logger.info("Candidate %s updated in PostgreSQL — status=done", candidate_id)

        return {"candidate_id": candidate_id, "chunks": len(ids), "status": "done"}

    except Exception as e:
        logger.error("Failed candidate=%s: %s", candidate_id, e)
        if self.request.retries >= self.max_retries:
            update_candidate_from_task(candidate_id, None, status="failed")
            logger.error("Candidate %s permanently failed after %d retries", candidate_id, self.request.retries)
        raise self.retry(exc=e, countdown=10)
