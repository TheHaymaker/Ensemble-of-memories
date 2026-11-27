"""Sleep, daydreams, tensions and vacating. Run: python3 test_sleep.py [out_dir]  (writes sleep.png)"""
import gzip
import json
import os
import random
import shutil
import sys
import tempfile
import threading
import time

from dreams import HeuristicJudge
from embeddings import ConceptEmbedder
from mdensemble import MdEnsemble
from memory import FRUITLESS_K, MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()


def store(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return MemoryStore(root, ConceptEmbedder())


def row(s, mid):
    return next((r for r in s.rows() if r["id"] == mid), None)


def judge(s, **kw):
    return HeuristicJudge(low=s.recall_min, **kw)


def test_a_night_shifts_from_consolidation_to_association():
    s = store("night")
    old_deploy = s.remember("deploys go out tuesday and thursday", 0.6, "ops")
    old_db = s.remember("the staging database password rotates monthly", 0.6, "ops")
    for i in range(6):
        s.remember(f"printer on floor {i} jams again", 0.4, "misc")
    s.beat(5)
    new_deploy = s.remember("deploys no longer go out on thursday", 0.6, "ops")
    new_db = s.remember("staging db password now rotates weekly instead", 0.6, "ops")
    night = s.sleep(judge(s), cycles=4, pairs_per_cycle=10, rng=random.Random(1))
    split = [(c["consolidate"], c["associate"]) for c in night["cycles"]]
    assert split == [(8, 2), (6, 4), (4, 6), (2, 8)], split
    assert night["counts"].get("subtract") == 1 and night["counts"].get("substitute") == 1, night["report"]
    idx = s._load()
    assert idx["m"][old_deploy]["superseded_by"] == new_deploy and idx["m"][old_db]["superseded_by"] == new_db
    assert s.sleep_pressure() == 0
    return f"cycles (consolidate, associate) = {split}; {night['report']}"


def test_sleep_pressure_decides_when_to_sleep():
    ens = MdEnsemble(os.path.join(TMP, "press_ens"), ["conductor"])
    shutil.rmtree(ens.root); ens = MdEnsemble(os.path.join(TMP, "press_ens"), ["conductor"])
    p = Player(ens, "conductor", store("press"), sleep_at=5)
    for i in range(4):
        p.remember(f"refresh tokens rotate note {i}", 0.5)
    quiet = p.listen()
    p.remember("session tokens rotate each use", 0.5)
    busy = p.listen()
    assert "slept at" not in quiet and "slept at" in busy and p.memory.sleep_pressure() == 0
    return "4 new memories: no sleep; the 5th made sleep due and listen() slept; pressure reset to 0"


def test_daydreams_propose_but_never_destroy():
    s = store("day")
    old = s.remember("deploys go out tuesday and thursday", 0.6, "ops")
    s.beat(30)                                               # old one is dormant now
    new = s.remember("deploys no longer go out on thursday", 0.6, "ops")
    before = s._load()["m"][old]["s"]
    ev = s.daydream(judge(s), "which days do we deploy", samples=4, rng=random.Random(2))
    assert ev["proposed"] >= 1 and s._load()["m"][old]["s"] == before and "superseded_by" not in s._load()["m"][old]
    night = s.sleep(judge(s), cycles=2, pairs_per_cycle=6, rng=random.Random(3))
    assert s._load()["m"][old]["superseded_by"] == new, night["report"]
    return "daydream around 'which days do we deploy' proposed the contradiction and changed nothing; the next sleep applied it"


def test_dream_ideas_cannot_overrule_waking_lessons():
    s = store("trust")
    lesson = s.remember("staging db password rotates monthly", 0.6, "ops")
    s.beat(5)
    idea = s.remember("staging db password now rotates weekly instead", 0.6, "dream")    # dream-made
    night1 = s.sleep(judge(s), cycles=2, pairs_per_cycle=6, rng=random.Random(4))
    m = s._load()["m"]
    tensions = s.open_tensions()
    assert "superseded_by" not in m[lesson] and len(tensions) == 1 and night1["counts"].get("downgraded") == 1
    s.use(idea); s.use(idea)                                 # agents relied on it while awake
    s.remember("unrelated new note about printers jams", 0.3, "misc")
    s.sleep(judge(s), cycles=2, pairs_per_cycle=6, rng=random.Random(5))
    m = s._load()["m"]
    assert m[lesson].get("superseded_by") == idea and not s.open_tensions()
    return ("dream-made 'weekly' could not replace the waking 'monthly' lesson: held as a tension; after agents "
            "used it twice, the next sleep let it replace the lesson and closed the tension")


def test_valuable_contradictions_are_qualified_not_discarded():
    s = store("qualify")
    a = s.remember("deploy small changes daily", 0.6, "eng")
    s.beat(2)
    b = s.remember("deploy large batched releases only before audits", 0.6, "compliance")
    sa, sb = row(s, a)["strength"], row(s, b)["strength"]
    night = s.sleep(judge(s, high=0.6), cycles=2, pairs_per_cycle=6, rng=random.Random(6))
    m = s._load()["m"]
    q = m[a].get("qualified_by")
    assert night["counts"].get("qualify") == 1 and q and q == m[b].get("qualified_by"), night["report"]
    assert row(s, a)["strength"] >= sa * 0.99 and row(s, b)["strength"] >= sb * 0.99
    return f"both kept at full strength and linked to: '{s.read(q)}'"


def test_unclear_conflicts_go_to_an_ensemble_vote():
    ens = MdEnsemble(os.path.join(TMP, "vote_ens"), ["conductor", "x", "y", "z"])
    shutil.rmtree(ens.root); ens = MdEnsemble(os.path.join(TMP, "vote_ens"), ["conductor", "x", "y", "z"])
    cond = Player(ens, "conductor", store("vote_mem"), sleep_at=2)
    first = cond.memory.remember("refresh tokens rotate on every use", 0.6, "auth team")
    second = cond.memory.remember("refresh tokens do not rotate on every use", 0.6, "mobile team")
    heard = cond.listen()                                    # sleeps, finds the tension, raises it
    q = next(l.split()[1] for l in heard.splitlines() if l.startswith("raised "))
    for name, ans in (("x", "yes"), ("y", "yes"), ("z", "no")):
        Player(ens, name).vote(q, ans, 0.8)
    result = cond.close_question(q)
    m = cond.memory._load()["m"]
    assert "tension resolved (a)" in result and m[second].get("superseded_by") == first
    text_line = next(l for l in heard.splitlines() if l.strip().startswith("(Does"))  # the vote's question text
    return f"sleep found the conflict and raised {q}: {text_line.strip()[:90]}...; vote yes -> first kept, second superseded"


def test_vacating_needs_evidence_and_archives():
    s = store("vacate")
    lonely = s.remember("printer on floor three jams", 0.4, "misc")
    valued = s.remember("cafeteria lunch closes early friday", 0.4, "misc")
    for _ in range(6):
        s.beat(4); s.use(valued)                              # used 6 times: longer grace
    s.remember("refresh tokens rotate on every use", 0.5, "auth")
    s.beat(80)                                                # both printer notes dormant
    nights = 0
    while row(s, lonely) is not None and nights < 20:
        s.remember(f"session tokens rotate note {nights}", 0.5, "auth")
        s.sleep(judge(s), cycles=4, pairs_per_cycle=6, rng=random.Random(nights)); s.beat(5); nights += 1
    assert row(s, lonely) is None and row(s, valued) is not None, nights
    with gzip.open(os.path.join(s.root, "archive.jsonl.gz"), "rt") as f:
        archived = [json.loads(l) for l in f]
    assert any(r["id"] == lonely for r in archived)
    found = s.search_archive("printer jams on floor three")
    new = s.restore(found[0]["id"])
    hit = s.recall("printer floor three jam", 0.9)
    assert found[0]["id"] == lonely and hit and hit[0]["id"] in (new, valued)
    return (f"after {nights} nights the unused dormant memory had {FRUITLESS_K}+ fruitless dream exposures and was archived; "
            f"the one used 6 times is still waiting out its longer grace; archive search + restore brought it back")


def test_every_dormant_memory_gets_its_turn():
    s = store("expose")
    for i in range(120):
        s.remember(f"note{i:03d} about vendor{i * 7 % 97:02d} topic{i * 13 % 89:02d}", 0.3, "misc")
    s.beat(40)
    for n in range(8):
        s.remember(f"tokens rotate note {n}", 0.5, "auth")
        s.sleep(judge(s), cycles=4, pairs_per_cycle=20, rng=random.Random(n))
    m = s._load()["m"]
    dormant = [k for k, v in m.items() if v["dormant"]]
    never = [k for k in dormant if m[k].get("last_sampled") is None]
    assert not never, len(never)
    return f"after 8 nights all {len(dormant)} dormant memories had been replayed at least once (oldest-unsampled first)"


def test_slow_judge_does_not_block_other_agents():
    s = store("lock")
    for i in range(10):
        s.remember(f"deploys go out tuesday note {i}", 0.5, f"src{i}")

    def slow(a, b, sim):
        time.sleep(0.05)
        return None
    t = threading.Thread(target=lambda: s.sleep(slow, cycles=2, pairs_per_cycle=20))
    t.start(); time.sleep(0.3)
    t0 = time.time(); s.remember("written during the night", 0.5); dt = time.time() - t0
    t.join()
    assert dt < 0.5, dt
    return f"another agent wrote a memory in {dt * 1000:.0f} ms while a ~2 s night was being judged"


def long_run(out, beats=600):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    topics = [g.split() for g in ConceptEmbedder.GROUPS]
    s = store("long")
    rng = random.Random(4)
    j = judge(s)
    held, active, kb, arch, ops, nights = [], [], [], [], {}, []
    for beat in range(beats):
        for _ in range(3):
            t1, t2 = rng.sample(topics, 2)                      # mixed topics: fewer near-duplicates
            words = [rng.choice(t1), rng.choice(t2)] + rng.sample(["note", "update", "fact", "item", "detail", "point"], 3)
            s.remember(" ".join(words) + f" {rng.randint(0, 999)}", rng.uniform(0.2, 0.7), rng.choice("abc"))
        if beat % 3 == 0:
            s.daydream(j, " ".join(rng.choice(topics)[:2]), samples=4, rng=rng)
        s.beat()
        if s.sleep_due(30):
            night = s.sleep(j, cycles=4, pairs_per_cycle=20, rng=rng)
            nights.append(beat)
            for k, v in night["counts"].items():
                ops[k] = ops.get(k, 0) + v
        st = s.stats()
        held.append(st["short"] + st["intermediate"] + st["long"] + st["dormant"])
        active.append(st["short"] + st["intermediate"] + st["long"])
        ap = os.path.join(s.root, "archive.jsonl.gz")
        arch.append(os.path.getsize(ap) / 1024 if os.path.exists(ap) else 0)
        kb.append(st["bytes"] / 1024 - arch[-1])
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.3))
    ax[0].plot(held, color="#2471a3", label="memories held (all tiers)")
    ax[0].plot(active, color="#2471a3", ls=":", label="active")
    for nb in nights:
        ax[0].axvline(nb, color="#ddd", lw=0.5, zorder=0)
    ax[0].set_title("3 new memories per beat; sleep when 30 build up (grey lines)", fontsize=10)
    ax[1].plot(kb, color="#2471a3", label="working memory on disk")
    ax[1].plot(arch, color="#7f8c8d", label="archive (compressed cold storage)")
    ax[1].set_title("Storage (KB)", fontsize=10)
    for a in ax:
        a.set_xlabel("beat"); a.legend(fontsize=7)
    fig.tight_layout()
    path = os.path.join(out, "sleep.png")
    fig.savefig(path, dpi=150)
    return path, held[-1], max(held[400:]) - min(held[400:]), round(kb[-1]), round(arch[-1]), len(nights), ops


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
    path, held, spread, kb, arch, n, ops = long_run(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(f"\nlong run -> {path}: {n} nights; at beat 600 holding {held} memories (range over last 200 beats: {spread}); "
          f"working {kb} KB, archive {arch} KB; outcomes {ops}")
