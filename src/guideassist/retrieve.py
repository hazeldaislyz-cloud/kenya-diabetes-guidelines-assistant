"""Find the passages most relevant to a question (BM25 keyword ranking).

BM25 runs fully offline and is easy to explain: passages that share rare words with
the question score highest. Clinical questions often turn on exact terms (HbA1c,
metformin, eGFR), which keyword ranking handles well.
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from .ingest import Passage

STOP = set("""a an and are as at be by can do does for from how i in is it of on or should
the this to what when which who with you your patient patients""".split())

SYNONYMS = {  # expand common abbreviations both ways
    "hba1c": ["a1c", "glycated", "haemoglobin", "hemoglobin"],
    "t2dm": ["type", "2", "diabetes"], "t1dm": ["type", "1", "diabetes"],
    "dka": ["ketoacidosis"], "bp": ["blood", "pressure"], "ckd": ["kidney", "renal"],
    "hypo": ["hypoglycaemia", "hypoglycemia"],
}


def tokens(text: str) -> list[str]:
    toks = [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()) if t not in STOP]
    extra = [s for t in toks for s in SYNONYMS.get(t, [])]
    return toks + extra


class Retriever:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self.bm25 = BM25Okapi([tokens(p.text) for p in passages])

    def search(self, question: str, k: int = 5) -> list[tuple[Passage, float]]:
        scores = self.bm25.get_scores(tokens(question))
        best = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [(self.passages[i], float(scores[i])) for i in best]
