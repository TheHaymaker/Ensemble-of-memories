"""An offline stand-in for Claude: drives `ens` the way the skills ask, with no model calls.

It is not meant to be smart. It lets you test the harness and Ensemble's mechanics (fading,
promotion, nights, lessons, family inheritance) quickly and for free, e.g. 20 nights in a minute.
Its judgments are deterministic per run, so two runs on the same Ensemble code match.

Session: listen, recall the task, use what it recalls, remember the task's expected memories.
Night:   reinforce close pairs, add a link for middling ones, a few qualify/tension verdicts;
         poems from word play with low made-up probabilities; one thought-exercise per seed.
"""
import hashlib
import json
import random

WORDS = ["lantern", "tidepool", "abacus", "moth", "granary", "kiln", "ferry", "quarry", "almanac", "loom",
         "hinge", "orchard", "compass", "bellows", "cistern", "weathervane", "thimble", "anvil"]


def _rng(*parts):
    return random.Random(int(hashlib.sha1("|".join(parts).encode()).hexdigest()[:12], 16))


def session(r, project, task):
    calls = ["ens listen"]
    r.ens(project, "listen")
    found = r.ens(project, "recall", task.get("title") or task["prompt"][:80])
    calls.append("ens recall")
    for line in found.splitlines():
        mid = line.split()[0] if line[:1] == "m" and line[1:6].isdigit() else None
        if mid:
            r.ens(project, "use-memory", mid)
            calls.append("ens use-memory")
    for x in task.get("expect", []):
        r.ens(project, "remember", x, "--importance", "0.7")
        calls.append("ens remember")
    r.ens(project, "write-note", f"last task: {task.get('title', task['id'])}")
    calls.append("ens write-note")
    return {"ens_calls": calls, "cost_usd": None, "turns": None, "result": "fake session"}


def night(r, project):
    rng = _rng(r.name, project, r.ens(project, "listen").splitlines()[0])
    calls = []

    pairs = json.loads(r.ens(project, "dream-pairs"))["pairs"]
    calls.append("ens dream-pairs")
    verdicts = []
    for p in pairs:
        a, b, sim = p["a"], p["b"], p["similarity"]
        imagined = "imagined" in (a.get("origin", ""), b.get("origin", "")) or {a.get("src"), b.get("src")} & {
            "poem", "probe", "excursion", "prediction"}
        roll = rng.random()
        if sim >= 0.5:
            op = "reinforce"
        elif sim >= 0.2 and roll < 0.5:
            op = "add"
        elif sim >= 0.2 and roll < 0.6 and not imagined:
            op = "qualify"
        elif roll < 0.03 and not imagined:
            op = "tension"
        else:
            op = "none"
        v = {"a": a["id"], "b": b["id"], "op": op, "score": round(0.6 + 0.4 * sim, 2), "insight": None}
        if op in ("add", "qualify", "tension"):
            v["insight"] = f"{a['text'][:60]} / {b['text'][:60]}: {'linked' if op == 'add' else 'each holds in its own case'}"
        verdicts.append(v)
    out = r.ens(project, "dream-apply", stdin=json.dumps(verdicts))
    calls.append("ens dream-apply")

    poems = json.loads(r.ens(project, "poem-pairs"))["pairs"]
    calls.append("ens poem-pairs")
    ans = []
    for p in poems:
        A, B = p["A"], p["B"]

        def cands(seed):
            return [{"text": f"the {rng.choice(WORDS)} of {seed.split()[min(i, len(seed.split()) - 1)]}",
                     "p": round(rng.uniform(0.01, 0.2), 3)} for i in range(8)]
        ans.append({"A": A["id"], "B": B["id"], "figures": cands(A["text"] + " " + B["text"]),
                    "aliases": {"A": cands(A["text"]), "B": cands(B["text"])},
                    "glosses": {"A": A["text"][:80], "B": B["text"][:80]},
                    "probes": {"A": f"when does '{A['text'][:40]}' stop holding?", "B": None},
                    "verse": f"{rng.choice(WORDS)} and {rng.choice(WORDS)},\n{A['text'][:30]}... {B['text'][:30]}..."})
    if poems:
        out += "\n" + r.ens(project, "poem-apply", stdin=json.dumps(ans))
        calls.append("ens poem-apply")

    seeds = json.loads(r.ens(project, "excursion-seeds"))["seeds"]
    calls.append("ens excursion-seeds")
    notes = [{"seed": s["seed"], "form": "hypothesis" if rng.random() < 0.5 else "thought-exercise",
              "title": f"what if {s['seed'][:40]}", "outcome": "imagined it through", "surprise": "little",
              "verdict": rng.choice(["silly", "plausible", "trivial"]),
              "prediction": f"a later task will touch {s['seed'][:30]}", "spawn": []} for s in seeds]
    if seeds:
        out += "\n" + r.ens(project, "excursion-apply", stdin=json.dumps(notes))
        calls.append("ens excursion-apply")
    return {"ens_calls": calls, "cost_usd": None, "turns": None, "result": out[:2000]}
