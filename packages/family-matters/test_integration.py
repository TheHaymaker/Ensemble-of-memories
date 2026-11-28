"""Memory + embeddings + Ensemble together. Run: python3 test_integration.py
Uses the deterministic ConceptEmbedder so results are reproducible offline."""
import multiprocessing as mp
import os
import random
import shutil
import tempfile

from embeddings import ConceptEmbedder
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()


def d(name):
    p = os.path.join(TMP, name)
    shutil.rmtree(p, ignore_errors=True)
    return p


def test_paraphrase_revival_beats_keywords():
    fact = "the staging database password rotates on the first monday of each month"
    cue = "when do the preprod creds change?"
    out = {}
    for label, emb in (("keywords", None), ("embeddings", ConceptEmbedder())):
        s = MemoryStore(d(f"para_{label}"), emb)
        mid = s.remember(fact, 0.5)
        s.beat(30)
        hits = s.recall(cue, 0.95)
        out[label] = bool(hits and hits[0]["id"] == mid and hits[0]["how"] == "revived")
    assert out == {"keywords": False, "embeddings": True}, out
    return "cue sharing no words with the memory: keywords miss it, embeddings revive it"


def test_vectors_persist_and_embedder_is_locked_in():
    root = d("persist")
    s = MemoryStore(root, ConceptEmbedder())
    ids = [s.remember(t, 0.6) for t in ("deploys go out tuesday and thursday", "cafeteria closes early friday")]
    s2 = MemoryStore(root, ConceptEmbedder())                    # reopen
    hits = s2.recall("which days can we ship to production", 0.5)
    assert hits and hits[0]["id"] == ids[0]
    try:
        MemoryStore(root, None); raise AssertionError("should refuse")
    except ValueError as err:
        msg = str(err)
    return f"reopened store recalls by meaning; opening with another embedder is refused ({msg})"


def test_conductor_remembers_decisions_and_listen_shows_memory():
    ens = MdEnsemble(d("ens"), ["conductor", "a", "b", "c"])
    cond = Player(ens, "conductor", MemoryStore(d("cmem"), ConceptEmbedder()))
    a, b, c = (Player(ens, n) for n in "abc")
    cond.open_question("rotate-refresh-tokens")
    cond.open_question("database", ["postgres", "dynamo"])
    for p, ans in ((a, "yes"), (b, "yes"), (c, "no")):
        p.vote("rotate-refresh-tokens", ans, 0.8)
        p.vote("database", "postgres" if ans == "yes" else "dynamo", 0.7)
    r1 = cond.close_question("rotate-refresh-tokens")
    r2 = cond.close_question("database")
    heard = cond.listen()
    assert "remembered it as" in r1 and "remembered it as" in r2
    assert "memory: 2 active" in heard and "Decided 'rotate-refresh-tokens'" in heard
    for _ in range(40):
        cond.next_beat()
    assert "memory: 0 active, 2 repressed" in cond.listen()
    back = cond.recall("did we decide whether session tokens get renewed?", 0.95)
    assert "revived" in back and "rotate-refresh-tokens" in back, back
    return ("closing questions stored both decisions; listen() showed them, then they went dormant "
            "with the ensemble's beat; a strong paraphrased cue revived the right one")


def _worker(args):
    root, seed = args
    s = MemoryStore(root, ConceptEmbedder())
    rng = random.Random(seed)
    n = 0
    for i in range(30):
        if rng.random() < 0.6:
            s.remember(f"worker {seed} deploy note {i} tuesday release", 0.5); n += 1
        else:
            s.recall("which days do we ship", 0.6)
    return n


def test_concurrent_embedding_writers():
    root = d("conc")
    MemoryStore(root, ConceptEmbedder())
    with mp.Pool(8) as pool:
        made = sum(pool.map(_worker, [(root, i) for i in range(8)]))
    s = MemoryStore(root, ConceptEmbedder())
    rows = s.rows()
    import numpy as np
    vi = sorted(s._load()["m"][r["id"]]["vi"] for r in rows)
    assert len(rows) == made and len(set(vi)) == made and len(s._vectors()) >= made
    return f"8 processes: {made} memories, every one has its own vector row"


def test_adk_tool_schemas():
    from google.adk.tools import FunctionTool
    ens = MdEnsemble(d("adk"), ["conductor", "a"])
    cond = Player(ens, "conductor", MemoryStore(d("adkmem"), ConceptEmbedder()))
    names = [FunctionTool(t)._get_declaration().name for t in cond.tools()]
    assert {"remember", "recall", "use_memory", "close_question", "listen"} <= set(names)
    return f"Google ADK builds all {len(names)} conductor tools: {', '.join(names)}"


def test_calibration_runs():
    from calibrate import calibrate
    k, c = calibrate("keywords"), calibrate("concept")
    assert c["auc"] > k["auc"]
    return f"calibrate.py: keywords AUC {k['auc']}, test embedder AUC {c['auc']}"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            print(f"PASS {t.__name__}\n      {t()}")
        except Exception as err:
            failed += 1
            print(f"FAIL {t.__name__}: {type(err).__name__}: {err}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
