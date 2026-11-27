"""Robustness tests for Ensemble. Run: python3 test_ensemble.py"""
import multiprocessing as mp
import os
import random
import shutil
import subprocess
import tempfile
import time
import wave

import numpy as np

from ensemble import CAP, Ensemble, FS

ROSTER = ["conductor", "strings", "brass", "woodwinds", "percussion", "keys", "harp", "choir", "soloist"]
TMP = tempfile.mkdtemp()


def fresh(name="mix.wav", roster=ROSTER):
    path = os.path.join(TMP, name)
    for f in (path, path + ".lock"):
        if os.path.exists(f):
            os.remove(f)
    return Ensemble(path, roster)


def truth(e, ledger, beat):
    """Expected (lean, weight) per binary question from a plain-Python ledger."""
    out = {}
    for qid, votes in ledger.items():
        net = sum(s * c * e.gamma ** (beat - t) for s, c, t in votes.values())
        w = sum(c * e.gamma ** (beat - t) for s, c, t in votes.values())
        out[qid] = (net / w if w > 0.05 else 0.0, w)
    return out


def test_parts_exact_isolated_flat():
    e = fresh()
    rng = random.Random(1)
    last = {}
    size = os.path.getsize(e.path)
    for i in range(2000):
        a = rng.choice(ROSTER[1:])
        text = f"{a} update {i}: " + " ".join(rng.choice(["schema", "token", "retry", "api", "ui", "cache"])
                                               for _ in range(rng.randint(1, 120)))
        e.note(a, text)
        last[a] = text
        assert os.path.getsize(e.path) == size
    for a, text in last.items():
        assert e.read(a)[1]["note"] == text
    return f"2000 random writes, {len(last)} parts all exact, file stayed {size} bytes"


def test_score_matches_ledger_with_retraction_and_decay():
    e = fresh()
    rng = random.Random(2)
    qs = ["auth-first", "rotate-tokens", "api-stable"]
    for q in qs:
        e.open_question(q)
    ledger = {q: {} for q in qs}
    beat = 0
    worst = 0.0
    for step in range(300):
        a, q = rng.choice(ROSTER[1:]), rng.choice(qs)
        r = rng.random()
        if r < 0.1:
            beat = e.beat()
        elif r < 0.2 and a in ledger[q]:
            e.withdraw(a, q)
            del ledger[q][a]
        else:
            stance, conf = rng.choice([1, -1]), round(rng.random(), 3)
            e.cast(a, q, "yes" if stance > 0 else "no", conf)
            ledger[q][a] = (stance, conf, beat)
        st = e.state()["score"]
        for q2, (lean, w) in truth(e, ledger, beat).items():
            worst = max(worst, abs(st[q2]["weight"] - w), abs(st[q2]["lean"] - lean) * min(w, 1))
    assert worst < 0.02, worst
    assert e.audit() == []
    return f"300 random votes/withdrawals/beats; worst deviation from ledger {worst:.4f}; audit clean"


def test_audit_catches_undeclared_play():
    e = fresh()
    e.open_question("ship")
    for a in ROSTER[1:5]:
        e.cast(a, "ship", "yes", 0.7)
    assert e.audit() == []
    # a faulty agent plays a 'no' into the score without declaring it in its part
    with e._txn() as spec:
        reg = e._reg(spec)
        e._play(spec, e._contrib(reg["q"]["ship"], -1, 0.9, reg["t"], reg["t"]))
    flags = e.audit()
    assert flags and flags[0]["question"] == "ship", flags
    return f"undeclared vote detected: {flags}"


def test_limits():
    e = fresh()
    e.open_question("q")
    msgs = []
    try:
        e.note("strings", os.urandom(2000).hex())
    except ValueError as err:
        msgs.append(str(err))
    e.cast("strings", "q", "yes", 50)                     # clamped to 1
    assert abs(e.state()["score"]["q"]["weight"] - 1.0) < 1e-6
    for bad in (lambda: e.cast("strings", "nope", "yes", 1), lambda: e.cast("strings", "q", "maybe", 1)):
        try:
            bad(); raise AssertionError("should fail")
        except (KeyError, ValueError) as err:
            msgs.append(str(err))
    n = 1
    try:
        while True:
            e.open_question(f"fill{n}"); n += 1
    except RuntimeError as err:
        msgs.append(str(err))
    return f"oversize part, confidence 50 -> 1.0, bad question/answer, score full after {n} questions"


def _worker(args):
    path, agent, seed = args
    e = Ensemble(path, ROSTER)
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
        results = pool.map(_worker, [(e.path, a, i) for i, a in enumerate(ROSTER[1:])])
    dt = time.time() - t0
    for agent, last in results:
        if last:
            assert e.read(agent)[1]["note"] == last
    assert e.audit() == [], e.audit()
    return f"8 processes x 40 ops in {dt:.1f}s: no lost writes, every part exact, score matches parts"


def _ffmpeg(src, dst, *args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, *args, dst], check=True)


def _write_wav(path, x):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS)
        w.writeframes(np.clip(np.round(x * 32767), -32767, 32767).astype("<i2").tobytes())


def _scenario():
    e = fresh()
    e.open_question("auth-first"); e.open_question("rotate-tokens"); e.open_question("db", ["postgres", "sqlite", "dynamo"])
    rng = random.Random(3)
    for i, a in enumerate(ROSTER[1:]):
        e.note(a, f"{a}: working on part {i} " * 8)
        e.cast(a, "auth-first", "yes" if i < 7 else "no", 0.6 + 0.04 * i)
        e.cast(a, "rotate-tokens", "yes" if i % 2 else "no", 0.7)
        e.cast(a, "db", (["postgres"] * 5 + ["sqlite"] * 2 + ["dynamo"])[i], rng.uniform(0.5, 1))
    e.beat(); e.beat()
    return e


def _compare(ref, got):
    worst = 0.0
    for q, r in ref.items():
        g = got[q]
        if "lean" in r:
            assert g["verdict"] == r["verdict"], (q, r, g)
            worst = max(worst, abs(g["lean"] - r["lean"]))
        else:
            assert max(g["shares"], key=g["shares"].get) == max(r["shares"], key=r["shares"].get)
            worst = max(worst, max(abs(g["shares"][o] - r["shares"][o]) for o in r["shares"]))
    return worst


def test_lossy_copies():
    e = _scenario()
    ref = e.state()["score"]
    reg = e._reg(e._load())
    x = e._samples(e.path)
    lines = []
    # shifted by 337 samples, quieter, with background noise
    shifted = os.path.join(TMP, "shifted.wav")
    noisy = np.concatenate([np.zeros(337), x * 0.6]) + np.random.default_rng(0).normal(0, 0.003, len(x) + 337)
    _write_wav(shifted, noisy)
    got = e.read_copy(shifted, reg=reg)
    assert got["offset"] == 337, got["offset"]
    lines.append(f"shift 337 + gain 0.6 + noise: offset found {got['offset']}, gain {got['gain']:.2f}, "
                 f"worst lean/share error {_compare(ref, got['score']):.3f}")
    for kbps in (128, 64, 32):
        mp3, back = os.path.join(TMP, f"m{kbps}.mp3"), os.path.join(TMP, f"m{kbps}.wav")
        _ffmpeg(shifted, mp3, "-b:a", f"{kbps}k")
        _ffmpeg(mp3, back, "-ar", str(FS), "-ac", "1")
        got = e.read_copy(back, reg=reg)
        lines.append(f"MP3 {kbps:3d} kbps: verdicts match, worst error {_compare(ref, got['score']):.3f}, "
                     f"intact parts {len(got['intact_parts'])}/9")
    return "\n      ".join(lines)


def test_three_way_merge():
    e = _scenario()
    base = os.path.join(TMP, "base.wav"); shutil.copy(e.path, base)
    host_a = Ensemble(os.path.join(TMP, "hostA.wav"), ROSTER); shutil.copy(base, host_a.path)
    host_b = Ensemble(os.path.join(TMP, "hostB.wav"), ROSTER); shutil.copy(base, host_b.path)
    single = Ensemble(os.path.join(TMP, "single.wav"), ROSTER); shutil.copy(base, single.path)
    ops_a = [("note", "strings", "strings moved to host A"), ("cast", "strings", "rotate-tokens", "yes", 1.0),
             ("cast", "brass", "db", "sqlite", 0.9)]
    ops_b = [("note", "keys", "keys on host B"), ("cast", "keys", "rotate-tokens", "yes", 0.9),
             ("cast", "harp", "auth-first", "no", 0.8)]
    for host, ops in ((host_a, ops_a), (host_b, ops_b)):
        for op in ops:
            for target in (host, single):
                getattr(target, op[0])(*op[1:])
    clashes = e.merge(base, host_a.path, host_b.path)
    assert clashes == []
    from ensemble import CB0, CBN, G_V
    m, s1 = (x._load()[0, CB0:CB0 + CBN].real / G_V for x in (e, single))
    assert np.abs(m - s1).max() <= 0.0011, np.abs(m - s1).max()   # one 0.001 grid step: rounding order
    for a in ROSTER:
        assert e.read(a)[1] == single.read(a)[1]
    assert e.audit() == []
    return "two hosts diverged; merge equals doing every op on one host (parts exact, score within one 0.001 step)"


def test_crashed_agent_fades():
    e = fresh()
    e.open_question("ship")
    e.cast("strings", "ship", "no", 1.0)              # strings will crash
    for a in ROSTER[2:6]:
        e.cast(a, "ship", "yes", 0.25)
    first = e.state()["score"]["ship"]["verdict"]
    for b in range(40):
        e.beat()
        if b % 5 == 4:                                 # the live agents re-affirm
            for a in ROSTER[2:6]:
                e.cast(a, "ship", "yes", 0.25)
    s = e.state()["score"]["ship"]
    assert first == "split" and s["verdict"] == "yes", (first, s)
    return f"crashed agent's confident 'no' faded: split -> {s['verdict']} (lean {s['lean']:+.2f}) after 40 beats"


def test_latency():
    e = _scenario()
    timings = {}
    for name, fn in [("state()", e.state), ("note()", lambda: e.note("strings", "x" * 300)),
                     ("cast()", lambda: e.cast("brass", "auth-first", "yes", 0.5)),
                     ("read(part)", lambda: e.read("keys")), ("audit()", e.audit)]:
        t0 = time.perf_counter()
        for _ in range(50):
            fn()
        timings[name] = (time.perf_counter() - t0) / 50 * 1000
    return ", ".join(f"{k} {v:.1f} ms" for k, v in timings.items())


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
