import fitz
from pathlib import Path
class FileServices:
    async def extract_text_from_pdf(pdf_path:Path) -> str:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
