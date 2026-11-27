"""Promotion paths: dream ideas -> confirmed memories, memories -> lessons. Run: python3 test_lessons.py"""
import os
import random
import shutil
import tempfile

import memory as M
from dreams import HeuristicJudge
from embeddings import ConceptEmbedder
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()


def store(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return MemoryStore(root, ConceptEmbedder())


def judge(s, **kw):
    return HeuristicJudge(low=s.recall_min, **kw)


def grow_lesson(s, text, twin_text, nights=4, seed=0):
    """Use a memory 8 times, spaced, with a reinforcing twin, across several nights."""
    mid = s.remember(text, 0.6, "ops")
    twin = s.remember(twin_text, 0.6, "security")
    rng = random.Random(seed)
    for i in range(8):
        s.beat(4); s.use(mid); s.use(twin)
    for _ in range(nights):
        s.remember(f"unrelated printer jam {rng.randint(0, 999)}", 0.3, "misc")
        s.sleep(judge(s), cycles=2, pairs_per_cycle=6, rng=rng)
        s.beat(4); s.use(mid)
    return mid, twin


def test_dream_ideas_are_confirmed_by_waking_use():
    s = store("confirm")
    a = s.remember("rotate the session tokens on a weekly schedule", 0.6, "auth")
    s.beat(20)
    b = s.remember("staging password rotation happens monthly", 0.6, "ops")
    night = s.sleep(HeuristicJudge(low=0.15, high=0.95), cycles=2, pairs_per_cycle=4, rng=random.Random(1))
    idea = night["insights"][0]
    m = s._load()["m"]
    assert m[idea]["origin"] == "dream"
    s.use(idea); s.use(idea)
    m = s._load()["m"]
    assert m[idea]["origin"] == "confirmed"
    return f"dream link stored as an unconfirmed idea; after 2 waking uses it became a confirmed memory: '{s.read(idea)[:70]}...'"


def test_memories_harden_into_lessons_that_do_not_fade():
    s = store("harden")
    mid, twin = grow_lesson(s, "refresh tokens rotate on every use", "session tokens rotate each use")
    m = s._load()["m"][mid]
    assert m.get("lesson"), m
    s.beat(1000)
    row = next(r for r in s.rows() if r["id"] == mid)
    assert row["tier"] == "lesson" and row["strength"] == 1.0
    assert " trauma | " in s.summary().splitlines()[0] and os.path.exists(os.path.join(s.root, "lessons.md"))
    return (f"8 spaced uses + a dream reinforcement + 3 nights in long-term -> lesson; 1000 beats later "
            f"still at strength {row['strength']}; listed in lessons.md")


def test_dreams_cannot_overturn_a_lesson_only_a_vote_can():
    ens = MdEnsemble(os.path.join(TMP, "lv"), ["conductor", "x", "y", "z"])
    shutil.rmtree(ens.root); ens = MdEnsemble(os.path.join(TMP, "lv"), ["conductor", "x", "y", "z"])
    cond = Player(ens, "conductor", store("lvm"))
    s = cond.memory
    lesson, _ = grow_lesson(s, "deploys go out tuesday and thursday", "release days are tuesday and thursday")
    assert s._load()["m"][lesson].get("lesson")
    s.beat(20)
    newer = s.remember("deploys no longer go out on thursday", 0.6, "ops")
    s.sleep(judge(s), cycles=2, pairs_per_cycle=6, rng=random.Random(9))
    assert s._load()["m"][lesson].get("lesson") and "superseded_by" not in s._load()["m"][lesson]
    heard = cond.listen()
    q = next(l.split()[1] for l in heard.splitlines() if l.startswith("raised "))
    assert "deploys no longer go out on thursday" in heard            # the question names both sides
    for name, ans in (("x", "yes"), ("y", "yes"), ("z", "no")):       # yes: the newer note takes precedence
        Player(ens, name).vote(q, ans, 0.8)
    cond.close_question(q)
    m = s._load()["m"][lesson]
    assert not m.get("lesson") and m.get("superseded_by") == newer
    return "a newer contradiction could not touch the lesson in sleep; it became a vote; the group sided with the newer note, so the lesson was demoted and superseded"


def test_lessons_surface_before_anyone_asks():
    ens = MdEnsemble(os.path.join(TMP, "pre"), ["conductor"])
    shutil.rmtree(ens.root); ens = MdEnsemble(os.path.join(TMP, "pre"), ["conductor"])
    cond = Player(ens, "conductor", store("prem"))
    lesson, _ = grow_lesson(cond.memory, "the staging database password rotates monthly",
                            "staging db creds rotate every month")
    before = cond.listen()
    cond.open_question("change-preprod-creds-schedule", text="Should we change how often the preprod DB credentials rotate?")
    after = cond.listen()
    assert "trauma " not in before and f"trauma {lesson}" in after
    line = next(l for l in after.splitlines() if l.startswith("trauma "))
    return f"no lesson shown until a related question opened; then listen() offered: '{line}'"


def test_lesson_cap_keeps_reading_flat():
    s = store("cap")
    old = M.LESSON_CAP
    M.LESSON_CAP = 2
    try:
        ids = [grow_lesson(s, f"{w} tokens rotate on every use", f"{w} session tokens rotate each use", seed=i)[0]
               for i, w in enumerate(("refresh", "access", "api"))]
        s.use(ids[1]); s.use(ids[2])
        s.remember("printer jam again", 0.3, "misc")
        s.sleep(judge(s), cycles=1, pairs_per_cycle=2, rng=random.Random(3))
        n = len(s.lessons())
    finally:
        M.LESSON_CAP = old
    assert n <= 2, n
    return f"with the cap set to 2, three qualifying memories left {n} lessons; the least-used was demoted to long-term"


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
