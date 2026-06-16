import asyncio
import json
import logging
import uuid
from app.workers.celery_app import celery_app
from app.services.s3_processor import s3_file_as_temp
from app.services.DocumentLoader import document_Loader
from app.services.text_spliter import DocumentSpliter
from app.services.Embadding import EmbeddingService
from app.core.chroma_client import chroma
from app.core.config import settings
from app.llm.prompts import RESUME_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


def _extract_candidate_data(resume_text: str) -> dict:
    """
    Call LLM synchronously to extract structured candidate data from resume text.
    Returns dict matching Candidate model fields.
    """
    import anthropic, openai
    from groq import Groq

    provider = settings.DEFAULT_PROVIDER.lower()
    model    = settings.DEFAULT_MODEL

    messages = [
        {"role": "system", "content": RESUME_EXTRACTION_PROMPT["system"]},
        {"role": "user",   "content": RESUME_EXTRACTION_PROMPT["user"].format(resume_text=resume_text[:6000])},
    ]

    if provider == "ollama":
        client = openai.OpenAI(base_url=f"{settings.OLLAMA_BASE_URL}/v1", api_key="ollama")
        resp   = client.chat.completions.create(model=model, messages=messages, temperature=0.0)
        raw    = resp.choices[0].message.content

    elif provider == "groq":
        client = Groq(api_key=settings.GROQ_API_KEY)
        resp   = client.chat.completions.create(model=model, messages=messages, temperature=0.0)
        raw    = resp.choices[0].message.content

    elif provider == "openai":
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        resp   = client.chat.completions.create(model=model, messages=messages, temperature=0.0)
        raw    = resp.choices[0].message.content

    elif provider == "anthropic":
        client  = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        system  = messages[0]["content"]
        resp    = client.messages.create(model=model, max_tokens=1024, system=system,
                                         messages=messages[1:], temperature=0.0)
        raw     = resp.content[0].text
    else:
        raise ValueError(f"Unsupported provider for extraction: {provider}")

    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


def _update_candidate_in_db(candidate_id: str, data: dict, status: str):
    """Update candidate row in PostgreSQL synchronously using psycopg2."""
    import psycopg2
    from urllib.parse import urlparse

    # Parse asyncpg URL → convert to psycopg2 format
    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(db_url)

    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE candidates SET
            name            = %s,
            email           = %s,
            phone           = %s,
            location        = %s,
            current_role    = %s,
            experience      = %s,
            skills          = %s,
            expected_salary = %s,
            notice_period   = %s,
            summary         = %s,
            status          = %s
        WHERE id = %s
        """,
        (
            data.get("name"),
            data.get("email"),
            data.get("phone"),
            data.get("location"),
            data.get("current_role"),
            data.get("experience"),
            data.get("skills") or [],
            data.get("expected_salary"),
            data.get("notice_period"),
            data.get("summary"),
            status,
            candidate_id,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()


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
            loaded_docs = asyncio.run(document_Loader(str(tmp_path)))

        # ── 3: Chunk ──────────────────────────────────────────────────────────
        chunks = DocumentSpliter.parent_child_spliter(loaded_docs)
        if not chunks:
            raise ValueError("No chunks generated from document")

        # ── 4: Embed + Store in ChromaDB ──────────────────────────────────────
        embedder = EmbeddingService()
        ids, embeddings, docs, metas = [], [], [], []

        for chunk in chunks:
            vector = embedder.get_vector(chunk.page_content)
            ids.append(str(uuid.uuid4()))
            embeddings.append(vector)
            docs.append(chunk.page_content)
            metas.append({
                "candidate_id":   candidate_id,
                "parent_index":   chunk.metadata["parent_index"],
                "parent_content": chunk.metadata["parent_content"],
                "file_type":      chunk.metadata.get("file_type", ""),
                "resume_url":     resume_url,
            })

        chroma.collection.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        logger.info("Stored %d chunks in ChromaDB for candidate=%s", len(ids), candidate_id)

        # ── 5: LLM extracts structured candidate data from full resume text ───
        full_text = " ".join(doc.page_content for doc in loaded_docs)
        extracted = _extract_candidate_data(full_text)
        logger.info("Extracted candidate data: %s", extracted.get("name"))

        # ── 6: Update PostgreSQL candidate row ────────────────────────────────
        _update_candidate_in_db(candidate_id, extracted, status="done")
        logger.info("Candidate %s updated in PostgreSQL — status=done", candidate_id)

        return {"candidate_id": candidate_id, "chunks": len(ids), "status": "done"}

    except Exception as e:
        logger.error("Failed candidate=%s: %s", candidate_id, e)
        _update_candidate_in_db(candidate_id, {}, status="failed")
        raise self.retry(exc=e, countdown=10)
