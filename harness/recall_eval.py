#!/usr/bin/env python3
"""How well does recall find what real sessions were looking for?

    .lab/venv/bin/python harness/recall_eval.py [harness/data/recall-saga1.json]
    ENSEMBLE_EMBEDDER=hybrid .lab/venv/bin/python harness/recall_eval.py      (needs model2vec)

Each query is a cue Claude actually sent to `ens recall` in a run, with the memories that existed then
and, labelled by hand, the ones that answer it. Rebuilds each store with the current Ensemble code and
reports: answerable cues where a right memory came back, where it came back first, and wrong memories
returned (counting weak matches)."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "packages", "ensemble"))
from memory import MemoryStore  # noqa: E402


def make_embedder():
    kind = os.environ.get("ENSEMBLE_EMBEDDER", "keywords")
    if kind == "keywords":
        return None
    import embeddings as E
    return {"model2vec": E.Model2VecEmbedder, "hybrid": E.HybridEmbedder}[kind]()


def evaluate(path, emb=None):
    qs = json.load(open(path))["queries"]
    found = first = wrong = answerable = 0
    rows = []
    for q in qs:
        s = MemoryStore(tempfile.mkdtemp(), emb)
        ids = {}
        for old, m in q["memories"].items():
            ids[s.remember(m["text"], 0.5, m.get("src") or "")] = old
        hits = [(ids[h["id"]], h["how"]) for h in s.recall(q["cue"], 0.5)]
        got = [h for h, _ in hits]
        rel = set(q["relevant"])
        if rel:
            answerable += 1
            found += bool(rel & set(got))
            first += bool(got and got[0] in rel)
        wrong += len([h for h in got if h not in rel])
        rows.append((q["cue"], sorted(rel), hits))
    return {"answerable": answerable, "found": found, "first": first, "wrong": wrong, "rows": rows}


if __name__ == "__main__":
    r = evaluate(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "data", "recall-saga1.json"),
                 make_embedder())
    for cue, rel, hits in r["rows"]:
        mark = "ok " if (set(rel) & {h for h, _ in hits}) else ("-- " if rel else "   ")
        print(f"{mark}{cue[:60]:60} want {rel or '-'} got {hits}")
    print(f"\nfound {r['found']}/{r['answerable']}, first {r['first']}/{r['answerable']}, wrong returned {r['wrong']}")
