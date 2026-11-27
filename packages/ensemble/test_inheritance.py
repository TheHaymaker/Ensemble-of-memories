"""Lessons at project scale, and what a child or a new generation actually hears.
Run: python3 test_inheritance.py

These are the gaps a 30-session run with real Claude sessions found (harness/scenarios/family-saga.json):
no memory ever became a lesson, so reunions had nothing to tell, and children and new generations
started with nothing because family advice only matched open questions."""
import os
import random
import shutil
import tempfile

from embeddings import ConceptEmbedder
from family import Family
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()


def fresh(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return root


def agree(a, b, sim):
    """A judge that, like Claude in the real runs, reinforces two notes that say the same thing."""
    return {"op": "reinforce", "score": sim} if sim >= 0.5 else None


def session_life(s, text, twin, uses, nights, rng):
    """One beat per session; the memory is relied on in `uses` sessions, three sessions apart; a night
    after every second session, as with ENSEMBLE_SLEEP_AT reached by a few sessions' worth of notes."""
    mid = s.remember(text, 0.6, "waking")
    tid = s.remember(twin, 0.6, "waking")          # a related note, also relied on, for a dream to link
    for i in range(max(uses, nights) * 3):
        s.beat(1)
        if i % 3 == 0 and uses:
            s.use(mid); s.use(tid); uses -= 1
        if i % 3 == 2 and nights:
            s.remember(f"unrelated note {rng.randint(0, 999)}", 0.3, "misc")
            s.sleep(agree, cycles=2, pairs_per_cycle=6, rng=rng); nights -= 1
    return mid


def test_a_relied_on_memory_becomes_a_lesson_within_a_few_weeks():
    s = MemoryStore(fresh("weeks"), ConceptEmbedder())
    mid = session_life(s, "staging database credentials rotate every week",
                       "rotate the staging database password weekly", uses=4, nights=4, rng=random.Random(1))
    assert any(l["id"] == mid for l in s.lessons()), s.rows()
    return "4 uses three sessions apart, a dream reinforcement and 2 nights consolidated: a lesson"


def test_a_memory_used_once_does_not_harden():
    s = MemoryStore(fresh("once"), ConceptEmbedder())
    mid = session_life(s, "staging database credentials rotate every week",
                       "rotate the staging database password weekly", uses=1, nights=6, rng=random.Random(2))
    assert not any(l["id"] == mid for l in s.lessons())
    return "one use and many nights: still not a lesson"


def family(name):
    root = fresh(name)
    return root, Family(os.path.join(root, "family"))


def player(root, f, member):
    ens = MdEnsemble(os.path.join(root, member, "state"), ["conductor"])
    p = Player(ens, "conductor", MemoryStore(os.path.join(root, member, "memory")), family=f, family_member=member)
    return p


def test_a_child_hears_its_parent_without_open_questions():
    root, f = family("child")
    f.birth("recipes", os.path.join(root, "recipes", "memory"))
    parent = player(root, f, "recipes")
    keep = parent.memory.remember("quantities stay floats; format_qty snaps to kitchen fractions at display", 0.7)
    parent.memory.remember("pinch is a count unit and never converts", 0.5)
    parent.memory.use(keep)
    f.birth("planner", os.path.join(root, "planner", "memory"), ["recipes"])
    child = player(root, f, "planner")
    heard = child.listen()
    assert "format_qty snaps to kitchen fractions" in heard and "your parent, advice only" in heard, heard
    assert "family saying" in child.recall("how should the shopping list format quantities", 0.5)
    return "listen shows the parent's most relied-on memory as a saying; recall finds it by the task's words"


def test_a_new_generation_hears_its_heirlooms():
    root, f = family("generation")
    f.birth("recipes", os.path.join(root, "recipes", "memory"))
    p = player(root, f, "recipes")
    mid = p.memory.remember("the US cup stays 236.6 ml because densities are calibrated to it", 0.7)
    p.memory.use(mid)
    out = f.milestone("recipes", os.path.join(root, "recipes@2", "memory"), "v2")
    heir = player(root, f, out["name"])
    heard = heir.listen()
    assert "family heirloom" in heard and "236.6 ml" in heard, heard
    hid = next(h for h in f._load()["heirlooms"])
    assert heir.adopt_saying(hid).startswith("adopted as m")             # heirlooms can be taken in too
    assert f._load()["sayings"] == {} or all(s.get("told") != "birth" for s in f._load()["sayings"].values())
    return "recipes@2 starts by hearing recipes' heirlooms, not an empty memory"


def test_reunion_tells_lessons_as_sayings():
    root, f = family("reunion")
    f.birth("ops", os.path.join(root, "ops", "memory"))
    s = f.store("ops")
    session_life(s, "staging database credentials rotate every week",
                 "rotate the staging database password weekly", uses=4, nights=4, rng=random.Random(1))
    assert s.lessons()
    before = len(f._load()["sayings"])
    out = f.reunion()
    assert out["told"] >= 1 and len(f._load()["sayings"]) > before
    return f"a lesson from session-scale use reached the family at a reunion ({out['told']} told)"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    ok = 0
    for t in tests:
        try:
            print(f"PASS {t.__name__}\n      {t()}"); ok += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{ok}/{len(tests)} passed")
