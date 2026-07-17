from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List
import io

@dataclass
class PageText:
    page: int
    text: str
    used_ocr: bool = False

    def to_dict(self):
        return asdict(self)

class PDFParser:
    def __init__(self, use_ocr: bool = False, min_page_text_chars: int = 80):
        self.use_ocr = use_ocr
        self.min_page_text_chars = min_page_text_chars

    def parse(self, pdf_path: Path) -> List[PageText]:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("缺少PyMuPDF，请先执行 pip install -r requirements.txt") from exc

        pages: List[PageText] = []
        with fitz.open(pdf_path) as doc:
            for idx, page in enumerate(doc):
                text = page.get_text("text") or ""
                used_ocr = False
                if self.use_ocr and len(text.strip()) < self.min_page_text_chars:
                    text = self._ocr_page(page)
                    used_ocr = True
                pages.append(PageText(page=idx + 1, text=text, used_ocr=used_ocr))
        return pages

    @staticmethod
    def _ocr_page(page) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("已启用OCR，但缺少pytesseract或Pillow") from exc

        import fitz
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, lang="chi_sim+eng")
