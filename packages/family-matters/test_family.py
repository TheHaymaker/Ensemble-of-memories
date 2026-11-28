"""A three-generation family. Run: python3 test_family.py"""
import json
import os
import random
import shutil
import tempfile

from dreams import HeuristicJudge
from explorers import HeuristicExplorer
from family import Family
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

TMP = tempfile.mkdtemp()


def fresh(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return root


def live(f, name, nights, excursions=0, lessons=(), seed=0):
    """Give a member a life: nights of sleep, some excursions, and lessons it earned."""
    s = f.store(name)
    rng = random.Random(seed)
    for text, twin in lessons:
        a = s.remember(text, 0.6, name); b = s.remember(twin, 0.6, name)
        for i in range(8):
            s.beat(4); s.use(a); s.use(b)
    for n in range(nights):
        s.remember(f"{name} routine note {n} printer jam", 0.3, name)
        if excursions:
            s.wander(HeuristicExplorer(seed + n), n=excursions, rng=rng)
        s.sleep(HeuristicJudge(low=s.recall_min), cycles=2, pairs_per_cycle=6, rng=rng)
        s.beat(4)
        for text, _ in lessons:
            hit = s.recall(text, 0.4)
            if hit:
                s.use(hit[0]["id"])
    return s


def family_of_three_generations():
    root = fresh("fam")
    f = Family(root)
    f.birth("atlas", os.path.join(root, "atlas"))
    live(f, "atlas", nights=4, excursions=2,
         lessons=[("rotate shared credentials on a fixed schedule", "shared credentials rotate on schedule")])
    f.mark("atlas", "leaked credentials", 1.0, "a credential leak in production")
    f.birth("quill", os.path.join(root, "quill"))                       # an unrelated, quiet founder
    live(f, "quill", nights=4)
    f.birth("birch", os.path.join(root, "birch"), ["atlas"])
    f.birth("cedar", os.path.join(root, "cedar"), ["atlas"])
    live(f, "birch", nights=2)
    f.mark("birch", "credentials leaked again", 1.0, "it happened to us too")
    live(f, "cedar", nights=6)                                          # a calm life
    return f


F = family_of_three_generations()


def test_traits_come_from_how_a_project_lived():
    a, q = F.traits("atlas"), F.traits("quill")
    ea, eq = F.expression(a), F.expression(q)
    assert a["curiosity"] > 0.6 > q["curiosity"] and ea["excursions"] > eq["excursions"]
    return (f"atlas ran 2 excursions a night -> curiosity {a['curiosity']}, {ea['excursions']} excursions/night as a trait; "
            f"quiet quill -> {q['curiosity']}, {eq['excursions']}")


def test_children_blend_their_relatives_by_closeness():
    born = F.birth("fern", os.path.join(F.root, "fern"), ["atlas", "quill"])["traits"]
    a, q = F.traits("atlas"), F.traits("quill")
    fam = F._load()
    w = {o: F.closeness(fam, "fern", o) for o in fam["members"] if F.closeness(fam, "fern", o) > 0}
    lo, hi = sorted((a["curiosity"], q["curiosity"]))
    assert lo < born["curiosity"] < hi and w["atlas"] == w["quill"] == 1.0 and w["birch"] == 0.3
    return f"fern, child of curious atlas and quiet quill, was born with curiosity {born['curiosity']} (relatives weighted {w})"


def test_marks_halve_renew_and_fade():
    def strength(n, theme="credentials"):
        return max((m["strength"] for m in F.effective_marks(n) if "credentials" in m["theme"]), default=0.0)
    F.birth("dune", os.path.join(F.root, "dune"), ["birch"])
    F.birth("elm", os.path.join(F.root, "elm"), ["cedar"])
    b, c, d, e = strength("birch"), strength("cedar"), strength("dune"), strength("elm")
    assert b == 1.0 and 0.1 < c < 0.3 and d == 0.5 and e < c
    return (f"atlas leak 1.0 -> birch inherited 0.5, then lived its own leak: {b}; cedar inherited 0.5 and lived calmly "
            f"for 6 nights: {c}; birch's child dune: {d}; cedar's child elm: {e}")


def test_a_mark_changes_what_feels_important():
    ens = MdEnsemble(fresh("imp_ens"), ["birch", "quill"])
    pb = Player(ens, "birch", F.store("birch"), family=F)
    pq = Player(ens, "quill", F.store("quill"), family=F)
    text = "someone pasted the credentials into a public channel"
    mb, mq = pb.memory.remember(text, 0.4, "birch"), pq.memory.remember(text, 0.4, "quill")
    ib, iq = pb.memory._load()["m"][mb]["s"], pq.memory._load()["m"][mq]["s"]
    assert ib > iq
    return f"the same event felt more important to birch (marked by leaks): {ib:.2f} vs quill {iq:.2f}"


def test_sayings_are_advice_until_confirmed():
    told = F.tell("atlas")
    ens = MdEnsemble(fresh("say_ens"), ["birch"])
    p = Player(ens, "birch", F.store("birch"), family=F)
    p.open_question("credential-rotation", text="How often should we rotate shared credentials?")
    heard = p.listen()
    line = next(l for l in heard.splitlines() if l.startswith("family advice"))
    sid = line.split()[2]
    assert "advice only" in line and "from atlas, your parent" in line
    mid = p.family.adopt("birch", sid)
    m = p.memory._load()["m"][mid]
    assert m["origin"] == "inherited"
    for _ in range(p.memory.confirm_uses):
        p.memory.beat(4); p.memory.use(mid)
    before = F._load()["sayings"][sid]["weight"]
    F.reunion()
    after = F._load()["sayings"][sid]
    assert after["weight"] > before and "birch" in after["confirmed_by"]
    return f"{told} saying(s) told; birch heard: '{line[:110]}...'; adopted, confirmed by use, and the reunion raised its weight {before} -> {after['weight']}"


def test_children_can_turn_out_differently():
    born = F._load()["members"]["dune"]["born_traits"]["curiosity"]
    live(F, "dune", nights=12)                       # never wanders
    now = F.traits("dune")["curiosity"]
    child = F.birth("gale", os.path.join(F.root, "gale"), ["dune"])["traits"]["curiosity"]
    assert now < born and child < born
    return f"dune was born with curiosity {born} but never wandered: now {now}; its child gale starts at {child}"


def test_reunions_find_what_only_the_family_can_see():
    for n, (t1, t2) in (("birch", ("deploy small changes daily", "small deploy changes daily")),
                        ("cedar", ("deploy small changes each day", "small deploy changes each day"))):
        live(F, n, nights=4, lessons=[(t1, t2)], seed=7)
    out = F.reunion()
    assert any("deploy" in w for w in out["wisdom"]), out
    return f"birch and cedar each learned it separately; the reunion named it family wisdom: {out['wisdom']}"


def test_heirlooms_pass_intact():
    s = F.store("atlas")
    mid = s.remember("the 2am rollback that saved launch day: revert first, investigate second", 0.9, "atlas")
    hid = F.heirloom("atlas", mid, "how we stay calm in incidents")
    ens = MdEnsemble(fresh("heir_ens"), ["elm"])
    p = Player(ens, "elm", F.store("elm"), family=F)
    p.open_question("rollback-or-investigate", text="During the incident do we rollback first or investigate?")
    line = next(l for l in p.listen().splitlines() if "baggage" in l)
    assert "revert first, investigate second" in line
    return f"great-grandchild elm, facing an incident question, was handed: '{line[:120]}'"


def test_the_family_store_stays_small():
    root = fresh("long_fam")
    f = Family(root)
    prev = []
    sizes = []
    for g in range(12):
        name = f"g{g:02d}"
        f.birth(name, os.path.join(root, name), prev)
        s = f.store(name)
        rng = random.Random(g)
        words = "harbor lantern quarry velvet cobalt meadow tundra saffron glacier orchard ember canyon".split()
        for i in range(10):                         # ten distinct lessons per generation, injected directly
            text = " ".join(f"{w}{g:02d}{i}" for w in rng.sample(words, 3))         # unique words per lesson
            mid = s.remember(text, 0.6, name)
            with s._txn() as idx:
                idx["m"][mid].update(lesson=True, c=2)
        f.mark(name, f"incident {g}", 1.0)
        f.retire(name)
        sizes.append(os.path.getsize(os.path.join(root, "family.json")))
        prev = [name]
    fam = json.load(open(os.path.join(root, "family.json")))
    assert len(fam["sayings"]) == 60 and sizes[-1] < 1.5 * sizes[5]
    return (f"12 generations, 120 lessons told: {len(fam['sayings'])} sayings kept; family.json "
            f"{sizes[5] // 1024} KB at generation 6, {sizes[-1] // 1024} KB at 12")


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
