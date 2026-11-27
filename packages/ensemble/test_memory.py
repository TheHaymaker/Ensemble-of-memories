"""Tests and a long simulation for the tiered memory store.
Run: python3 test_memory.py [out_dir]   (writes memory_life.png)"""
import multiprocessing as mp
import os
import random
import shutil
import sys
import tempfile

from memory import DORMANT, FLOOR_CAP, MemoryStore

TMP = tempfile.mkdtemp()


def fresh(name):
    root = os.path.join(TMP, name)
    shutil.rmtree(root, ignore_errors=True)
    return MemoryStore(root)


def row(s, mid):
    return next(r for r in s.rows() if r["id"] == mid)


def test_unused_memory_fades_to_dormant():
    s = fresh("fade")
    mid = s.remember("one-off fact about the build server", 0.5)
    beats = 0
    while row(s, mid)["tier"] != "dormant":
        s.beat(); beats += 1
    assert "m00001" not in s.summary().split("\n", 1)[-1]
    return f"never-used memory went dormant after {beats} beats and left the summary"


def test_spacing_beats_massing():
    s = fresh("spacing")
    massed = s.remember("massed: crammed six times in one beat", 0.5)
    spaced = s.remember("spaced: used six times, four beats apart", 0.5)
    for _ in range(6):
        s.use(massed)
    for i in range(6):
        s.use(spaced); s.beat(4)
    s.beat(60)
    m, p = row(s, massed), row(s, spaced)
    assert m["tier"] == "dormant" and p["tier"] == "long", (m, p)
    return f"after 84 beats: massed -> {m['tier']}, spaced -> {p['tier']} ({p['strength']:.2f})"


def test_revival_needs_a_strong_matching_cue():
    s = fresh("revive")
    mid = s.remember("the staging database password rotates on the first monday of each month", 0.5)
    s.beat(30)
    assert row(s, mid)["tier"] == "dormant"
    weak = s.recall("staging database password rotation monday", 0.3)
    unrelated = s.recall("frontend button colours and spacing", 1.0)
    floor_before = row(s, mid)["floor"]
    strong = s.recall("when does the staging database password rotate", 0.9)
    r = row(s, mid)
    assert not weak and not unrelated and strong and strong[0]["how"] == "revived"
    assert r["tier"] == "short" and r["floor"] > floor_before and r["revivals"] == 1
    return (f"weak matching cue: no; strong unrelated cue: no; strong matching cue: revived to "
            f"{r['tier']} {r['strength']:.2f}, floor {floor_before} -> {r['floor']}")


def test_buffs_are_permanent_but_capped():
    s = fresh("buffs")
    six = s.remember("used six times", 0.5)
    seven = s.remember("used seven times", 0.5)
    heavy = s.remember("used a thousand times", 0.5)
    for i in range(6):
        s.use(six)
    for i in range(7):
        s.use(seven)
    for i in range(1000):
        s.use(heavy)
    s.beat(2000)
    a, b, h = row(s, six), row(s, seven), row(s, heavy)
    assert a["tier"] == "dormant" and b["tier"] != "dormant" and b["strength"] >= DORMANT
    assert h["floor"] <= FLOOR_CAP
    return (f"after 2000 idle beats: 6 uses -> {a['tier']} (floor {a['floor']}), "
            f"7 uses -> {b['tier']} (floor {b['floor']}, can never go dormant), "
            f"1000 uses -> floor capped at {h['floor']}")


def test_summary_stays_flat_as_memory_grows():
    s = fresh("flat")
    rng = random.Random(5)
    vocab = ("auth token schema deploy cache queue billing invoice tenant login retry index "
             "latency alert rollout flag webhook export import backup restore migration").split()
    sizes, actives = [], []
    for beat in range(500):
        for _ in range(4):
            s.remember(" ".join(rng.sample(vocab, 6)), rng.uniform(0.2, 0.8))
        if beat % 2 == 0:
            s.recall(" ".join(rng.sample(vocab, 4)), rng.uniform(0.2, 1.0))
        s.beat()
        if beat % 25 == 0:
            sizes.append(len(s.summary())); actives.append(s.stats())
    st = s.stats()
    assert max(sizes) <= 1200, max(sizes)
    return (f"2000 memories over 500 beats: summary {min(sizes)}-{max(sizes)} chars (~{max(sizes) // 4} tokens); "
            f"now {st['short']} short, {st['intermediate']} intermediate, {st['long']} long, "
            f"{st['dormant']} dormant; storage {st['bytes'] // 1024} KB")


def _worker(args):
    root, seed = args
    s = MemoryStore(root)
    rng = random.Random(seed)
    ids = []
    for i in range(50):
        r = rng.random()
        if r < 0.5 or not ids:
            ids.append(s.remember(f"worker {seed} item {i}", 0.5))
        elif r < 0.8:
            s.use(rng.choice(ids))
        else:
            s.recall(f"worker {seed} item", 0.6)
    return len(ids)


def test_nights_do_not_crowd_out_what_was_learned():
    """In real runs nights made about 5 ideas per waking memory, and listen shows only the top 5 lines."""
    s = MemoryStore(tempfile.mkdtemp())
    real = [s.remember(f"decision {i}: money is integer cents in module {i}", 0.4) for i in range(3)]
    for i in range(8):
        s.remember(f"poem line {i}", 0.9, "poem")
        s.remember(f"dream idea {i} linking cents and packs", 0.9, "dream")
    lines = s.summary().splitlines()
    assert all(any(r in l for l in lines[1:4]) for r in real), lines          # waking first, despite lower strength
    assert not any("poem line" in l for l in lines) and sum("(idea, unconfirmed)" in l for l in lines) == 2
    assert "3 active, 16 ideas from nights" in lines[0]
    a, b = real[0], real[1]
    n = len(s.rows())
    s.sleep(lambda x, y, sim: {"op": "reinforce", "score": 0.9, "insight": "they agree"}, cycles=1,
            pairs_per_cycle=4, plan=[[(a, b)]])
    assert s._load()["m"][a]["dream_links"] == 1                             # the pair was judged...
    assert len(s.rows()) == n                                                 # ...and its reinforce insight added nothing
    return "summary: waking memories first, 2 unconfirmed ideas, no poems; reinforce insights aren't stored"


def test_concurrent_agents():
    s = fresh("conc")
    with mp.Pool(8) as pool:
        made = sum(pool.map(_worker, [(s.root, i) for i in range(8)]))
    assert len(s.rows()) == made
    return f"8 processes x 50 ops: all {made} memories present, index intact"


def life(out):
    """One agent's memory over 300 beats, for the chart."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    s = fresh("life")
    rng = random.Random(9)
    tracked = {
        "one-off fact, revived at beat 180": s.remember("the vendor contract renews in march with a price cap", 0.5),
        "used often, spaced": s.remember("deploys go out tuesday and thursday only", 0.5),
        "crammed: 6 uses in one beat": s.remember("the old api key format starts with sk underscore", 0.5),
        "used 8 times early, then never": s.remember("incident channel is called war room", 0.5),
    }
    ids = list(tracked.values())
    for _ in range(6):
        s.use(ids[2])
    filler = "noise item about lunch parking printers badges wifi coffee".split()
    traj = {k: [] for k in tracked}
    tiers, summ = [], []
    for beat in range(300):
        if beat % 12 == 0 and beat < 250:
            s.use(ids[1])
        if beat < 32 and beat % 4 == 0:
            s.use(ids[3])
        if beat == 180:
            s.recall("when does the vendor contract renew, is there a price cap", 0.95)
        for _ in range(3):
            s.remember(" ".join(rng.sample(filler, 4)), rng.uniform(0.2, 0.6))
        s.beat()
        for k, mid in tracked.items():
            r = row(s, mid)
            traj[k].append((r["strength"], r["tier"]))
        st = s.stats()
        tiers.append([st["short"], st["intermediate"], st["long"], st["dormant"]])
        summ.append(len(s.summary()) / 4)

    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1.5, 1]})
    colors = ["#c0392b", "#2471a3", "#e67e22", "#27ae60"]
    for (k, tr), c in zip(traj.items(), colors):
        ys = [t[0] for t in tr]
        ax[0].plot(range(1, 301), ys, color=c, label=k, lw=1.4)
        dorm = [i + 1 for i, t in enumerate(tr) if t[1] == "dormant"]
        if dorm:
            ax[0].scatter(dorm, [tr[i - 1][0] for i in dorm], color=c, s=4, alpha=0.5)
    ax[0].axhline(DORMANT, color="k", ls=":", lw=0.8)
    ax[0].text(302, DORMANT, "dormant line", fontsize=7, va="center")
    ax[0].set_yscale("log"); ax[0].set_ylim(0.003, 1.2)
    ax[0].set_xlabel("beat"); ax[0].set_ylabel("strength (log)")
    ax[0].set_title("Four memories over 300 beats (dots = dormant)", fontsize=10)
    ax[0].legend(fontsize=7, loc="lower left")
    T = list(zip(*tiers))
    ax[1].stackplot(range(1, 301), T[0], T[1], T[2], T[3],
                    labels=["short", "intermediate", "long", "dormant"],
                    colors=["#f5b041", "#5dade2", "#1f618d", "#d5d8dc"])
    ax[1].set_xlabel("beat"); ax[1].set_ylabel("memories")
    tw = ax[1].twinx()
    tw.plot(range(1, 301), summ, color="k", lw=1.2, label="summary tokens")
    tw.set_ylim(0, max(summ) * 3); tw.set_ylabel("tokens agents read per turn")
    h1, l1 = ax[1].get_legend_handles_labels(); h2, l2 = tw.get_legend_handles_labels()
    ax[1].legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    ax[1].set_title("All memories by tier vs. what agents read", fontsize=10)
    fig.tight_layout()
    path = os.path.join(out, "memory_life.png")
    fig.savefig(path, dpi=150)
    final = {k: tr[-1] for k, tr in traj.items()}
    return path, final, tiers[-1], max(summ)


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
    path, final, tiers, summ = life(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(f"\nlife run -> {path}")
    for k, (s, t) in final.items():
        print(f"  {k:36s} {t:12s} {s:.3f}")
    print(f"  tiers at beat 300 (short, intermediate, long, dormant): {tiers}; summary <= {summ:.0f} tokens")
