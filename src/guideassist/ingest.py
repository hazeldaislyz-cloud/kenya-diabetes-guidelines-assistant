"""Read a guideline PDF into overlapping passages, each tagged with its page number."""
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


def clean(text: str) -> str:
    text = text.replace("­", "")            # soft hyphens
    text = re.sub(r"-\n(\w)", r"\1", text)       # words split across lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_page(text: str, page: int, max_words: int = 180, overlap: int = 40) -> list[Passage]:
    words = text.split()
    out, start, n = [], 0, 0
    while start < len(words):
        chunk = words[start:start + max_words]
        out.append(Passage(f"p{page}-{n}", page, " ".join(chunk)))
        if start + max_words >= len(words):
            break
        start += max_words - overlap
        n += 1
    return out


def load_pdf(path: str | Path) -> list[Passage]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    passages: list[Passage] = []
    for i, page in enumerate(reader.pages, start=1):
        text = clean(page.extract_text() or "")
        if len(text.split()) >= 15:            # skip blank and near-blank pages
            passages.extend(split_page(text, i))
    return passages


def save(passages: list[Passage], path: str | Path) -> None:
    Path(path).write_text("\n".join(json.dumps(asdict(p)) for p in passages))


def load(path: str | Path) -> list[Passage]:
    return [Passage(**json.loads(l)) for l in Path(path).read_text().splitlines() if l.strip()]
