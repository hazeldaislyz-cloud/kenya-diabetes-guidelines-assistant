"""Score the assistant against a hand-written question set (eval/questions.jsonl).

Each line: {"question": ..., "expected_pages": [12, 13], "key_facts": ["metformin", "500"],
            "in_scope": true}

Measures:
- retrieval hit rate: the right page is among the top 5 passages
- answer accuracy: the answer contains every key fact (checked by string match, then
  read by a person; string matching alone is not enough for clinical content)
- citation accuracy: the answer cites at least one expected page
- refusal: out-of-scope questions get the "not covered" answer
"""
from __future__ import annotations

import json
from pathlib import Path

from .answer import NOT_FOUND, answer
from .retrieve import Retriever


def run(retriever: Retriever, questions_path: str | Path, client=None) -> tuple[list[dict], dict]:
    rows = []
    for line in Path(questions_path).read_text().splitlines():
        if not line.strip():
            continue
        q = json.loads(line)
        hits = retriever.search(q["question"], 5)
        res = answer(q["question"], retriever, client=client)
        refused = res["answer"].strip() == NOT_FOUND
        exp = set(q.get("expected_pages", []))
        rows.append({
            "question": q["question"], "in_scope": q["in_scope"],
            "retrieval_hit": bool(exp & {p.page for p, _ in hits}) if q["in_scope"] else None,
            "facts_found": all(f.lower() in res["answer"].lower() for f in q.get("key_facts", [])) if q["in_scope"] else None,
            "cites_expected_page": bool(exp & set(res["pages"])) if q["in_scope"] else None,
            "refused": refused, "source": res["source"], "answer": res["answer"],
        })
    ins = [r for r in rows if r["in_scope"]]
    outs = [r for r in rows if not r["in_scope"]]
    rate = lambda xs, k: round(sum(bool(x[k]) for x in xs) / max(1, len(xs)), 3)
    summary = {
        "questions": len(rows), "in_scope": len(ins), "out_of_scope": len(outs),
        "retrieval hit rate (top 5)": rate(ins, "retrieval_hit"),
        "answers with all key facts": rate(ins, "facts_found"),
        "answers citing an expected page": rate(ins, "cites_expected_page"),
        "in-scope questions wrongly refused": rate(ins, "refused"),
        "out-of-scope questions correctly refused": rate(outs, "refused"),
    }
    return rows, summary
