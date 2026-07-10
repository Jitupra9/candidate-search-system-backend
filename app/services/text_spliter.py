from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Total character threshold to decide short (resume) vs long (CV).
# Below this  → merge all pages into one embedding (full text, no splitting).
# At or above → RecursiveCharacterTextSplitter into chunks.
_SHORT_DOC_CHAR_THRESHOLD = 4500

_CV_CHUNK_SIZE    = 1500
_CV_CHUNK_OVERLAP = 150


class DocumentSpliter:

    @staticmethod
    def smart_split(docs: list[Document]) -> list[Document]:
        """Auto-detect short resume vs long CV and process accordingly.

        Short document (total chars < 3000 — e.g. a 1-2 paragraph resume):
          → Merge all pages/sections into one string.
          → Store as a single ChromaDB entry.
          → Full text is both the embedding input and the LLM context.

        Long document (total chars >= 3000 — e.g. a multi-section CV):
          → Merge all pages/sections into one string.
          → Split with RecursiveCharacterTextSplitter (chunk_size=1000).
          → Each chunk stored with content + content_index.
        """
        full_text = "\n\n".join(
            doc.page_content.strip()
            for doc in docs
            if doc.page_content.strip()
        )
        if not full_text:
            return []

        # Base metadata from first doc — drop page-level keys that vary per page
        base_meta = {
            k: v for k, v in docs[0].metadata.items()
            if k not in ("page", "section_index", "row_index", "has_table")
        }

        if len(full_text) < _SHORT_DOC_CHAR_THRESHOLD:
            # ── Short resume: single chunk, full text ─────────────────────────
            return [Document(
                page_content=full_text,
                metadata={**base_meta, "content": full_text, "content_index": 0},
            )]

        # ── Long CV: recursive split ──────────────────────────────────────────
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CV_CHUNK_SIZE,
            chunk_overlap=_CV_CHUNK_OVERLAP,
        )
        raw_chunks = splitter.create_documents([full_text], metadatas=[base_meta])

        final_docs: list[Document] = []
        for idx, chunk in enumerate(raw_chunks):
            text = chunk.page_content.strip()
            if not text:
                continue
            final_docs.append(Document(
                page_content=text,
                metadata={**base_meta, "content": text, "content_index": idx},
            ))
        return final_docs

    # ── kept for backward compatibility ──────────────────────────────────────

    @staticmethod
    def flat_splitter(docs: list[Document]) -> list[Document]:
        """Store each loader page/section as one entry — no merging, no splitting."""
        final_docs: list[Document] = []
        for idx, doc in enumerate(docs):
            text = doc.page_content.strip()
            if not text:
                continue
            final_docs.append(Document(
                page_content=text,
                metadata={**doc.metadata, "content": text, "content_index": idx},
            ))
        return final_docs
