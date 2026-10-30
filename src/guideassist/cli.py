"""Command line use.

    python -m guideassist.cli index ../data/guidelines.pdf     # build data/passages.jsonl
    python -m guideassist.cli ask "What is the starting dose of metformin?"
    python -m guideassist.cli eval                              # score against eval/questions.jsonl
    python -m guideassist.cli eval heldout                      # score against eval/heldout.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .answer import answer
from .evaluate import run
from .ingest import load, load_pdf, save
from .retrieve import Retriever

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "data" / "passages.jsonl"


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "help"
    if cmd == "index":
        ps = load_pdf(argv[1])
        save(ps, INDEX)
        print(f"{len(ps)} passages from {len({p.page for p in ps})} pages -> {INDEX}")
    elif cmd == "ask":
        res = answer(" ".join(argv[1:]), Retriever(load(INDEX)))
        print(res["answer"]); print(f"\n(source: {res['source']}; pages: {res['pages']})")
    elif cmd == "eval":
        name = argv[1] if len(argv) > 1 else "questions"
        rows, summary = run(Retriever(load(INDEX)), ROOT / "eval" / f"{name}.jsonl")
        tag = "" if name == "questions" else f"_{name}"
        (ROOT / "eval" / f"results{tag}.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
        (ROOT / "eval" / f"summary{tag}.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
