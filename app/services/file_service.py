import fitz
from pathlib import Path
class FileServices:
    @staticmethod 
    def extract_text_from_pdf(pdf_path:Path) -> str:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    @staticmethod
    def count_pages(pdf_path: Path) -> int:
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
