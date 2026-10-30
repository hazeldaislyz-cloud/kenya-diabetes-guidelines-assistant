"""Answer a question using only retrieved guideline passages.

Rules the assistant must follow, and that the code checks:
- Every factual sentence cites a page, as [p. 12].
- Every cited page must be one of the passages it was given.
- If the passages don't answer the question, it says so instead of guessing.
- If it relies on text read by OCR from a figure, it tells the reader to check the figure.
"""
from __future__ import annotations

import os
import re

from .retrieve import Retriever

MIN_COVERAGE = 0.5  # chosen on eval/questions.jsonl; checked on eval/heldout.jsonl

NOT_FOUND = "The guideline doesn't cover this question, so I can't answer it from this source."

PROMPT = """You answer questions for health workers using ONLY the guideline excerpts below.

Rules:
- Use only information in the excerpts. Do not use outside knowledge.
- After every sentence that states a fact, cite the page like [p. 12].
- If the excerpts do not contain the answer, reply exactly: "{not_found}"
- Be brief: at most 120 words. Use the guideline's own doses, thresholds and wording.
- Excerpts marked "figure text, read by OCR" come from images and may contain reading
  errors. If you use one, end with: "Check the figure on page N before acting."

{unknown}EXCERPTS:
{context}

QUESTION: {question}
"""


def _label(p) -> str:
    return ", figure text, read by OCR" if getattr(p, "source", "text") == "ocr" else ""


def cited_pages(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[p\.?\s*(\d+)\]", text)}


def check(answer: str, allowed_pages: set[int]) -> list[str]:
    """Return a list of problems; empty means the answer passed."""
    if answer.strip() == NOT_FOUND:
        return []
    problems = []
    pages = cited_pages(answer)
    if not pages:
        problems.append("no citations")
    if pages - allowed_pages:
        problems.append(f"cites pages it was not given: {sorted(pages - allowed_pages)}")
    return problems


def answer(question: str, retriever: Retriever, k: int = 5, min_coverage: float = MIN_COVERAGE,
           client=None, model: str = "claude-sonnet-5-5") -> dict:
    hits = retriever.search(question, k)
    allowed = {p.page for p, _ in hits}
    ocr_pages = sorted({p.page for p, _ in hits if p.source == "ocr"})
    # Gate: if the retrieved passages cover little of the question (weighting rare words
    # most), the guideline probably doesn't address it, so don't call a model at all.
    if not hits or hits[0][1] <= 0 or retriever.coverage(question, hits) < min_coverage:
        return {"answer": NOT_FOUND, "pages": [], "source": "retrieval found nothing relevant", "problems": []}
    unknown = retriever.unknown_terms(question)
    note = f" Note: the guideline never mentions: {', '.join(unknown)}." if unknown else ""

    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        # Offline mode: show the best passages with their pages, no generated text.
        text = "\n\n".join(f"[p. {p.page}{_label(p)}] {p.text[:400]}" for p, _ in hits[:2])
        return {"answer": text + note, "pages": sorted(allowed), "source": "passages only (no API key)", "problems": []}

    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    context = "\n\n".join(f"[p. {p.page}{_label(p)}] {p.text}" for p, _ in hits)
    msg = client.messages.create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content": PROMPT.format(
            not_found=NOT_FOUND, context=context, question=question,
            unknown=(f"The guideline never uses these words from the question: {', '.join(unknown)}. "
                     "If the answer depends on them, reply with the not-found sentence.\n\n") if unknown else "")}])
    # Join the text blocks of the reply (newer models may also return other block types).
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "text") == "text").strip()
    problems = check(text, allowed)
    if problems:
        return {"answer": NOT_FOUND, "pages": [], "source": "answer withheld: " + "; ".join(problems),
                "problems": problems, "rejected_answer": text}
    pages = cited_pages(text)
    used_ocr = sorted(pages & set(ocr_pages))
    if used_ocr and "check the figure" not in text.lower():
        text += f" Check the figure on page {used_ocr[0]} before acting."
    if note and text.strip() != NOT_FOUND:
        text += note
    return {"answer": text, "pages": sorted(pages), "source": "llm", "problems": []}
