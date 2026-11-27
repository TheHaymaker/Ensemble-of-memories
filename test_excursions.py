"""Excursions: curiosity that acts. Run: python3 test_excursions.py"""
import os
import random
import shutil
import tempfile

from dreams import HeuristicJudge
from embeddings import ConceptEmbedder
from explorers import HeuristicExplorer
from mdensemble import MdEnsemble
from memory import MemoryStore
from poets import HeuristicPoet
from tools import Player

TMP = tempfile.mkdtemp()


def store(name, emb=True):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return MemoryStore(root, ConceptEmbedder() if emb else None)


class Scripted:
    def __init__(self, **note):
        self.note, self.seeds = note, []

    def __call__(self, seed, context):
        self.seeds.append(seed)
        return dict(self.note)


def test_silly_ideas_are_done_anyway_and_kept():
    s = store("silly")
    s.remember("the cafeteria closes early on fridays", 0.6, "facilities")
    s.remember("refresh tokens rotate on every use", 0.6, "auth")
    ex = Scripted(form="thought-exercise", title="a cafeteria that rotates its menu like tokens",
                  outcome="every lunch expires after one bite", verdict="silly", spawn=[])
    rep = s.wander(ex, n=1, rng=random.Random(0))
    note = s.read(rep["excursions"][0])
    assert rep["verdicts"] == {"silly": 1} and note.startswith("[imagined thought-exercise]")
    assert "What if" in ex.seeds[0]
    assert "imagined, unconfirmed" in s.describe(rep["excursions"][0])
    return f"seed '{ex.seeds[0][:60]}...' -> kept anyway: '{note[:80]}...'"


def test_seeds_come_from_poems_and_are_not_repeated():
    s = store("seeds")
    a = s.remember("the staging database password rotates monthly", 0.7, "ops")
    s.remember("printer jams on floor three", 0.7, "it")
    s.compose(HeuristicPoet(), pairs=1, rng=random.Random(1))
    ex = Scripted(form="build-out", title="t", outcome="o", verdict="trivial")
    seen = []
    for i in range(4):
        s.wander(ex, n=1, rng=random.Random(i))
    poem_seeds = [x for x in ex.seeds if not x.startswith("What if")]
    assert poem_seeds and len(poem_seeds) == len(set(poem_seeds))
    return f"{len(poem_seeds)} excursion(s) seeded from poem figures, none repeated; the rest were what-if pairings"


def test_excursions_spawn_new_memories():
    s = store("spawn")
    s.remember("deploys go out tuesday and thursday", 0.6, "ops")
    s.remember("the cafeteria closes early on fridays", 0.6, "facilities")
    ex = Scripted(form="build-out", title="deploy lunch", outcome="o", verdict="promising",
                  spawn=["ship only after lunch", "a canteen for releases", "a third idea that gets dropped"])
    rep = s.wander(ex, n=1, rng=random.Random(0))
    m = s._load()["m"]
    assert len(rep["spawned"]) == 2 and all(m[k]["parents"] == rep["excursions"] for k in rep["spawned"])
    return f"one excursion gave rise to {len(rep['spawned'])} new ideas (capped at 2), each linked to it"


def test_imagined_hypotheses_can_come_true():
    s = store("true")
    s.remember("staging db password rotates monthly", 0.6, "ops")
    s.remember("cafeteria lunch closes early friday", 0.6, "facilities")
    ex = Scripted(form="hypothesis", title="credentials want to rotate faster", outcome="o", verdict="promising",
                  prediction="the staging db password will rotate weekly")
    rep = s.wander(ex, n=1, rng=random.Random(0))
    hyp, pred = rep["excursions"][0], rep["predictions"][0]
    s.beat(10)
    s.remember("cafeteria opens late on monday", 0.5, "facilities")          # unrelated: nothing happens
    assert s._load()["m"][hyp]["origin"] == "dream"
    news = s.remember("ops: the staging db password now rotates weekly", 0.6, "ops")
    m = s._load()["m"]
    assert m[pred]["came_true"] == news and m[hyp]["origin"] == "confirmed" and m[hyp]["confirmed_by"] == news
    assert "imagined, unconfirmed" not in s.describe(hyp)
    return "an imagined hypothesis predicted weekly rotation; 10 beats later a real note reported it, and the hypothesis became confirmed"


def test_excursions_never_settle_facts():
    s = store("facts")
    lesson = s.remember("staging db password rotates monthly", 0.7, "ops")
    s.beat(5)
    ex = Scripted(form="thought-exercise", title="weekly", outcome="staging db password now rotates weekly instead",
                  verdict="nonsensical")
    s.wander(ex, n=1, rng=random.Random(0))
    s.sleep(HeuristicJudge(low=s.recall_min), cycles=2, pairs_per_cycle=6, rng=random.Random(1))
    assert "superseded_by" not in s._load()["m"][lesson] and not s.open_tensions()
    return "an excursion whose outcome read like an update changed nothing and raised no dispute"


def test_experiments_only_run_through_your_runner():
    s = store("run")
    s.remember("deploys go out tuesday and thursday", 0.6, "ops")
    s.remember("printer jams on floor three", 0.6, "it")
    ex = Scripted(form="experiment", title="count jams", outcome="o", verdict="trivial", code="print(2 + 2)")
    no_runner = s.read(s.wander(ex, n=1, rng=random.Random(0))["excursions"][0])
    ran = []
    def sandbox(code):
        ran.append(code)
        return "4"
    with_runner = s.read(s.wander(ex, n=1, rng=random.Random(1), runner=sandbox)["excursions"][0])
    assert "ran it" not in no_runner and "(ran it: 4)" in with_runner and ran == ["print(2 + 2)"]
    return "with no runner the experiment stays imagined; with your sandbox it ran and the output joined the note"


def test_the_whole_night_with_curiosity():
    ens = MdEnsemble(os.path.join(TMP, "night_ens"), ["conductor"])
    shutil.rmtree(ens.root); ens = MdEnsemble(os.path.join(TMP, "night_ens"), ["conductor"])
    p = Player(ens, "conductor", store("night"), sleep_at=4, poet=HeuristicPoet(),
               explorer=HeuristicExplorer(seed=2), excursions=2)
    for t in ("the staging database password rotates monthly", "printer jams on floor three",
              "deploys go out tuesday and thursday", "the cafeteria closes early on fridays"):
        p.remember(t, 0.6)
    heard = p.listen()
    lines = [l for l in heard.splitlines() if l.startswith(("slept", "composed", "wandered"))]
    assert len(lines) == 3 and os.path.exists(os.path.join(p.memory.root, "excursions.md"))
    assert "composed from 0" not in heard and "wandered: 2 excursions" in heard
    return " | ".join(lines)


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
