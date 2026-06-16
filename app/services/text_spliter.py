from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# File types where rows must NOT be split further — each row is already a chunk
_TABULAR_TYPES = {"csv", "xlsx", "xls"}


class DocumentSpliter:

    @staticmethod
    def parent_child_spliter(docs: list[Document]) -> list[Document]:
        """
        Smart parent-child split:
        - Tabular docs (CSV/Excel): each row = one child, row = parent (no split needed)
        - Text docs (PDF/DOCX/TXT): parent=1000 chars, child=200 chars

        Child stored in vector DB (small, fast search).
        Parent content stored in metadata (full context for LLM).
        """
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=200, chunk_overlap=20
        )

        final_docs: list[Document] = []
        parent_index = 0

        for doc in docs:
            file_type = doc.metadata.get("file_type", "")

            if file_type in _TABULAR_TYPES:
                # ── Tabular: row is both parent and child ─────────────────────
                # Row text is already small enough — no further splitting
                final_docs.append(Document(
                    page_content=doc.page_content,
                    metadata={
                        **doc.metadata,
                        "parent_content": doc.page_content,
                        "parent_index": parent_index,
                    },
                ))
                parent_index += 1

            else:
                # ── Text: recursive parent → child split ──────────────────────
                parent_docs = parent_splitter.create_documents(
                    [doc.page_content],
                    metadatas=[doc.metadata],
                )
                for parent in parent_docs:
                    child_docs = child_splitter.split_documents([parent])
                    for child in child_docs:
                        final_docs.append(Document(
                            page_content=child.page_content,
                            metadata={
                                **doc.metadata,
                                "parent_content": parent.page_content,
                                "parent_index": parent_index,
                            },
                        ))
                    parent_index += 1

        return final_docs

    @staticmethod
    def recursive_split(raw_text: str) -> list[Document]:
        """Simple flat split — use when you only have raw text string."""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=100
        )
        return splitter.create_documents([raw_text])
