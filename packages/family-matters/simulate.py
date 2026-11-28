"""A 60-beat run of nine scripted agents, measured three ways.

The same events (status notes and votes) are carried by:
  thread    a shared message log (each note and vote is a message)
  markdown  one overwritten .md file per agent (note + votes)
  ensemble  the WAV (notes in parts, votes in the score)

The conductor's reading cost per beat is measured for each, in tokens (approximated
as characters / 4). Agents are scripted, not LLMs: this measures the protocol, not
model behaviour.
"""
import json
import os
import random
import sys

import numpy as np

from ensemble import Ensemble
from tools import Player

ROSTER = ["conductor", "strings", "brass", "woodwinds", "percussion", "keys", "harp", "choir", "soloist"]
PLAYERS = ROSTER[1:]
BEATS = 60
OPENS = {0: [("auth-first", None), ("db", ["postgres", "sqlite", "dynamo"])],
         10: [("rotate-tokens", None)], 20: [("api-stable", None)],
         30: [("ship-v1", None)], 40: [("split-services", None)]}
CLOSE_AFTER = 25
CRASH = ("woodwinds", 30)
CHEAT = ("harp", 45)
tok = lambda s: len(s) / 4

WORDS = ("schema migration token refresh retry backoff endpoint contract cache invalidation "
         "login signup webhook queue worker index latency p95 flaky test fixture rollout flag "
         "billing invoice tenant quota rate-limit dashboard alert trace span").split()


def belief(rng, agent, q, beat):
    i = PLAYERS.index(agent)
    if q == "auth-first":
        return ("yes" if i < 6 else "no"), 0.7
    if q == "rotate-tokens":                    # split, then resolves at beat 25
        return ("yes" if i % 2 == 0 or (beat >= 25 and i < 5) else "no"), 0.8
    if q == "api-stable":                       # confident minority vs unsure majority
        return ("no", 1.0) if i < 2 else ("yes", 0.15)
    if q == "ship-v1":
        return "yes", 0.9
    if q == "split-services":                   # stays split: a real conflict
        return ("yes" if i % 2 else "no"), 0.9
    if q == "db":
        return (["postgres"] * 5 + ["sqlite"] * 2 + ["dynamo"])[i], 0.8


def main(out, backend="audio", quiet=False):
    if backend == "audio":
        path = os.path.join(out, "run.wav")
        for f in (path, path + ".lock"):
            if os.path.exists(f):
                os.remove(f)
        ens = Ensemble(path, ROSTER)
        storage = lambda: os.path.getsize(path)
    else:
        import shutil
        from mdensemble import MdEnsemble
        path = os.path.join(out, "run_md")
        shutil.rmtree(path, ignore_errors=True)
        ens = MdEnsemble(path, ROSTER)
        storage = ens.size
    cond = Player(ens, "conductor")
    players = {a: Player(ens, a) for a in PLAYERS}
    rng = random.Random(42)

    thread, md = [], {a: {"note": "", "votes": {}} for a in PLAYERS}
    open_q, ledger = {}, {}
    rows, lean_hist = [], {}
    prev_conflicts = set()
    for beat in range(BEATS):
        # conductor opens / closes questions
        for qid, opts in OPENS.get(beat, []):
            cond.open_question(qid, opts); open_q[qid] = beat; ledger[qid] = {}
            thread.append(f"[b{beat}] conductor opens '{qid}'" + (f" options {opts}" if opts else ""))
        for qid, t0 in list(open_q.items()):
            if beat - t0 == CLOSE_AFTER:
                cond.close_question(qid); del open_q[qid]; del ledger[qid]
                for a in PLAYERS:
                    md[a]["votes"].pop(qid, None)
                thread.append(f"[b{beat}] conductor closes '{qid}'")
        new_msgs, changed_md = [], set()
        # players act
        for a, p in players.items():
            if a == CRASH[0] and beat >= CRASH[1]:
                continue
            if rng.random() < 0.5:
                text = f"{a} @b{beat}: " + " ".join(rng.choice(WORDS) for _ in range(rng.randint(25, 60)))
                p.write_note(text)
                md[a]["note"] = text; changed_md.add(a)
                new_msgs.append(f"[b{beat}] {a}: {text}")
            for qid, t0 in open_q.items():
                if (beat - t0) % 5 == 0:                     # vote on open, then re-affirm every 5 beats
                    ans, conf = belief(rng, a, qid, beat)
                    r = p.vote(qid, ans, conf)
                    assert not r.startswith("error"), r
                    ledger[qid][a] = (ans, conf, beat)
                    md[a]["votes"][qid] = f"{ans} ({conf}, beat {beat})"; changed_md.add(a)
                    new_msgs.append(f"[b{beat}] {a} votes {ans} ({conf}) on '{qid}'")
        if beat == CHEAT[1] and backend == "audio":        # a faulty agent plays an undeclared vote
            with ens._txn() as spec:
                reg = ens._reg(spec)
                ens._play(spec, ens._contrib(reg["q"]["ship-v1"], -1, 1.0, reg["t"], reg["t"]))
        elif beat == CHEAT[1]:                              # markdown: someone hand-edits the summary
            sp = os.path.join(path, "score.md")
            text = open(sp).read().replace('"verdict":"yes"', '"verdict":"no"', 1)
            open(sp, "w").write(text)
        thread.extend(new_msgs)

        # --- what the conductor reads this beat ---
        heard = cond.listen()
        audit = cond.audit()
        st = ens.state()["score"]
        conflicts = {q for q, r in st.items() if r.get("conflict")}
        reads = ""
        if conflicts - prev_conflicts:                       # a new conflict: read the changed parts
            changed = [l for l in heard.splitlines()[0].split("changed: ")[1].split(" |")[0].split(", ") if l != "none"]
            reads = "\n".join(cond.read_part(c.split(" v")[0]) for c in changed)
        prev_conflicts = conflicts
        ens_tokens = tok(heard) + tok(audit) + tok(reads)
        md_render = lambda a: (f"# {a}\n{md[a]['note']}\n\n## votes\n"
                               + "".join(f"- {q}: {v}\n" for q, v in md[a]["votes"].items()))
        md_tokens = sum(tok(md_render(a)) for a in changed_md)
        thread_tokens = sum(tok(m) for m in new_msgs)

        # ground truth from the ledger (decayed), to check the score's verdicts
        correct = total = 0
        for qid, votes in ledger.items():
            if qid == "db" or not votes:
                continue
            net = sum((1 if v[0] == "yes" else -1) * v[1] * ens.gamma ** (beat - v[2])
                      for a, v in votes.items())
            w = sum(v[1] * ens.gamma ** (beat - v[2]) for v in votes.values())
            truth = "split" if abs(net / w) < 0.25 else ("yes" if net > 0 else "no")
            ok = st[qid]["verdict"] == truth or (backend == "audio" and qid == "ship-v1" and beat >= CHEAT[1])
            if not ok:
                print(f"  mismatch beat {beat} {qid}: score {st[qid]['verdict']} {st[qid]['lean']:+.3f}, ledger {truth} {net / w:+.3f}")
            correct += ok
            total += 1
            lean_hist.setdefault(qid, {})[beat] = st[qid]["lean"]
        ens.beat()
        rows.append({"beat": beat, "thread_tokens": thread_tokens, "md_tokens": md_tokens,
                     "ens_tokens": ens_tokens,
                     "thread_bytes": sum(len(m.encode()) for m in thread),
                     "md_bytes": sum(len(md_render(a).encode()) for a in PLAYERS),
                     "ens_bytes": storage(),
                     "verdicts_correct": f"{correct}/{total}", "audit": audit,
                     "listen_sample": heard if beat in (12, 45) else None})
    json.dump(rows, open(os.path.join(out, f"run_{backend}.json"), "w"), indent=1)
    if quiet:
        return rows
    plot(rows, lean_hist, os.path.join(out, "benchmark.png"))

    T = lambda k: sum(r[k] for r in rows)
    print(f"conductor reading over {BEATS} beats (tokens ~ chars/4):")
    print(f"  thread   {T('thread_tokens'):8.0f}   storage {rows[-1]['thread_bytes']:7d} B and growing")
    print(f"  markdown {T('md_tokens'):8.0f}   storage {rows[-1]['md_bytes']:7d} B flat")
    print(f"  ensemble {T('ens_tokens'):8.0f}   storage {rows[-1]['ens_bytes']:7d} B fixed")
    ok = sum(int(r["verdicts_correct"].split("/")[0]) for r in rows)
    tot = sum(int(r["verdicts_correct"].split("/")[1]) for r in rows)
    print(f"score verdicts matching the ledger: {ok}/{tot}")
    print("audit at beat 44:", rows[44]["audit"], "| beat 45:", rows[45]["audit"])
    print("\nwhat the conductor hears at beat 12:\n" + rows[12]["listen_sample"])
    print("\nat beat 45:\n" + rows[45]["listen_sample"])


def plot(rows, lean_hist, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    b = [r["beat"] for r in rows]
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2))
    c = {"thread": "#c0392b", "markdown": "#7f8c8d", "ensemble": "#2471a3"}
    for k, key in (("thread", "thread_tokens"), ("markdown", "md_tokens"), ("ensemble", "ens_tokens")):
        ax[0].plot(b, [r[key] for r in rows], color=c[k], label=k)
        ax[1].plot(b, np.cumsum([r[key] for r in rows]), color=c[k], label=k)
    ax[0].set_title("Conductor tokens read per beat", fontsize=10)
    ax[1].set_title("Cumulative tokens (if kept in context)", fontsize=10)
    for a in ax[:2]:
        a.set_xlabel("beat"); a.legend(fontsize=8)
    for qid, h in lean_hist.items():
        ks = sorted(h)
        ax[2].plot(ks, [h[k] for k in ks], label=qid)
    ax[2].axhspan(-0.25, 0.25, color="#f5e6a8", alpha=0.6)
    ax[2].axvline(CRASH[1], color="#999", ls=":"); ax[2].text(CRASH[1] + 0.5, -0.95, "woodwinds\ncrashes", fontsize=7)
    ax[2].axvline(CHEAT[1], color="#999", ls=":"); ax[2].text(CHEAT[1] + 0.5, -0.95, "harp plays\nundeclared no", fontsize=7)
    ax[2].set_ylim(-1, 1); ax[2].set_xlabel("beat"); ax[2].legend(fontsize=7, loc="upper left")
    ax[2].set_title("Lean of each question, read from the score", fontsize=10)
    fig.tight_layout(); fig.savefig(png, dpi=150)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".", sys.argv[2] if len(sys.argv) > 2 else "audio")
