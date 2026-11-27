"""The Ensemble robustness tests, run against the markdown backend. Run: python3 test_md.py"""
import multiprocessing as mp
import os
import random
import shutil
import subprocess
import tempfile
import time

from ensemble import Ensemble, FS
from mdensemble import MdEnsemble

ROSTER = ["conductor", "strings", "brass", "woodwinds", "percussion", "keys", "harp", "choir", "soloist"]
TMP = tempfile.mkdtemp()


def fresh(name="md", roster=ROSTER):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return MdEnsemble(root, roster)


def test_parts_exact_and_bounded():
    e = fresh()
    rng = random.Random(1)
    last, sizes = {}, []
    for i in range(2000):
        a = rng.choice(ROSTER[1:])
        text = f"{a} update {i}: " + " ".join(rng.choice(["schema", "token", "retry", "api", "ui", "cache"])
                                               for _ in range(rng.randint(1, 120)))
        e.note(a, text)
        last[a] = text
        sizes.append(e.size())
    for a, text in last.items():
        assert e.read(a)[1]["note"] == text
    bound = e.cap * len(ROSTER) + 4096
    assert max(sizes) <= bound
    return f"2000 random writes, all parts exact; storage {min(sizes[100:])}-{max(sizes)} B, hard bound {bound} B"


def test_score_exact_vs_ledger():
    e = fresh()
    rng = random.Random(2)
    qs = ["auth-first", "rotate-tokens", "api-stable"]
    for q in qs:
        e.open_question(q)
    ledger = {q: {} for q in qs}
    beat, worst = 0, 0.0
    for _ in range(300):
        a, q = rng.choice(ROSTER[1:]), rng.choice(qs)
        r = rng.random()
        if r < 0.1:
            beat = e.beat()
        elif r < 0.2 and a in ledger[q]:
            e.withdraw(a, q); del ledger[q][a]
        else:
            s, c = rng.choice([1, -1]), round(rng.random(), 3)
            e.cast(a, q, "yes" if s > 0 else "no", c)
            ledger[q][a] = (s, c, beat)
        st = e.state()["score"]
        for q2, votes in ledger.items():
            w = sum(c * e.gamma ** (beat - t) for s, c, t in votes.values())
            worst = max(worst, abs(st[q2]["weight"] - w))
    assert worst < 1e-9 and e.audit() == []
    return f"300 random votes/withdrawals/beats; worst deviation {worst:.1e} (exact); audit clean"


def test_audit_catches_tampered_summary():
    e = fresh()
    e.open_question("ship")
    for a in ROSTER[1:5]:
        e.cast(a, "ship", "yes", 0.7)
    path = os.path.join(e.root, "score.md")
    text = open(path).read().replace('"verdict":"yes"', '"verdict":"no"').replace('"weight":2.8', '"weight":9.9')
    open(path, "w").write(text)
    flags = e.audit()
    assert flags, flags
    return f"hand-edited score.md detected: {flags}"


def test_limits():
    e = fresh()
    e.open_question("q")
    try:
        e.note("strings", "x" * 5000); raise AssertionError
    except ValueError:
        pass
    e.cast("strings", "q", "yes", 50)
    assert abs(e.state()["score"]["q"]["weight"] - 1.0) < 1e-9
    n = 0
    try:
        while True:
            e.open_question(f"q-{n:03d}"); n += 1
    except ValueError:
        pass
    return (f"oversize part rejected, confidence 50 -> 1.0; the conductor's {e.cap}-byte file "
            f"holds {n + 1} open questions before it fills")


def _worker(args):
    root, agent, seed = args
    e = MdEnsemble(root, ROSTER)
    rng = random.Random(seed)
    last = None
    for i in range(40):
        if rng.random() < 0.5:
            last = f"{agent} note {i} " + "x" * rng.randint(0, 200)
            e.note(agent, last)
        else:
            e.cast(agent, rng.choice(["c1", "c2"]), rng.choice(["yes", "no"]), round(rng.random(), 3))
    return agent, last


def test_concurrent_writers():
    e = fresh()
    e.open_question("c1"); e.open_question("c2")
    t0 = time.time()
    with mp.Pool(8) as pool:
        results = pool.map(_worker, [(e.root, a, i) for i, a in enumerate(ROSTER[1:])])
    for agent, last in results:
        if last:
            assert e.read(agent)[1]["note"] == last
    assert e.audit() == []
    return f"8 processes x 40 ops in {time.time() - t0:.1f}s: no lost writes, summary consistent"


def _scenario(name="md"):
    e = fresh(name)
    e.open_question("auth-first"); e.open_question("rotate-tokens"); e.open_question("db", ["postgres", "sqlite", "dynamo"])
    rng = random.Random(3)
    for i, a in enumerate(ROSTER[1:]):
        e.note(a, f"{a}: working on part {i} " * 8)
        e.cast(a, "auth-first", "yes" if i < 7 else "no", 0.6 + 0.04 * i)
        e.cast(a, "rotate-tokens", "yes" if i % 2 else "no", 0.7)
        e.cast(a, "db", (["postgres"] * 5 + ["sqlite"] * 2 + ["dynamo"])[i], rng.uniform(0.5, 1))
    e.beat(); e.beat()
    return e


def test_three_way_merge():
    e = _scenario()
    base = os.path.join(TMP, "base"); shutil.rmtree(base, ignore_errors=True); shutil.copytree(e.root, base)
    hosts = []
    for n in ("hostA", "hostB", "single"):
        p = os.path.join(TMP, n); shutil.rmtree(p, ignore_errors=True); shutil.copytree(base, p)
        hosts.append(MdEnsemble(p, ROSTER))
    A, B, S = hosts
    ops_a = [("note", "strings", "moved to host A"), ("cast", "strings", "rotate-tokens", "yes", 1.0)]
    ops_b = [("note", "keys", "on host B"), ("cast", "harp", "auth-first", "no", 0.8)]
    for host, ops in ((A, ops_a), (B, ops_b)):
        for op in ops:
            for t in (host, S):
                getattr(t, op[0])(*op[1:])
    assert e.merge(base, A.root, B.root) == []
    assert e.state()["score"] == S.state()["score"]
    return "two hosts diverged; merge is exactly equal to doing every op on one host"


def test_crashed_agent_fades():
    e = fresh()
    e.open_question("ship")
    e.cast("strings", "ship", "no", 1.0)
    for a in ROSTER[2:6]:
        e.cast(a, "ship", "yes", 0.25)
    first = e.state()["score"]["ship"]["verdict"]
    for b in range(40):
        e.beat()
        if b % 5 == 4:
            for a in ROSTER[2:6]:
                e.cast(a, "ship", "yes", 0.25)
    s = e.state()["score"]["ship"]
    assert first == "split" and s["verdict"] == "yes"
    return f"crashed agent's 'no' faded: split -> yes (lean {s['lean']:+.2f}) after 40 beats"


def test_export_to_wav_and_mp3():
    e = _scenario("exp")
    wav = os.path.join(TMP, "export.wav")
    cut = e.export_wav(wav)
    audio = Ensemble(wav, ROSTER)
    ref, got = e.state()["score"], audio.state()["score"]
    worst = 0.0
    for q, r in ref.items():
        if "lean" in r:
            assert got[q]["verdict"] == r["verdict"]
            worst = max(worst, abs(got[q]["lean"] - r["lean"]))
    assert audio.audit() == []
    mp3, back = os.path.join(TMP, "e.mp3"), os.path.join(TMP, "e_back.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-b:a", "64k", mp3], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", str(FS), "-ac", "1", back], check=True)
    reg = audio._reg(audio._load())
    via = audio.read_copy(back, reg=reg)["score"]
    for q, r in ref.items():
        if "lean" in r:
            assert via[q]["verdict"] == r["verdict"]
    return (f"markdown -> WAV: verdicts match, worst lean error {worst:.4f}, audio audit clean, "
            f"notes cut: {cut or 'none'}; WAV -> 64 kbps MP3 -> verdicts still match")


def test_latency():
    e = _scenario("lat")
    out = {}
    for name, fn in [("state()", e.state), ("note()", lambda: e.note("strings", "x" * 300)),
                     ("cast()", lambda: e.cast("brass", "auth-first", "yes", 0.5)),
                     ("read(part)", lambda: e.read("keys")), ("audit()", e.audit)]:
        t0 = time.perf_counter()
        for _ in range(50):
            fn()
        out[name] = (time.perf_counter() - t0) / 50 * 1000
    return ", ".join(f"{k} {v:.1f} ms" for k, v in out.items())


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
