"""Generations within a project, and kinship. Run: python3 test_generations.py"""
import os
import random
import shutil
import tempfile

from dreams import HeuristicJudge
from family import AGE_NIGHTS, Family
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()


def fresh(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return root


def setup(name="widget"):
    root = fresh(name + "_fam")
    f = Family(root)
    f.birth(name, os.path.join(root, name))
    return f, root


def lesson(s, text, twin, nights=4):
    a, b = s.remember(text, 0.6, "ops"), s.remember(twin, 0.6, "ops")
    for _ in range(8):
        s.beat(4); s.use(a); s.use(b)
    for n in range(nights):
        s.remember(f"note {n} printer jam", 0.3, "ops")
        s.sleep(HeuristicJudge(low=s.recall_min), cycles=2, pairs_per_cycle=6, rng=random.Random(n))
        s.beat(4); s.use(a)
    return a


def conductor(f, name):
    ens = MdEnsemble(fresh(name.replace("@", "_") + "_ens"), [name])
    return Player(ens, name, f.store(name), family=f)


def test_drift_is_suggested_and_waits_for_approval():
    f, root = setup()
    s = f.store("widget")
    with s._txn() as idx:
        idx["overturned"] = 4                          # four pieces of knowledge overturned recently
    s.remember("the api returns json", 0.5, "ops"); s.remember("auth uses sessions", 0.5, "ops")
    heard = conductor(f, "widget").listen()
    line = next(l for l in heard.splitlines() if l.startswith("suggest:"))
    assert "drift" in line and f._load()["members"]["widget"]["status"] == "living"
    return f"conductor: '{line}'; nothing changed until approval"


def test_declining_snoozes_the_suggestion():
    f, root = setup("snooze")
    s = f.store("snooze")
    s.remember("we launched the public beta today", 0.6, "ops")
    assert f.suggest("snooze")
    f.decline("snooze")
    assert f.suggest("snooze") is None
    return "a launch note was flagged as a possible milestone; declined, it stays quiet (and that note is not flagged again)"


def test_approval_starts_a_new_generation():
    f, root = setup("chat")
    s = f.store("chat")
    lesson(s, "rotate shared credentials on a fixed schedule", "shared credentials rotate on schedule")
    used = s.remember("the widget loads after the page font", 0.6, "ops")
    for _ in range(5):
        s.beat(4); s.use(used)
    f.mark("chat", "leaked credentials", 1.0)
    with s._txn() as idx:
        idx["overturned"] = 5
    f.suggest("chat")
    out = f.approve("chat", os.path.join(root, "chat2"))
    fam = f._load()
    child = out["name"]
    assert child == "chat@2" and fam["members"]["chat"]["status"] == "retired"
    assert fam["members"][child]["gen"] == 2 and out["heirlooms"] >= 1
    assert len(f.store(child)._load()["m"]) == 0
    mark = max(m["strength"] for m in f.effective_marks(child))
    p = conductor(f, child)
    p.open_question("credential-rotation", text="How often should we rotate shared credentials?")
    advice = [l for l in p.listen().splitlines() if l.startswith("family ")]
    assert any("from chat, your parent" in l for l in advice)
    return (f"approved: 'chat' retired, '{child}' born with clean memory, {out['heirlooms']} heirlooms, leak mark {mark}; "
            f"it heard: '{advice[0][:100]}...'")


def test_you_can_declare_a_milestone_directly():
    f, root = setup("site")
    f.store("site").remember("homepage copy", 0.5, "ops")
    out = f.milestone("site", os.path.join(root, "site2"), "v2 rewrite on a new framework")
    assert out["name"] == "site@2" and f._load()["members"]["site@2"]["came_of_age"]["why"] == "v2 rewrite on a new framework"
    return "you declared 'v2 rewrite on a new framework': site came of age at once as site@2"


def test_age_alone_eventually_suggests_it():
    f, root = setup("old")
    s = f.store("old")
    with s._txn() as idx:
        idx["nights"] = AGE_NIGHTS
    sug = f.suggest("old")
    assert sug and any(r.startswith("age") for r in sug["reasons"])
    return f"after {AGE_NIGHTS} nights in one generation, the conductor suggests: {sug['reasons']}"


def test_kinship_is_suggested_then_approved():
    root = fresh("kin")
    f = Family(root)
    for n in ("pipeline", "quality"):
        f.birth(n, os.path.join(root, n))
        s = f.store(n)
        lesson(s, "rotate shared credentials on a fixed schedule", "shared credentials rotate on schedule")
        lesson(s, "deploy small changes daily", "small deploy changes daily")
    out = f.reunion()
    assert out["kin_suggestions"] and {out["kin_suggestions"][0]["a"], out["kin_suggestions"][0]["b"]} == {"pipeline", "quality"}
    fam = f._load()
    before = f.closeness(fam, "pipeline", "quality")
    f.approve_kin("pipeline", "quality")
    after = f.closeness(f._load(), "pipeline", "quality")
    assert before == 0 and after == 0.3
    return (f"two unrelated projects shared {out['kin_suggestions'][0]['shared_lessons']} lessons; the reunion proposed "
            f"them as kin; approved, they now count as siblings (closeness {before} -> {after})")



def test_the_tree_can_be_seen():
    from family_view import render_html, to_mermaid
    f, root = setup("view")
    f.birth("view-kid", os.path.join(root, "kid"), ["view"])
    f.milestone("view", os.path.join(root, "view2"), "rewrite")
    page = open(render_html(f, os.path.join(root, "tree.html"))).read()
    mm = to_mermaid(f)
    assert all(n in page for n in ("view", "view-kid", "view@2")) and "<svg" in page
    assert "==>|came of age|" in mm and mm.count("-->") == 1
    return "render_html draws every member as one self-contained page; to_mermaid marks the coming-of-age line"


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
