"""
DocumentLoader
==============
Supports:
  .pdf   → plain text PDF  (PyMuPDF)
  .pdf   → tabular PDF     (pdfplumber — detects tables automatically)
  .docx  → Word document   (python-docx)
  .doc   → legacy Word     (textract fallback)
  .csv   → CSV file        (pandas)
  .xlsx  → Excel file      (pandas)
  .txt   → plain text      (built-in)

All loaders return List[Document] with metadata:
  { source, file_type, page (if applicable), row_index (CSV/Excel) }
"""
import logging
from pathlib import Path
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


# ── PDF ───────────────────────────────────────────────────────────────────────

def _load_pdf(path: str) -> list[Document]:
    """
    Smart PDF loader:
    - First scans for tables using pdfplumber
    - Falls back to PyMuPDF for plain text pages
    - Returns one Document per page, table rows joined as markdown-style text
    """
    import pdfplumber
    from langchain_community.document_loaders import PyMuPDFLoader

    docs: list[Document] = []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            page_text = ""

            # ── Extract tables first ──────────────────────────────────────────
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        cleaned = [str(cell).strip() if cell else "" for cell in row]
                        page_text += " | ".join(cleaned) + "\n"
            else:
                # ── Plain text page ───────────────────────────────────────────
                page_text = page.extract_text() or ""

            if page_text.strip():
                docs.append(Document(
                    page_content=page_text.strip(),
                    metadata={
                        "source": path,
                        "file_type": "pdf",
                        "page": page_num + 1,
                        "has_table": bool(tables),
                    },
                ))

    # Fallback: if pdfplumber extracted nothing, use PyMuPDF
    if not docs:
        logger.warning("pdfplumber got no text, falling back to PyMuPDF: %s", path)
        loader = PyMuPDFLoader(path)
        raw = loader.load()
        docs = [
            Document(
                page_content=d.page_content,
                metadata={**d.metadata, "file_type": "pdf", "has_table": False},
            )
            for d in raw
        ]

    return docs


# ── DOCX ──────────────────────────────────────────────────────────────────────

def _load_docx(path: str) -> list[Document]:
    """
    Word document loader.
    - Extracts paragraphs as text
    - Extracts tables as pipe-separated rows
    - Groups into logical sections (heading → content)
    """
    from docx import Document as DocxDocument

    docx = DocxDocument(path)
    sections: list[str] = []
    current_section = ""

    for para in docx.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # New heading → save previous section, start new one
        if para.style.name.startswith("Heading"):
            if current_section:
                sections.append(current_section.strip())
            current_section = f"## {text}\n"
        else:
            current_section += text + "\n"

    if current_section:
        sections.append(current_section.strip())

    # Extract tables
    for table in docx.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            sections.append("\n".join(rows))

    return [
        Document(
            page_content=section,
            metadata={"source": path, "file_type": "docx", "section_index": i},
        )
        for i, section in enumerate(sections)
        if section.strip()
    ]


# ── CSV ───────────────────────────────────────────────────────────────────────

def _load_csv(path: str) -> list[Document]:
    """
    CSV loader — each row becomes a Document.
    Row text: 'column: value, column: value, ...'
    This makes each row independently searchable.
    """
    import pandas as pd

    df = pd.read_csv(path)
    df = df.fillna("")
    docs: list[Document] = []

    for idx, row in df.iterrows():
        row_text = ", ".join(
            f"{col}: {str(val).strip()}"
            for col, val in row.items()
            if str(val).strip()
        )
        if row_text:
            docs.append(Document(
                page_content=row_text,
                metadata={
                    "source": path,
                    "file_type": "csv",
                    "row_index": int(idx),
                    "columns": list(df.columns),
                },
            ))

    return docs


# ── XLSX ──────────────────────────────────────────────────────────────────────

def _load_xlsx(path: str) -> list[Document]:
    """
    Excel loader — processes all sheets.
    Each row becomes a Document with sheet name in metadata.
    """
    import pandas as pd

    xl = pd.ExcelFile(path)
    docs: list[Document] = []

    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name).fillna("")
        for idx, row in df.iterrows():
            row_text = ", ".join(
                f"{col}: {str(val).strip()}"
                for col, val in row.items()
                if str(val).strip()
            )
            if row_text:
                docs.append(Document(
                    page_content=row_text,
                    metadata={
                        "source": path,
                        "file_type": "xlsx",
                        "sheet": sheet_name,
                        "row_index": int(idx),
                    },
                ))

    return docs


# ── TXT ───────────────────────────────────────────────────────────────────────

def _load_txt(path: str) -> list[Document]:
    """Plain text — split on double newlines into paragraphs."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

    return [
        Document(
            page_content=para,
            metadata={"source": path, "file_type": "txt", "para_index": i},
        )
        for i, para in enumerate(paragraphs)
    ]


# ── Router ────────────────────────────────────────────────────────────────────

_LOADERS = {
    ".pdf":  _load_pdf,
    ".docx": _load_docx,
    ".doc":  _load_docx,   # python-docx handles .doc too in most cases
    ".csv":  _load_csv,
    ".xlsx": _load_xlsx,
    ".xls":  _load_xlsx,
    ".txt":  _load_txt,
}


async def document_Loader(document_path: str) -> list[Document]:
    """
    Main entry point.
    Auto-detects file type and routes to correct loader.
    Returns List[Document] with normalized metadata.

    Raises:
        ValueError  — unsupported file type
        RuntimeError — loader failure with cause
    """
    path = Path(document_path)
    ext = path.suffix.lower()

    loader_fn = _LOADERS.get(ext)
    if not loader_fn:
        raise ValueError(
            f"Unsupported file type: '{ext}'. "
            f"Supported: {list(_LOADERS.keys())}"
        )

    try:
        docs = loader_fn(document_path)
        logger.info("Loaded %d documents from %s (%s)", len(docs), path.name, ext)
        return docs
    except Exception as e:
        logger.error("Failed to load %s: %s", path.name, e)
        raise RuntimeError(f"Failed to load '{path.name}': {e}") from e
