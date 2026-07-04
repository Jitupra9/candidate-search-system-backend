import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# File types where rows must NOT be split further — each row is already a chunk
_TABULAR_TYPES = {"csv", "xlsx", "xls"}

# A line is a "section heading" candidate if short, all-caps-ish, no trailing
# punctuation that would suggest it's a sentence fragment.
_HEADING_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9 &/\-,]{2,40}$")

# Minimum useful length for a final chunk's own text (after stripping).
# Anything shorter than this and matching the heading pattern (or just very
# short generically) is considered "low-signal" and gets merged forward
# instead of being emitted as its own chunk.
_MIN_CHUNK_CHARS = 25


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0].strip() if text.strip() else ""


def _is_heading_only(text: str) -> bool:
    """True if the chunk is just a bare section heading with no body."""
    stripped = text.strip()
    if not stripped:
        return True
    lines = [l for l in stripped.splitlines() if l.strip()]
    if len(lines) == 1 and len(stripped) <= _MIN_CHUNK_CHARS:
        return bool(_HEADING_PATTERN.match(lines[0].strip()))
    return False


def _last_heading_in(text: str) -> str | None:
    """Find the last ALL-CAPS heading-looking line within a block of text,
    so it can be carried forward into the next parent chunk for context."""
    candidate = None
    for line in text.splitlines():
        line = line.strip()
        if _HEADING_PATTERN.match(line):
            candidate = line
    return candidate


class DocumentSpliter:

    @staticmethod
    def parent_child_spliter(docs: list[Document]) -> list[Document]:

        # Parent chunks: larger context window fed to the LLM at answer time.
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        # Child chunks: smaller, used for embedding/retrieval precision.
        # Bumped from 200/20 -> 350/50 to avoid severing compound terms
        # (e.g. "Llama 3", "GPT-4o") across chunk boundaries.
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=350, chunk_overlap=50
        )

        final_docs: list[Document] = []
        parent_index = 0
        carried_heading: str | None = None

        for doc in docs:
            file_type = doc.metadata.get("file_type", "")

            if file_type in _TABULAR_TYPES:
                # ── Tabular: row is both parent and child ─────────────────────
                # Row text is already small enough — no further splitting
                if doc.page_content.strip():
                    final_docs.append(Document(
                        page_content=doc.page_content,
                        metadata={
                            **doc.metadata,
                            "parent_content": doc.page_content,
                            "parent_index": parent_index,
                        },
                    ))
                    parent_index += 1
                continue

            # ── Text: recursive parent → child split ──────────────────────
            source_text = doc.page_content
            if carried_heading and not source_text.lstrip().startswith(carried_heading):
                # Re-attach the most recent section heading so this doc's
                # parent chunks don't lose section context across the
                # page/document boundary.
                source_text = f"{carried_heading}\n{source_text}"

            parent_docs = parent_splitter.create_documents(
                [source_text],
                metadatas=[doc.metadata],
            )

            for parent in parent_docs:
                # Track the latest heading seen so far so it can be carried
                # into the *next* Document if this one ends mid-section.
                heading_here = _last_heading_in(parent.page_content)
                if heading_here:
                    carried_heading = heading_here

                child_docs = child_splitter.split_documents([parent])

                for child in child_docs:
                    if _is_heading_only(child.page_content):
                        # Skip emitting a standalone heading-only chunk —
                        # it carries no answerable content on its own and
                        # only wastes a retrieval slot.
                        continue
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
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=100
        )
        return splitter.create_documents([raw_text])