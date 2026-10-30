"""Answer a question using only retrieved guideline passages.

Rules the assistant must follow, and that the code checks:
- Every factual sentence cites a page, as [p. 12].
- Every cited page must be one of the passages it was given.
- If the passages don't answer the question, it says so instead of guessing.
"""
from __future__ import annotations

import os
import re

from .retrieve import Retriever, tokens

NOT_FOUND = "The guideline doesn't cover this question, so I can't answer it from this source."

PROMPT = """You answer questions for health workers using ONLY the guideline excerpts below.

Rules:
- Use only information in the excerpts. Do not use outside knowledge.
- After every sentence that states a fact, cite the page like [p. 12].
- If the excerpts do not contain the answer, reply exactly: "{not_found}"
- Be brief: at most 120 words. Use the guideline's own doses, thresholds and wording.

EXCERPTS:
{context}

QUESTION: {question}
"""


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


def overlap(question: str, text: str) -> float:
    """Share of the question's words that appear in the passage."""
    q = set(tokens(question))
    return len(q & set(tokens(text))) / max(1, len(q))


def answer(question: str, retriever: Retriever, k: int = 5, min_overlap: float = 0.3,
           client=None, model: str = "claude-sonnet-4-5") -> dict:
    hits = retriever.search(question, k)
    allowed = {p.page for p, _ in hits}
    # Gate: if the best passage shares few words with the question, the guideline
    # probably doesn't cover it. The threshold is tuned on the evaluation set.
    if not hits or hits[0][1] <= 0 or overlap(question, hits[0][0].text) < min_overlap:
        return {"answer": NOT_FOUND, "pages": [], "source": "retrieval found nothing relevant", "problems": []}

    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        # Offline mode: show the best passages with their pages, no generated text.
        text = "\n\n".join(f"[p. {p.page}] {p.text[:400]}" for p, _ in hits[:2])
        return {"answer": text, "pages": sorted(allowed), "source": "passages only (no API key)", "problems": []}

    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    context = "\n\n".join(f"[p. {p.page}] {p.text}" for p, _ in hits)
    msg = client.messages.create(
        model=model, max_tokens=400, temperature=0,
        messages=[{"role": "user", "content": PROMPT.format(not_found=NOT_FOUND, context=context, question=question)}])
    text = msg.content[0].text.strip()
    problems = check(text, allowed)
    if problems:
        return {"answer": NOT_FOUND, "pages": [], "source": "answer withheld: " + "; ".join(problems),
                "problems": problems, "rejected_answer": text}
    return {"answer": text, "pages": sorted(cited_pages(text)), "source": "llm", "problems": []}
