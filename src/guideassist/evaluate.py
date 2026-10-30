"""Score the assistant against a hand-written question set (eval/questions.jsonl).

Each line: {"question": ..., "expected_pages": [12, 13], "key_facts": ["metformin", "500"],
            "in_scope": true}

Every key fact was checked by hand against the expected page of the guideline.

Retrieval measures (run offline, no API key needed):
- page hit rate: an expected page is among the top 5 passages
- evidence found: every key fact appears in the top 5 passages, so a model could answer
- in-scope questions wrongly refused, out-of-scope questions correctly refused: the
  relevance gate that runs before any model is called
- unknown-word warnings: questions using words the guideline never uses

Answer measures (only when an Anthropic API key is set):
- answer accuracy: the answer contains every key fact (checked by string match, then read
  by a person; string matching alone is not enough for clinical content)
- citation accuracy: the answer cites at least one expected page
- answers withheld by the citation check
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .answer import NOT_FOUND, answer
from .retrieve import Retriever


def _has(text: str, fact: str) -> bool:
    squash = lambda s: "".join(s.lower().split())
    return squash(fact) in squash(text)


def run(retriever: Retriever, questions_path: str | Path, client=None, k: int = 5) -> tuple[list[dict], dict]:
    generate = client is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))
    rows = []
    for line in Path(questions_path).read_text().splitlines():
        if not line.strip():
            continue
        q = json.loads(line)
        hits = retriever.search(q["question"], k)
        res = answer(q["question"], retriever, k=k, client=client)
        refused = res["answer"].strip() == NOT_FOUND
        exp = set(q.get("expected_pages", []))
        retrieved = " ".join(p.text for p, _ in hits)
        row = {
            "question": q["question"], "in_scope": q["in_scope"], "expected_pages": sorted(exp),
            "retrieved_pages": [p.page for p, _ in hits],
            "retrieved_from_ocr": [p.page for p, _ in hits if p.source == "ocr"],
            "refused": refused, "source": res["source"],
            "unknown_terms": retriever.unknown_terms(q["question"]),
        }
        if q["in_scope"]:
            row["page_hit"] = bool(exp & {p.page for p, _ in hits})
            row["evidence_found"] = all(_has(retrieved, f) for f in q["key_facts"])
            if generate:
                row["facts_in_answer"] = all(_has(res["answer"], f) for f in q["key_facts"])
                row["cites_expected_page"] = bool(exp & set(res["pages"]))
        row["answer"] = res["answer"]
        if res.get("rejected_answer"):
            row["rejected_answer"] = res["rejected_answer"]
        rows.append(row)

    ins = [r for r in rows if r["in_scope"]]
    outs = [r for r in rows if not r["in_scope"]]
    rate = lambda xs, key: round(sum(bool(x.get(key)) for x in xs) / max(1, len(xs)), 3)
    summary = {
        "questions": len(rows), "in_scope": len(ins), "out_of_scope": len(outs),
        f"expected page in top {k}": rate(ins, "page_hit"),
        f"all key facts in top {k} passages": rate(ins, "evidence_found"),
        "in-scope questions wrongly refused": rate(ins, "refused"),
        "out-of-scope questions correctly refused": rate(outs, "refused"),
        "out-of-scope questions refused or flagged with an unknown-word warning": round(
            sum(r["refused"] or bool(r["unknown_terms"]) for r in outs) / max(1, len(outs)), 3),
        "in-scope questions given an unknown-word warning": round(
            sum(bool(r["unknown_terms"]) and not r["refused"] for r in ins) / max(1, len(ins)), 3),
    }
    if generate:
        summary["answers containing all key facts"] = rate(ins, "facts_in_answer")
        summary["answers citing an expected page"] = rate(ins, "cites_expected_page")
        summary["answers withheld by the citation check"] = round(
            sum(r["source"].startswith("answer withheld") for r in rows) / max(1, len(rows)), 3)
    else:
        summary["answer measures"] = "not run: set ANTHROPIC_API_KEY to generate and score answers"
    return rows, summary
