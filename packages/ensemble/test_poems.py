"""Poem-making: refuses the likely, keeps precision, opens language, settles nothing.
Run: python3 test_poems.py"""
import os
import random
import shutil
import tempfile

from dreams import HeuristicJudge
from embeddings import ConceptEmbedder
from memory import MemoryStore, word_commonness
from poets import HeuristicPoet

TMP = tempfile.mkdtemp()


def store(name, emb=False):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return MemoryStore(root, ConceptEmbedder() if emb else None)


def two(s):
    a = s.remember("the staging database password rotates monthly", 0.7, "ops")
    b = s.remember("the cafeteria closes early on fridays", 0.7, "facilities")
    return a, b


class Scripted:
    """A poet whose candidates and likelihoods are fixed, to test the selection."""

    def __init__(self, figures, aliases_a, aliases_b=None, verse=None):
        self.f, self.aa, self.ab, self.v = figures, aliases_a, aliases_b or [], verse

    def __call__(self, a, b, sim):
        return {"figures": self.f, "aliases": {"A": self.aa, "B": self.ab}, "verse": self.v, "score": 0.7}


def test_the_likely_half_is_always_refused():
    s = store("likely")
    a, b = two(s)
    poet = Scripted(figures=[{"text": "keys are like meals", "p": 0.40}, {"text": "a ledger molts", "p": 0.20},
                             {"text": "the canteen is a reliquary of hunger", "p": 0.05},
                             {"text": "salt-clocks shed their skins", "p": 0.01}],
                    aliases_a=[{"text": "the password thing", "p": 0.5}, {"text": "moon-shed cipher", "p": 0.02}])
    rep = s.compose(poet, pairs=1, rng=random.Random(0))
    fig = s.read(rep["figures"][0])
    names = [al for _, al in rep["aliases"]]
    assert fig == "salt-clocks shed their skins" and "moon-shed cipher" in names and "the password thing" not in names
    assert rep["excluded_as_likely"] == 3
    return f"of 4 figures the likelier half was refused; kept the least likely: '{fig}'; alias kept: {names}"


def test_a_lone_candidate_is_the_mode_and_is_refused():
    s = store("lone")
    two(s)
    rep = s.compose(Scripted(figures=["the obvious comparison"], aliases_a=["the only name"]), pairs=1,
                    rng=random.Random(0))
    assert not rep["figures"] and not rep["aliases"]
    return "a poet that offers one answer gives its most likely answer: nothing kept"


def test_model_logprobs_outrank_verbalized_guesses():
    s = store("logprob")
    two(s)
    poet = Scripted(figures=[{"text": "A", "p": 0.01, "logprob": -0.2}, {"text": "B", "p": 0.30, "logprob": -4.0},
                             {"text": "C", "p": 0.05, "logprob": -1.0}, {"text": "D", "p": 0.02, "logprob": -0.5}],
                    aliases_a=[])
    rep = s.compose(poet, pairs=1, rng=random.Random(0))
    assert s.read(rep["figures"][0]) == "B"
    return "when the model's own log-probs are present they decide: kept B (log-prob -4.0) though it claimed p=0.30"


def test_offline_poet_never_keeps_plain_language():
    s = store("plain")
    a = s.remember("the staging database password rotates monthly", 0.7, "ops")
    s.remember("printer jams on floor three", 0.7, "it")
    rep = s.compose(HeuristicPoet(), pairs=1, rng=random.Random(1))
    alias = next(al for t, al in rep["aliases"] if t == a)
    cands = HeuristicPoet()({"text": s.read(a), "tier": "x", "src": "ops"},
                            {"text": "printer jams", "tier": "x", "src": "it"}, 0)["aliases"]["A"]
    median = sorted(word_commonness(c) for c in cands)[len(cands) // 2]
    assert word_commonness(alias) < median and alias not in ("the secret of store", "the key of store")
    return f"kept '{alias}' (commonness {word_commonness(alias):.2f}) from {len(cands)} candidates, median {median:.2f}"


def test_precision_gate_rejects_ambiguous_names():
    s = store("precise", emb=True)
    p1 = s.remember("staging db password rotates monthly", 0.7, "ops")
    p2 = s.remember("preprod creds rotate monthly", 0.7, "security")         # nearly the same thing
    s.remember("cafeteria lunch closes early friday", 0.7, "facilities")
    poet = Scripted(figures=["x", "y"],
                    aliases_a=[{"text": "password rotation monthly", "p": 0.01}, {"text": "credential cycle", "p": 0.5}],
                    aliases_b=[{"text": "lunch hall friday", "p": 0.01}, {"text": "food", "p": 0.4}])
    rep = s.compose(poet, pairs=1, rng=random.Random(3))
    assert rep["rejected_aliases"] and not any(t in (p1, p2) for t, _ in rep["aliases"]), rep
    return f"an alias fitting two memories equally was refused ({rep['rejected_aliases'][0][1][0]!r}); precision kept"


def test_new_names_open_new_ways_in():
    s = store("open")
    a, b = two(s)
    before = s.recall("the moon-shed cipher", 0.9)
    s.compose(Scripted(figures=["f1", "f2"], aliases_a=[{"text": "the moon-shed cipher", "p": 0.01},
                                                        {"text": "the db password", "p": 0.6}]),
              pairs=1, rng=random.Random(0))
    after = s.recall("the moon-shed cipher", 0.9)
    assert not before and after and after[0]["id"] == a
    return "before: the metaphor found nothing; after composing: the same words recall the password memory"


def test_poems_never_settle_facts():
    s = store("settle", emb=True)
    lesson = s.remember("staging db password rotates monthly", 0.7, "ops")
    s.beat(5)
    s.remember("staging db password now rotates weekly instead", 0.7, "poem")   # a poem's figure
    s.sleep(HeuristicJudge(low=s.recall_min), cycles=2, pairs_per_cycle=6, rng=random.Random(4))
    m = s._load()["m"][lesson]
    assert "superseded_by" not in m and not s.open_tensions()
    return "a poem's line that reads like an update replaced nothing and raised no dispute in sleep"


def test_figures_are_hypotheses_and_verses_stay_flat():
    s = store("hyp")
    a, b = two(s)
    figs = []
    for i in range(15):
        rep = s.compose(Scripted(figures=[f"figure {i} alpha", f"figure {i} zeta-quill"], aliases_a=[],
                                 verse=f"verse {i}"), pairs=1, rng=random.Random(i))
        figs += rep["figures"]
    m = s._load()["m"]
    assert all(m[f]["origin"] == "dream" for f in figs[:3])
    s.use(figs[0]); s.use(figs[0])
    assert s._load()["m"][figs[0]]["origin"] == "confirmed"
    assert len(s.poems()) == 12 and open(os.path.join(s.root, "poems.md")).read().count("verse ") == 12
    return "figures start as unconfirmed ideas (confirmed after 2 waking uses); 15 sessions left the last 12 verses in poems.md"


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
