# app/utils/text_extract.py
import os
import logging
from typing import Tuple, Dict, Any

import pdfplumber
from docx import Document

logger = logging.getLogger(__name__)


def _extract_text_pdf(path: str) -> Tuple[str, int]:
    """Returns (text, page_count)."""
    text_parts = []
    page_count = 0
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            # extract_text may return None
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n\n".join(text_parts), page_count


def _extract_text_docx(path: str) -> str:
    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_text_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def is_probably_scanned(text: str, page_count: int, char_threshold_per_page: int = 50) -> bool:
    """
    Heuristic: if average characters per page is below threshold, likely scanned image PDF.
    Returns True if likely scanned.
    """
    if page_count <= 0:
        return False
    avg = max(0, len(text)) / page_count
    return avg < char_threshold_per_page


def extract_text(file_path: str, return_meta: bool = False) -> Any:
    """
    Extract text from .pdf, .docx, .txt.
    If return_meta is False (default) returns a string containing extracted text.
    If return_meta is True returns a dict: {'text': str, 'page_count': int|None, 'is_scanned': bool}
    Notes:
      - This function does NOT perform OCR. If PDF is scanned (images), extracted text will be empty or tiny.
      - For scanned PDFs, see the OCR snippet in the module docstring or call external OCR pipeline.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    lower = file_path.lower()
    text = ""
    page_count = None

    try:
        if lower.endswith(".pdf"):
            text, page_count = _extract_text_pdf(file_path)
        elif lower.endswith(".docx"):
            text = _extract_text_docx(file_path)
            page_count = None
        elif lower.endswith(".txt"):
            text = _extract_text_txt(file_path)
            page_count = None
        else:
            # attempt basic read for unknown file types
            try:
                text = _extract_text_txt(file_path)
            except Exception:
                raise ValueError("Unsupported file type. Supported: .pdf, .docx, .txt")
    except Exception as e:
        logger.exception("Failed to extract text: %s", e)
        raise

    scanned = False
    if page_count is not None:
        scanned = is_probably_scanned(text, page_count)

    if return_meta:
        return {"text": text, "page_count": page_count, "is_scanned": scanned}
    return text
