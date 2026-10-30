"""Read a guideline PDF into overlapping passages, each tagged with its page number.

Many clinical guidelines put key content (flowcharts, dosing tables) in images, which
plain text extraction can't read. If Tesseract OCR is installed, every page is also read
by OCR, and where OCR finds substantial text that extraction missed, that text is added
as extra passages marked source="ocr". OCR can misread numbers, so answers that rely on
it tell the reader to check the original figure.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Passage:
    id: str
    page: int          # 1-based page in the PDF file
    text: str
    source: str = "text"   # "text" (extracted) or "ocr" (read from an image)


def clean(text: str) -> str:
    text = text.replace("­", "")            # soft hyphens
    text = re.sub(r"-\n(\w)", r"\1", text)       # words split across lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


OCR_MIN_NEW_WORDS = 25  # add OCR text only where it finds this many words extraction missed


def split_page(text: str, page: int, max_words: int = 180, overlap: int = 40,
               source: str = "text") -> list[Passage]:
    words = text.split()
    out, start, n = [], 0, 0
    tag = "" if source == "text" else f"-{source}"
    while start < len(words):
        chunk = words[start:start + max_words]
        out.append(Passage(f"p{page}{tag}-{n}", page, " ".join(chunk), source))
        if start + max_words >= len(words):
            break
        start += max_words - overlap
        n += 1
    return out


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", text.lower()))


def ocr_pages(path: str | Path, scale: float = 2.5) -> dict[int, str]:
    """OCR every page. Returns {} if Tesseract or its Python wrapper isn't installed."""
    try:
        import pypdfium2 as pdfium
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        print("OCR skipped: install Tesseract and pytesseract to read text inside images.")
        return {}
    doc = pdfium.PdfDocument(str(path))
    return {i + 1: pytesseract.image_to_string(doc[i].render(scale=scale).to_pil()) for i in range(len(doc))}


def load_pdf(path: str | Path, ocr: bool = True) -> list[Passage]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    texts = {i: clean(p.extract_text() or "") for i, p in enumerate(reader.pages, start=1)}
    ocr_text = ocr_pages(path) if ocr else {}
    passages: list[Passage] = []
    for i, text in texts.items():
        if len(text.split()) >= 15:            # skip blank and near-blank pages
            passages.extend(split_page(text, i))
        o = clean(ocr_text.get(i, ""))
        if len(_words(o) - _words(text)) >= OCR_MIN_NEW_WORDS:
            passages.extend(split_page(o, i, source="ocr"))
    return passages


def save(passages: list[Passage], path: str | Path) -> None:
    Path(path).write_text("\n".join(json.dumps(asdict(p)) for p in passages))


def load(path: str | Path) -> list[Passage]:
    return [Passage(**json.loads(l)) for l in Path(path).read_text().splitlines() if l.strip()]
