"""Overturned decisions are marked replaced, and a replaced memory is never briefed, recalled or
handed down. Run: python3 test_replace.py

The recall A/B (harness/eval, run ab1) found the gap: recipe-core's first display rule was overturned
by the baker one session later, nothing marked the old memory, it had 2 uses against 0, and a child
project was born hearing the outdated rule as a saying."""
import os
import shutil
import tempfile

from family import Family
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()
OLD = "scaled quantities snap to fractions only when exact, else print 2 decimals, never approximate"
NEW = "baker's rule: always print the nearest kitchen fraction down to eighths, and 'a pinch' below 1/8 tsp"


def fresh(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return root


def player(root, member, f=None):
    ens = MdEnsemble(os.path.join(root, member, "state"), ["conductor"])
    return Player(ens, "conductor", MemoryStore(os.path.join(root, member, "memory")), family=f, family_member=member)


def test_remember_replaces_marks_the_old_memory():
    p = player(fresh("replaces"), "recipes")
    old = p.memory.remember(OLD, 0.7)
    p.memory.use(old); p.memory.use(old)
    out = p.remember(NEW, 0.8, replaces=old)
    new = out.split()[1].rstrip(",")
    row = next(r for r in p.memory.rows() if r["id"] == old)
    assert out == f"stored {new}, replacing {old}" and row["superseded_by"] == new, (out, row)
    assert old not in p.memory.summary() and new in p.memory.summary(), p.memory.summary()
    assert old not in p.listen()
    return f"{old} marked replaced by {new}; the briefing (summary, listen) shows only {new}"


def test_recall_answers_with_the_replacement():
    p = player(fresh("recall"), "recipes")
    old = p.memory.remember("deploys go out on Fridays after the standup", 0.7)
    new = p.memory.remember("no more releases at the end of the week: ship Tuesday mornings", 0.7, replaces=[old])
    hits = p.memory.recall("when do deploys go out on Fridays", 0.6)
    assert [h["id"] for h in hits] == [new] and hits[0]["how"] == "replacement", hits
    text = p.recall("when do deploys go out on Fridays", 0.6)
    assert f"current answer, replaces {old}" in text and "standup" not in text, text
    return "a cue in the old memory's words gets the memory that replaced it, never the stale text"


def test_a_chain_of_replacements_ends_at_the_current_answer():
    s = MemoryStore(fresh("chain"))
    a = s.remember("the cup is 236.6 ml", 0.6)
    b = s.remember("the cup is 240 ml for nutrition labels", 0.6, replaces=[a])
    c = s.remember("the cup is 250 ml, metric cup, from now on", 0.6, replaces=[b])
    hits = s.recall("the cup is 236.6 ml", 0.6)
    assert hits and hits[0]["id"] == c and a not in [h["id"] for h in hits] and b not in [h["id"] for h in hits], hits
    s.use(b); s.use(b)
    idx = s._load()
    assert s.standing(idx, c) == idx["m"][c]["uses"] + 2           # reliance on the topic moves to its answer
    assert s.replace(a, c)["superseded_by"] == c
    return f"{a} -> {b} -> {c}: recall in {a}'s words answers with {c}"


def test_using_a_replaced_memory_does_not_revive_it():
    p = player(fresh("use"), "recipes")
    old = p.memory.remember(OLD, 0.7)
    new = p.memory.remember(NEW, 0.8, replaces=[old])
    before = next(r for r in p.memory.rows() if r["id"] == old)["uses"]
    out = p.use_memory(old)
    after = next(r for r in p.memory.rows() if r["id"] == old)["uses"]
    assert f"replaced by {new}" in out and before == after, out
    return "use-memory on an overturned memory points to its replacement and changes nothing"


def test_remember_points_out_a_close_memory_to_replace_later():
    p = player(fresh("near"), "recipes")
    old = p.memory.remember("the staging database password rotates monthly", 0.6)
    p.memory.remember("pinch is a count unit and never converts", 0.5)
    out = p.remember("the staging database password now rotates weekly", 0.6)
    new = out.split()[1].rstrip(".")
    assert f"Close to: {old}" in out and f"fam revise-history OLD_ID {new}" in out and "pinch" not in out, out
    assert p.replace_memory(old, new) == f"{old} is now replaced by {new}"
    assert p.replace_memory(new, old).startswith("error")            # no cycles
    return "a new memory close to an old one asks whether it overturns it; replace-memory does it after the fact"


def test_replacing_a_lesson_demotes_it_and_settles_its_tension():
    s = MemoryStore(fresh("lesson"))
    old = s.remember("integration tests always hit the real staging database", 0.7)
    other = s.remember("integration tests use the in-memory fake database", 0.7)
    with s._txn() as idx:
        idx["m"][old]["lesson"] = True
        idx.setdefault("tensions", {})["m09999"] = {"a": old, "b": other, "status": "open", "raised": False}
    new = s.remember("integration tests use a throwaway container database, not staging", 0.7, replaces=[old])
    m = s._load()
    assert not m["m"][old].get("lesson") and m["tensions"]["m09999"]["status"] == f"resolved:replaced:{new}"
    assert old not in [l["id"] for l in s.lessons()]
    return "an overturned lesson stops being a lesson, and an open tension about it is settled"


def test_a_child_is_told_the_current_rule_not_the_overturned_one():
    """The ab1 case: the old rule had 2 uses, the new one none."""
    root = fresh("child")
    f = Family(os.path.join(root, "family"))
    f.birth("recipe-core", os.path.join(root, "recipe-core", "memory"))
    parent = player(root, "recipe-core", f)
    old = parent.memory.remember(OLD, 0.7)
    parent.memory.use(old); parent.memory.use(old)
    for i in range(4):                                     # other everyday knowledge, relied on once each
        parent.memory.use(parent.memory.remember(f"recipe-core convention number {i}: keep module {i} small", 0.6))
    parent.remember(NEW, 0.8, replaces=old)
    f.birth("meal-planner", os.path.join(root, "meal-planner", "memory"), ["recipe-core"])
    heard = player(root, "meal-planner", f).listen()
    assert "a pinch" in heard and "2 decimals" not in heard, heard
    texts = [s["text"] for s in f._load()["sayings"].values()]
    assert NEW in texts and OLD not in texts, texts
    return "the replacement takes over the old rule's 2 uses, so the child is told the baker's rule"


def test_a_saying_told_before_the_overturn_stops_being_heard():
    root = fresh("later")
    f = Family(os.path.join(root, "family"))
    f.birth("recipe-core", os.path.join(root, "recipe-core", "memory"))
    parent = player(root, "recipe-core", f)
    old = parent.memory.remember(OLD, 0.7)
    parent.memory.use(old)
    f.birth("meal-planner", os.path.join(root, "meal-planner", "memory"), ["recipe-core"])
    child = player(root, "meal-planner", f)
    assert "2 decimals" in child.listen()
    parent.remember(NEW, 0.8, replaces=old)
    heard = child.listen()
    advice = child.recall("how should quantities print, fractions or decimals", 0.5)
    assert "2 decimals" not in heard and "2 decimals" not in advice, (heard, advice)
    f.birth("shopping", os.path.join(root, "shopping", "memory"), ["recipe-core"])
    texts = [s["text"] for s in f._load()["sayings"].values()]
    assert NEW in texts, texts                 # the stale saying doesn't block telling the new rule
    return "once the parent replaces it, the old saying leaves the child's briefing, recall and later births"


def test_the_fam_command_takes_replaces():
    import subprocess
    import sys
    h = tempfile.mkdtemp()
    env = dict(os.environ, FAM_HOME=h, FAM_PROJECT="proj", PYTHONWARNINGS="ignore")
    ens = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fam.py")]
    run = lambda *a: subprocess.run(ens + list(a), capture_output=True, text=True, env=env, timeout=60).stdout.strip()
    assert run("never-forget", OLD) == "stored m00001"
    assert run("never-forget", NEW, "--replaces", "m00001") == "stored m00002, replacing m00001"
    assert "m00001" not in run("gossip") and "--replaces" in run("never-forget", "--help")
    assert run("revise-history", "m00002", "m00001").startswith("error")
    return "fam never-forget --replaces and fam revise-history work from the command line"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    ok = 0
    for t in tests:
        try:
            print(f"PASS {t.__name__}\n      {t()}"); ok += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{ok}/{len(tests)} passed")
