#!/usr/bin/env python3
"""poem_ab: does a woven poem in the night's context make dreams, probes and excursions more useful?

Two arms start from the identical memory and code state and each runs one real night per project:

    control  ENSEMBLE_NIGHT_POEMS=0: today's night (dreams, one-line poems, excursions)
    poems    ENSEMBLE_NIGHT_POEMS=1: first weave earlier one-line figures into one longer poem,
             then dreams, poems and excursions each see that poem as a lens

    python3 harness/poem_ab.py base   pab1     sessions, a first night (makes figures), more sessions
    python3 harness/poem_ab.py arms   pab1     fork the base into both arms; one night per project in each
    python3 harness/poem_ab.py judge  pab1     a blind Claude judge checks every item against the code
    python3 harness/poem_ab.py report pab1     runs/pab1-report.md and .json
    python3 harness/poem_ab.py all    pab1     all four in order (each step resumes; finished parts are kept)

What is measured, per arm (items from both arms are shuffled together, so the judge can't tell them apart):
    grounded   probes: the edge case it names really breaks or bends the memory in this code;
               dream insights and excursion claims: true of this code (the judge reads or runs it)
    novel      says something the memories before the night did not
    useful     0-2: would help a later session working on this code decide something
    valuable   grounded and novel and useful >= 1
plus counts (verdicts by op, insights, probes, excursions), word overlap with earlier memories
(lower is newer), and cost and turns per night.
"""
import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lab  # noqa: E402

PROJECTS = ["recipe-core", "pantry-tracker", "grocery-bot"]
BEFORE, BETWEEN = 3, 1                     # sessions before the first night, and between the nights
ARMS = {"control": {"ENSEMBLE_NIGHT_POEMS": "0"}, "poems": {"ENSEMBLE_NIGHT_POEMS": "1"}}
BASE_ENV = {"ENSEMBLE_NIGHT_POEMS": "0", "ENSEMBLE_EXCURSIONS": "3"}
JUDGE_TOOLS = ["Read", "Glob", "Grep", "Write", "Bash(python3:*)", "Bash(python:*)", "Bash(ls:*)", "Bash(cat:*)"]


def args(**kw):
    d = dict(fake=False, model=None, max_turns=60, timeout=2400)
    d.update(kw)
    return SimpleNamespace(**d)


def out_dir(name):
    d = os.path.join(lab.RUNS, f"{name}-ab")
    os.makedirs(d, exist_ok=True)
    return d


def steps_done(r):
    return {(e.get("step"), e.get("project"), e.get("task")) for e in read_log(r)}


def read_log(r):
    p = os.path.join(r.dir, "log.jsonl")
    return [json.loads(ln) for ln in open(p)] if os.path.exists(p) else []


# ------------------------------------------------------------------ base and arms
def cmd_base(a):
    r = lab.Run(f"{a.name}-base")
    if not r.exists():
        lab.new_run(r.name, a.projects, BASE_ENV, "poem_ab")
    ns, done = args(model=a.model, fake=a.fake), steps_done(r)
    for p in a.projects:
        ids = [t["id"] for t in lab.tasks_of(p)]
        for t in ids[:BEFORE]:
            if ("session", p, t) not in done:
                lab.do_session(r, p, t, ns)
        if ("night", p, None) not in done:
            lab.do_night(r, p, ns)
        for t in ids[BEFORE:BEFORE + BETWEEN]:
            if ("session", p, t) not in done:
                lab.do_session(r, p, t, ns)
    lab.write_report(r)
    for p in a.projects:
        idx = index_of(r.home, p)
        figs = [k for k, m in idx["m"].items() if m.get("src") == "poem"] if idx else []
        lab.say(f"{p}: {len(idx['m']) if idx else 0} memories, {len(figs)} one-line figures to weave")


def cmd_arms(a):
    base = lab.Run(f"{a.name}-base").need()
    runs = {}
    for arm, env in ARMS.items():
        r = lab.Run(f"{a.name}-{arm}")
        runs[arm] = r if r.exists() else lab.fork_run(base.name, r.name, env)

    def go(arm, r):
        for p in a.projects:
            if night_entry(r, p) is None:
                lab.do_night(r, p, args(model=a.model, fake=a.fake))
    ts = [threading.Thread(target=go, args=(arm, r)) for arm, r in runs.items()]
    [t.start() for t in ts]
    [t.join() for t in ts]


def night_entry(r, project, after_fork=True):
    """The log entry of this run's own night for project (after the fork, not the base's first night)."""
    log, forked = read_log(r), False
    for e in log:
        if e.get("step") == "fork":
            forked = True
        elif e.get("step") == "night" and e.get("project") == project and (forked or not after_fork):
            return e
    return None


# ------------------------------------------------------------------ reading what a night produced
def member_dir(home, project):
    ds = sorted(glob.glob(os.path.join(home, "projects", f"{project}*", "memory", "conductor")))
    return ds[-1] if ds else None


def index_of(home, project):
    d = member_dir(home, project)
    return lab.rd(os.path.join(d, "index.json")) if d else None


def text_of(home, project, mid):
    d = member_dir(home, project)
    p = os.path.join(d, "memories", f"{mid}.md") if d else ""
    return open(p).read().strip() if os.path.exists(p) else None


def answers(transcript):
    """Every JSON answer the night wrote for an apply step, from Write calls in the transcript."""
    out = []
    for line in open(transcript):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        for c in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Write":
                inp = c.get("input") or {}
                if str(inp.get("file_path", "")).endswith(".ensemble-answer.json"):
                    try:
                        out.append(json.loads(inp.get("content") or ""))
                    except ValueError:
                        pass
    return out


def classify(ans):
    if isinstance(ans, dict):
        return "weave" if "text" in ans else None, ans
    if not ans or not isinstance(ans[0], dict):
        return None, ans
    k = ans[0]
    return ("dream" if "op" in k else "poem" if "figures" in k else "excursion" if "seed" in k else None), ans


def night_items(r, project, before_texts):
    """What one night produced, as judgeable items plus counts."""
    e = night_entry(r, project)
    if not e or not e.get("transcript"):
        return None
    by = {"dream": [], "poem": [], "excursion": [], "weave": None}
    for ans in answers(os.path.join(r.dir, e["transcript"])):
        kind, v = classify(ans)
        if kind == "weave":
            by["weave"] = v
        elif kind:
            by[kind] = v                                     # the last answer of each kind is the applied one
    tx = lambda mid: before_texts.get(mid) or text_of(r.home, project, mid) or mid
    items, counts = [], {"ops": {}, "figures": 0, "probes": 0, "excursions": 0, "predictions": 0}
    for v in by["dream"]:
        op = v.get("op") or "none"
        counts["ops"][op] = counts["ops"].get(op, 0) + 1
        if op in ("add", "qualify", "tension", "substitute", "subtract"):
            items.append({"kind": "dream", "op": op, "a": tx(v.get("a")), "b": tx(v.get("b")),
                          "keep": tx(v["keep"]) if v.get("keep") else None, "insight": v.get("insight")})
    for w in by["poem"]:
        counts["figures"] += 1 if w.get("figures") else 0
        for side in ("A", "B"):
            probe = (w.get("probes") or {}).get(side)
            if probe:
                counts["probes"] += 1
                items.append({"kind": "probe", "memory": tx(w.get(side)), "probe": probe})
    for n in by["excursion"]:
        counts["excursions"] += 1
        counts["predictions"] += 1 if n.get("prediction") else 0
        items.append({"kind": "excursion", "seed": n.get("seed"), "form": n.get("form"), "title": n.get("title"),
                      "outcome": n.get("outcome"), "ran": n.get("ran"), "prediction": n.get("prediction")})
    return {"items": items, "counts": counts, "weave": by["weave"], "cost": e.get("cost_usd"), "turns": e.get("turns")}


def base_memories(name, project):
    base = lab.Run(f"{name}-base")
    idx = index_of(base.home, project) or {"m": {}}
    return {k: text_of(base.home, project, k) or m.get("head", "") for k, m in idx["m"].items()}


# ------------------------------------------------------------------ the blind judge
JUDGE = """You are grading the output of an AI memory system's "night" for the project in this folder.
Each item below is a claim, question or idea the night produced about THIS code. Check each one
against the code here: read it, and where a quick check settles it, run a throwaway Python snippet
(python3 -c, or a script you write under /tmp; never edit project files).

Fields to give for every item:
- "grounded": "yes" | "no" | "unclear".
    probe: "yes" if the edge case or condition it names really does break or bend the memory it
    probes, in this code (e.g. the input really is mishandled or the rule really has that exception);
    "no" if the memory holds there. dream: "yes" if the insight (or the keep/drop choice for
    substitute/subtract, or the conflict for tension) is true of this code. excursion: "yes" if its
    outcome and prediction are consistent with this code. "unclear" if you cannot tell.
- "novel": 1 if it says something the EARLIER MEMORIES below do not already say, else 0.
- "useful": 0, 1 or 2: would it help a later session working on this code decide or catch something?
  0 = no (vague, wrong, a restatement, a whimsy); 1 = somewhat; 2 = clearly.
- "checked": "ran" | "read" | "reasoned".
- "why": at most 20 words.

EARLIER MEMORIES (what was known before the night):
{memories}

ITEMS:
{items}

Write your grades as JSON to the file {out} with the Write tool, exactly this shape and one entry per item:
{{"grades": [{{"id": "J01", "grounded": "yes", "novel": 1, "useful": 2, "checked": "ran", "why": "..."}}]}}
Then reply "done"."""


def render(i, item):
    k = item["kind"]
    if k == "probe":
        body = f"PROBE of memory \"{item['memory']}\": {item['probe']}"
    elif k == "dream":
        body = f"DREAM verdict {item['op']} on A=\"{item['a']}\" and B=\"{item['b']}\""
        if item.get("keep"):
            body += f"; keep=\"{item['keep']}\""
        if item.get("insight"):
            body += f"; insight: {item['insight']}"
    else:
        body = (f"EXCURSION ({item.get('form')}) \"{item.get('title')}\" from seed \"{item.get('seed')}\": "
                f"{item.get('outcome')}")
        if item.get("ran"):
            body += f" Ran: {item['ran']}"
        if item.get("prediction"):
            body += f" Prediction: {item['prediction']}"
    return f"{i}. {body}"


def cmd_judge(a):
    od = out_dir(a.name)
    rng = random.Random(a.seed)
    for p in a.projects:
        res_path = os.path.join(od, f"judge-{p}.json")
        if os.path.exists(res_path):
            continue
        before = base_memories(a.name, p)
        pool = []
        for arm in ARMS:
            got = night_items(lab.Run(f"{a.name}-{arm}"), p, before)
            for it in (got or {}).get("items", []):
                pool.append(dict(it, arm=arm))
        rng.shuffle(pool)
        for n, it in enumerate(pool, 1):
            it["id"] = f"J{n:02d}"
        # judge in a fresh copy of the code as it stood before the nights
        jdir = os.path.join(od, "judge-work", p)
        if not os.path.exists(jdir):
            shutil.copytree(os.path.join(lab.Run(f"{a.name}-base").work, p), jdir,
                            ignore=shutil.ignore_patterns(".claude", ".git", ".ensemble*"))
        out = os.path.join(jdir, ".judge.json")
        prompt = JUDGE.format(memories="\n".join(f"- {t}" for t in before.values() if t),
                              items="\n".join(render(it["id"], it) for it in pool), out=out)
        with open(os.path.join(od, f"judge-{p}-prompt.txt"), "w") as f:
            f.write(prompt)
        lab.say(f"judge: {p}, {len(pool)} items")
        argv = ["claude", "-p", prompt, "--output-format", "json", "--setting-sources", "project,local",
                "--permission-mode", "acceptEdits", "--allowedTools", *JUDGE_TOOLS, "--max-turns", str(a.max_turns)]
        if a.model:
            argv += ["--model", a.model]
        env = {k: v for k, v in os.environ.items() if k not in lab.INHERITED_DROP}
        proc = subprocess.run(argv, cwd=jdir, env=env, capture_output=True, text=True, timeout=3600,
                              stdin=subprocess.DEVNULL)
        meta = {}
        try:
            meta = json.loads(proc.stdout)
        except ValueError:
            pass
        grades = (lab.rd(out) or {}).get("grades", [])
        lab.wr(res_path, {"items": pool, "grades": grades, "cost_usd": meta.get("total_cost_usd"),
                          "turns": meta.get("num_turns"), "result": (meta.get("result") or proc.stderr)[-500:]})
        lab.say(f"judge: {p} graded {len(grades)}/{len(pool)}, cost {meta.get('total_cost_usd')}")


# ------------------------------------------------------------------ report
WORD = re.compile(r"[a-z0-9]{3,}")


def overlap_with(text, earlier):
    w = set(WORD.findall((text or "").lower()))
    if not w:
        return 0.0
    return max((len(w & set(WORD.findall(e.lower()))) / len(w) for e in earlier if e), default=0.0)


def item_text(it):
    return it.get("probe") or it.get("insight") or " ".join(str(it.get(k) or "") for k in ("title", "outcome", "prediction"))


def fisher_two_sided(a, b, c, d):
    """2x2 table [[a, b], [c, d]]: two-sided Fisher exact p."""
    from math import comb
    n1, n2, k, n = a + b, c + d, a + c, a + b + c + d
    pr = lambda x: comb(n1, x) * comb(n2, k - x) / comb(n, k)
    p0 = pr(a)
    return min(1.0, sum(pr(x) for x in range(max(0, k - n2), min(k, n1) + 1) if pr(x) <= p0 + 1e-12))


def cmd_report(a):
    od = out_dir(a.name)
    rows, nights, weaves = [], {}, {}
    for p in a.projects:
        before = base_memories(a.name, p)
        for arm in ARMS:
            got = night_items(lab.Run(f"{a.name}-{arm}"), p, before)
            if got:
                nights[(arm, p)] = got
                if got["weave"]:
                    weaves[p] = got["weave"]
        j = lab.rd(os.path.join(od, f"judge-{p}.json"))
        if not j:
            continue
        g = {x["id"]: x for x in j["grades"]}
        for it in j["items"]:
            x = g.get(it["id"], {})
            rows.append(dict(it, project=p, grounded=x.get("grounded"), novel=x.get("novel"), useful=x.get("useful"),
                             checked=x.get("checked"), why=x.get("why"),
                             overlap=round(overlap_with(item_text(it), before.values()), 2)))

    def agg(sel):
        n = len(sel)
        graded = [r for r in sel if r["grounded"] is not None]
        val = [r for r in graded if r["grounded"] == "yes" and r["novel"] == 1 and (r["useful"] or 0) >= 1]
        return {"n": n, "graded": len(graded),
                "grounded": sum(r["grounded"] == "yes" for r in graded),
                "novel": sum(r["novel"] == 1 for r in graded),
                "useful_mean": round(sum(r["useful"] or 0 for r in graded) / len(graded), 2) if graded else None,
                "useful2": sum((r["useful"] or 0) == 2 for r in graded),
                "valuable": len(val),
                "overlap_mean": round(sum(r["overlap"] for r in sel) / n, 2) if n else None}

    summary = {}
    for kind in ("probe", "dream", "excursion", "all"):
        for arm in ARMS:
            sel = [r for r in rows if r["arm"] == arm and (kind == "all" or r["kind"] == kind)]
            summary[f"{kind}/{arm}"] = agg(sel)
    tests = {}
    for kind in ("probe", "dream", "excursion", "all"):
        c, t = summary[f"{kind}/control"], summary[f"{kind}/poems"]
        for metric in ("grounded", "valuable"):
            tests[f"{kind}/{metric}"] = round(fisher_two_sided(t[metric], t["graded"] - t[metric],
                                                               c[metric], c["graded"] - c[metric]), 3) \
                if c["graded"] and t["graded"] else None

    L = [f"# Woven poems in the night's context: {a.name}", "",
         "Two arms forked from one memory and code state; one real night per project in each. Items from both "
         "arms were shuffled together and graded blind by a Claude judge that read and ran the code.", "",
         "## Per item", "",
         "| kind | arm | items | graded | grounded | novel | useful (mean) | useful=2 | valuable | overlap with earlier |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    pct = lambda x, n: f"{x} ({round(100 * x / n)}%)" if n else "0"
    for kind in ("probe", "dream", "excursion", "all"):
        for arm in ARMS:
            s = summary[f"{kind}/{arm}"]
            L.append(f"| {kind} | {arm} | {s['n']} | {s['graded']} | {pct(s['grounded'], s['graded'])} | "
                     f"{pct(s['novel'], s['graded'])} | {s['useful_mean']} | {s['useful2']} | "
                     f"{pct(s['valuable'], s['graded'])} | {s['overlap_mean']} |")
    L += ["", "valuable = grounded, novel and useful >= 1. Fisher exact p (poems vs control): " +
          ", ".join(f"{k} {v}" for k, v in tests.items() if v is not None), "",
          "## Per night", "", "| project | arm | cost | turns | verdicts by op | probes | excursions | predictions | valuable |",
          "|---|---|---|---|---|---|---|---|---|"]
    for p in a.projects:
        for arm in ARMS:
            n = nights.get((arm, p))
            if not n:
                continue
            v = sum(1 for r in rows if r["project"] == p and r["arm"] == arm and r["grounded"] == "yes"
                    and r["novel"] == 1 and (r["useful"] or 0) >= 1)
            ops = ", ".join(f"{k} {c}" for k, c in sorted(n["counts"]["ops"].items()))
            L.append(f"| {p} | {arm} | {n['cost']} | {n['turns']} | {ops} | {n['counts']['probes']} | "
                     f"{n['counts']['excursions']} | {n['counts']['predictions']} | {v} |")
    if weaves:
        L += ["", "## The woven poems (poems arm)", ""]
        for p, w in weaves.items():
            L += [f"**{p}: {w.get('title')}**", "", *[f"> {ln}" if ln else ">" for ln in (w.get("text") or "").splitlines()], ""]
    L += ["## Every graded item", "", "| project | arm | kind | item | grounded | novel | useful | why |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (r["project"], r["kind"], r["arm"])):
        t = item_text(r).replace("|", "/").replace("\n", " ")[:160]
        L.append(f"| {r['project']} | {r['arm']} | {r['kind']} | {t} | {r['grounded']} | {r['novel']} | {r['useful']} | "
                 f"{(r['why'] or '').replace('|', '/')} |")
    path = os.path.join(od, "report.md")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    lab.wr(os.path.join(od, "report.json"), {"summary": summary, "fisher": tests, "rows": rows,
                                              "nights": {f"{k[0]}/{k[1]}": v for k, v in nights.items()}})
    lab.say(f"report: {path}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="poem_ab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["base", "arms", "judge", "report", "all"])
    ap.add_argument("name")
    ap.add_argument("--projects", default=",".join(PROJECTS))
    ap.add_argument("--model")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-turns", type=int, default=80)
    ap.add_argument("--fake", action="store_true", help="offline stand-in for the sessions and nights (tests the plumbing)")
    a = ap.parse_args(argv)
    a.projects = a.projects.split(",")
    for step in (["base", "arms", "judge", "report"] if a.cmd == "all" else [a.cmd]):
        globals()[f"cmd_{step}"](a)


if __name__ == "__main__":
    main()
