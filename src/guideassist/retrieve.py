"""Find the passages most relevant to a question (BM25 keyword ranking).

BM25 runs fully offline and is easy to explain: passages that share rare words with
the question score highest. Clinical questions often turn on exact terms (HbA1c,
metformin, eGFR), which keyword ranking handles well.
"""
from __future__ import annotations

import math
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


def norm(t: str) -> str:
    """Light normalisation so different forms of a word match: British and American
    spelling (hypoglycaemia/hypoglycemia, oedema/edema) and common word endings
    (screened/screening/screen)."""
    if t[0].isdigit():
        return t
    t = t.replace("ae", "e").replace("oe", "e")
    for suffix in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 4:
            return t[: -len(suffix)]
    return t


def tokens(text: str) -> list[str]:
    raw = [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()) if t not in STOP]
    extra = [s for t in raw for s in SYNONYMS.get(t, [])]
    return [norm(t) for t in raw + extra]


class Retriever:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        toks = [tokens(p.text) for p in passages]
        self.bm25 = BM25Okapi(toks)
        self.df: dict[str, int] = {}
        for t in toks:
            for w in set(t):
                self.df[w] = self.df.get(w, 0) + 1
        self._prefixes = {w[:6] for w in self.df if len(w) >= 6}

    def idf(self, term: str) -> float:
        """Rarity of a word in the guideline. Words it never uses count the most."""
        return math.log((len(self.passages) + 1) / (self.df.get(term, 0) + 0.5))

    def coverage(self, question: str, hits: list[tuple[Passage, float]]) -> float:
        """Share of the question's meaning, weighted by word rarity, found in the passages.
        Low coverage means the guideline probably doesn't address the question."""
        q = set(tokens(question))
        found = {t for p, _ in hits for t in tokens(p.text)}
        total = sum(self.idf(t) for t in q)
        return sum(self.idf(t) for t in q if t in found) / total if total else 0.0

    def unknown_terms(self, question: str) -> list[str]:
        """Words in the question that the guideline never uses (allowing simple word endings)."""
        out = []
        for word in sorted(set(re.findall(r"[a-z]+", question.lower())) - STOP):
            t = norm(word)
            if len(t) < 4 or t in self.df or (len(t) >= 6 and t[:6] in self._prefixes):
                continue
            out.append(word)
        return out

    def search(self, question: str, k: int = 5) -> list[tuple[Passage, float]]:
        scores = self.bm25.get_scores(tokens(question))
        best = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [(self.passages[i], float(scores[i])) for i in best]
