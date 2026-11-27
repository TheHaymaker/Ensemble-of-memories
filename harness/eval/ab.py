#!/usr/bin/env python3
"""A/B evaluation: does Ensemble improve outcomes on new work?

    python3 harness/eval/ab.py history ab1                  play the shared history once, with Ensemble
    python3 harness/eval/ab.py trials ab1 --arms ens,off --reps 1 --jobs 4
    python3 harness/eval/ab.py report ab1                   runs/ab1-ab/report.md
    python3 harness/eval/ab.py judge ab1                    optional blind LLM judge of every trial's diff

How it works (see harness/eval/README.md):
  1. `history` plays the spec's history steps with lab.py into runs/BASE (memories and code form).
  2. Each trial copies that frozen run (code, git history, Ensemble home) into its own directory and
     runs one probe task in one arm:
        ens    Ensemble as installed: SessionStart hook, skills, nudge, and the history's memories
        empty  Ensemble installed and nudged, but a fresh empty home (separates the ritual from the content)
        off    no Ensemble at all: no hook, no skills, no nudge, `ens` not on PATH; same repo
  3. Hidden checks (harness/eval/checks/PROBE.py, never visible to sessions) score the result:
     `task:` checks (did it do what was asked) and `mem:` checks (is it consistent with what the
     history decided or was told). Also the project's own tests, cost, turns and time.
  4. For `ens` trials, the transcript shows where each key fact surfaced: the SessionStart hook,
     `ens listen`, `ens recall`, or nowhere. That is the mechanism attribution.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
sys.path.insert(0, HARNESS)
import lab  # noqa: E402

SPEC = os.path.join(HERE, "recall-ab.json")
CHECKS = os.path.join(HERE, "checks")
LOCK = threading.Lock()


def spec(path=None):
    return lab.rd(path or SPEC)


def abdir(base):
    return os.path.join(lab.RUNS, f"{base}-ab")


# ------------------------------------------------------------------ history
def cmd_history(a):
    sp = spec(a.spec)
    scen = {"about": "history for " + os.path.basename(a.spec or SPEC), "projects": sp["projects"],
            "env": sp["env"], "nudge": True, "beats_per_session": 0, "steps": sp["history"]}
    os.makedirs(abdir(a.base), exist_ok=True)
    path = os.path.join(abdir(a.base), "history-scenario.json")
    lab.wr(path, scen)
    argv = [sys.executable, os.path.join(HARNESS, "lab.py"), "play", a.base, path]
    if a.model:
        argv += ["--model", a.model]
    subprocess.run(argv, check=True)


# ------------------------------------------------------------------ forking
def rewrite_paths(root, old, new):
    for d, _, files in os.walk(root):
        if "/.git" in d or d.endswith(".git"):
            continue
        for fn in files:
            p = os.path.join(d, fn)
            try:
                with open(p) as f:
                    s = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            if old in s:
                with open(p, "w") as f:
                    f.write(s.replace(old, new))


def fork(base, tid, arm):
    src = lab.Run(base).need()
    name = f"{base}-ab/trials/{tid}"
    r = lab.Run(name)
    if os.path.exists(r.dir):
        shutil.rmtree(r.dir)
    os.makedirs(r.dir)
    for part in ("app", "bin", "home", "work", "meta.json"):
        s, d = os.path.join(src.dir, part), os.path.join(r.dir, part)
        (shutil.copytree(s, d, symlinks=True) if os.path.isdir(s) else shutil.copy(s, d))
    rewrite_paths(r.dir, src.dir, r.dir)
    if arm == "empty":
        shutil.rmtree(r.home)
        os.makedirs(r.home)
    if arm == "off":
        shutil.rmtree(r.home)
        for p in os.listdir(r.work):
            cl = os.path.join(r.work, p, ".claude")
            shutil.rmtree(os.path.join(cl, "skills"), ignore_errors=True)
            lab.wr(os.path.join(cl, "settings.json"), {"autoMemoryEnabled": False,
                                                       "permissions": {"allow": lab.ALLOWED_TOOLS}})
    return r


def base_env():
    e = {k: v for k, v in os.environ.items() if k not in lab.INHERITED_DROP and not k.startswith("ENSEMBLE_")}
    e["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    return e


# ------------------------------------------------------------------ one trial
def run_trial(base, probe, arm, rep, a):
    tid = f"{probe['id']}-{arm}-{rep}"
    r = fork(base, tid, arm)
    project = probe["project"]
    wd = os.path.join(r.work, project)
    if arm == "off":
        env = base_env()
    else:
        r.ensure_joined(project)        # a child is born now, from its parent's memory as it stands
        env = r.env(project)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wd, capture_output=True, text=True).stdout.strip()
    tpath = os.path.join(r.dir, "transcript.jsonl")
    argv = ["claude", "-p", probe["prompt"], "--output-format", "stream-json", "--verbose",
            "--setting-sources", "project,local", "--permission-mode", "acceptEdits",
            "--allowedTools", *lab.ALLOWED_TOOLS, "--max-turns", str(a.max_turns)]
    if a.model:
        argv += ["--model", a.model]
    if arm != "off":
        argv += ["--append-system-prompt", lab.NUDGE]
    t0 = time.time()
    with open(tpath, "w") as out:
        p = subprocess.run(argv, cwd=wd, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           text=True, timeout=a.timeout)
    secs = round(time.time() - t0, 1)
    res = {}
    for ev in events(tpath):
        if ev.get("type") == "result":
            res = ev
    lab.commit_work(r, project, f"trial {tid}")
    checks = run_checks(probe["id"], wd)
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=wd,
                           capture_output=True, text=True, timeout=300)
    diff = subprocess.run(["git", "diff", head, "HEAD", "--", ".", ":(exclude).claude"], cwd=wd,
                          capture_output=True, text=True).stdout
    with open(os.path.join(r.dir, "diff.patch"), "w") as f:
        f.write(diff)
    row = {"trial": tid, "probe": probe["id"], "arm": arm, "rep": rep, "exit": p.returncode,
           "cost": res.get("total_cost_usd"), "turns": res.get("num_turns"), "secs": secs,
           "error": res.get("is_error"), "final": (res.get("result") or "")[:3000],
           "tests_pass": tests.returncode == 0, "checks": checks,
           "ens_calls": lab.ens_calls(tpath), "surfaced": surfaced(tpath, probe.get("facts", {})),
           "diff_lines": diff.count("\n")}
    with LOCK:
        with open(os.path.join(abdir(base), "results.jsonl"), "a") as f:
            f.write(json.dumps(row) + "\n")
    shutil.rmtree(os.path.join(r.dir, "app"), ignore_errors=True)   # keep work, home, transcript, diff
    return row


def run_checks(pid, wd):
    path = os.path.join(CHECKS, f"{pid}.py")
    env = {**base_env(), "PYTHONPATH": CHECKS, "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run([sys.executable, path], cwd=wd, capture_output=True, text=True, timeout=120, env=env)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"_crash": (p.stdout + p.stderr)[-500:]}


def events(path):
    with open(path) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict):
                yield ev


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(text_of(c.get("text") or c.get("content") or "") if isinstance(c, dict) else str(c)
                         for c in content)
    return ""


def sources(path):
    """Text the session was shown, by where it came from: hook (SessionStart), listen, recall, ens (other),
    and work (everything else it read: files, greps, test output)."""
    kinds, out = {}, {"hook": [], "listen": [], "recall": [], "ens": [], "work": []}
    for ev in events(path):
        if ev.get("type") == "system":
            blob = json.dumps(ev)
            if "hook" in blob.lower():
                out["hook"].append(blob)
            continue
        msg = ev.get("message")
        if not isinstance(msg, dict):
            continue
        for c in msg.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                cmd = (c.get("input") or {}).get("command") or ""
                kinds[c.get("id")] = ("listen" if re.search(r"\bens\s+(listen|--listen)", cmd) else
                                      "recall" if re.search(r"\bens\s+recall", cmd) else
                                      "ens" if re.search(r"\bens\s+", cmd) else "work")
            elif c.get("type") == "tool_result":
                out[kinds.get(c.get("tool_use_id"), "work")].append(text_of(c.get("content")))
            elif c.get("type") == "text" and msg.get("role") == "user":
                out["hook"].append(c.get("text") or "")
    return {k: "\n".join(v) for k, v in out.items()}


def surfaced(path, facts):
    src = sources(path)
    return {name: [k for k in ("hook", "listen", "recall", "ens", "work") if re.search(rx, src[k], re.I)]
            for name, rx in facts.items()}


# ------------------------------------------------------------------ trials
def results(base):
    path = os.path.join(abdir(base), "results.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def cmd_trials(a):
    sp = spec(a.spec)
    probes = [p for p in sp["probes"] if not a.probes or p["id"] in a.probes.split(",")]
    arms = a.arms.split(",")
    done = {r["trial"] for r in results(a.base)}
    todo = []
    for rep in range(1, a.reps + 1):
        for p in probes:
            for arm in arms:                       # interleaved, so time drift hits every arm alike
                if f"{p['id']}-{arm}-{rep}" not in done:
                    todo.append((p, arm, rep))
    lab.say(f"{len(todo)} trials to run ({len(done)} already done)")
    spent = sum(r.get("cost") or 0 for r in results(a.base))
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        futs = {}
        for p, arm, rep in todo:
            futs[ex.submit(run_trial, a.base, p, arm, rep, a)] = (p["id"], arm, rep)
        for fu in cf.as_completed(futs):
            pid, arm, rep = futs[fu]
            try:
                row = fu.result()
                spent += row.get("cost") or 0
                ok = sum(1 for k, v in row["checks"].items() if not k.startswith("_") and v)
                n = sum(1 for k in row["checks"] if not k.startswith("_"))
                lab.say(f"{row['trial']}: checks {ok}/{n}, tests {'pass' if row['tests_pass'] else 'FAIL'}, "
                        f"${row['cost']}, {row['turns']} turns  (total ${spent:.2f})")
            except Exception as e:
                lab.say(f"{pid}-{arm}-{rep}: FAILED {type(e).__name__}: {e}")
    cmd_report(a)


def cmd_rescore(a):
    """Re-run the hidden checks on every finished trial (after a check is added or fixed)."""
    sp = {p["id"]: p for p in spec(a.spec)["probes"]}
    rows = results(a.base)
    for r in rows:
        wd = os.path.join(abdir(a.base), "trials", r["trial"], "work", sp[r["probe"]]["project"])
        r["checks"] = run_checks(r["probe"], wd)
    with open(os.path.join(abdir(a.base), "results.jsonl"), "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    cmd_report(a)


# ------------------------------------------------------------------ judge
JUDGE = """You are grading a code change made by an AI coding session, blind: you don't know how it was set up.

Project: {project}
Task given to the session:
<task>{prompt}</task>

Context a well-informed teammate would know (decisions and requests from earlier work on this project
or its parent project; the session may or may not have known them):
<context>{context}</context>

The session's change (git diff):
<diff>{diff}</diff>

The session's final message:
<final>{final}</final>

Grade on two axes, 1 (poor) to 5 (excellent):
- quality: does the change do the task well and correctly, with sensible tests, without breaking things?
- consistency: does it fit the context above (follows earlier decisions and stated preferences, doesn't redo or contradict them)? 3 if the context doesn't bear on this task.
Answer with JSON only: {{"quality": n, "consistency": n, "why": "one sentence"}}"""

CONTEXT = {
    "recipe-core": ("- Quantities print as kitchen fractions down to eighths (1/3, 1 1/2), never decimals; under 1/8 tsp prints 'a pinch' (the baker's request).\n"
                    "- The baker said: whenever grams are shown, whole grams only, never like '14.2 g'.\n"
                    "- Maintainer's rule: anything recipe_core raises for bad input is a RecipeError (a ValueError subclass).\n"
                    "- The cup is 240 ml (US nutrition labeling), replacing 236.6 ml."),
}
CONTEXT["meal-planner"] = ("meal-planner is a child of recipe-core and vendors its unit code. Its parent's decisions:\n" + CONTEXT["recipe-core"])


def cmd_judge(a):
    sp = {p["id"]: p for p in spec(a.spec)["probes"]}
    path = os.path.join(abdir(a.base), "judge.jsonl")
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            done = {json.loads(l)["trial"] for l in f if l.strip()}
    rows = [r for r in results(a.base) if r["trial"] not in done]
    redact = re.compile(r"\b(ensemble|ens (listen|recall|remember|use-memory)|memor(y|ies)|recall(ed)?)\b", re.I)

    def one(r):
        p = sp[r["probe"]]
        with open(os.path.join(lab.RUNS, f"{a.base}-ab", "trials", r["trial"], "diff.patch")) as f:
            diff = f.read()[:30000]
        prompt = JUDGE.format(project=p["project"], prompt=p["prompt"], context=CONTEXT[p["project"]],
                              diff=diff, final=redact.sub("[…]", r["final"])[:3000])
        out = subprocess.run(["claude", "-p", prompt, "--model", a.judge_model, "--output-format", "json",
                              "--max-turns", "1", "--setting-sources", "local", "--tools", ""],
                             capture_output=True, text=True, env=base_env(), cwd=HERE, timeout=300)
        try:
            j = json.loads(out.stdout)
            txt = j.get("result", "")
            g = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
            g.update(trial=r["trial"], cost=j.get("total_cost_usd"))
        except Exception as e:
            g = {"trial": r["trial"], "error": f"{e}: {out.stdout[-300:]} {out.stderr[-300:]}"}
        with LOCK, open(path, "a") as f:
            f.write(json.dumps(g) + "\n")
        return g
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for g in ex.map(one, rows):
            lab.say(f"judge {g['trial']}: {g.get('quality')}/{g.get('consistency')} {g.get('error', '')[:200]}")
    cmd_report(a)


# ------------------------------------------------------------------ report
def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def fmt(x, d=2):
    return "-" if x is None else f"{x:.{d}f}"


def rate(rows, kind):
    vals = [v for r in rows for k, v in r["checks"].items() if k.startswith(kind + ":") and v is not None]
    return (sum(vals), len(vals))


def cmd_report(a):
    rows = results(a.base)
    sp = spec(a.spec)
    judged = {}
    jp = os.path.join(abdir(a.base), "judge.jsonl")
    if os.path.exists(jp):
        with open(jp) as f:
            for l in f:
                g = json.loads(l)
                if "quality" in g:
                    judged[g["trial"]] = g
    arms = [x for x in ("ens", "empty", "off") if any(r["arm"] == x for r in rows)]
    L = [f"# Does Ensemble improve outcomes? A/B on `{a.base}`", "",
         f"{len(rows)} trials, ${sum(r.get('cost') or 0 for r in rows):.2f} in sessions. Arms: "
         "**ens** = Ensemble with the history's memories; **empty** = Ensemble installed, empty memory; "
         "**off** = no Ensemble. Same frozen repo in every arm.", "",
         "## Overall", "", "| arm | trials | task checks | memory checks | own tests pass | judge quality | judge consistency | turns | cost | secs |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        t, m = rate(rs, "task"), rate(rs, "mem")
        js = [judged[r["trial"]] for r in rs if r["trial"] in judged]
        L.append(f"| {arm} | {len(rs)} | {t[0]}/{t[1]} ({100 * t[0] / max(t[1], 1):.0f}%) | {m[0]}/{m[1]} ({100 * m[0] / max(m[1], 1):.0f}%) | "
                 f"{sum(r['tests_pass'] for r in rs)}/{len(rs)} | {fmt(mean([j['quality'] for j in js]))} | "
                 f"{fmt(mean([j['consistency'] for j in js]))} | {fmt(mean([r['turns'] for r in rs]), 1)} | "
                 f"${fmt(mean([r['cost'] for r in rs]))} | {fmt(mean([r['secs'] for r in rs]), 0)} |")
    L += ["", "## Per probe", ""]
    for p in sp["probes"]:
        prs = [r for r in rows if r["probe"] == p["id"]]
        if not prs:
            continue
        L += [f"### {p['id']} ({p['project']})", "", p["why"], ""]
        names = sorted({k for r in prs for k in r["checks"] if not k.startswith("_")})
        L.append("| check | " + " | ".join(arms) + " |")
        L.append("|---|" + "---|" * len(arms))
        for n in names:
            cells = []
            for arm in arms:
                vs = [r["checks"].get(n) for r in prs if r["arm"] == arm]
                vs = [v for v in vs if v is not None]
                cells.append(f"{sum(vs)}/{len(vs)}" if vs else "-")
            L.append(f"| {n} | " + " | ".join(cells) + " |")
        for lbl, fn in (("own tests pass", lambda r: r["tests_pass"]),):
            L.append(f"| {lbl} | " + " | ".join(f"{sum(fn(r) for r in prs if r['arm'] == arm)}/{sum(1 for r in prs if r['arm'] == arm)}" for arm in arms) + " |")
        L.append("| turns / cost | " + " | ".join(
            f"{fmt(mean([r['turns'] for r in prs if r['arm'] == arm]), 1)} / ${fmt(mean([r['cost'] for r in prs if r['arm'] == arm]))}" for arm in arms) + " |")
        if judged:
            L.append("| judge q / c | " + " | ".join(
                f"{fmt(mean([judged[r['trial']]['quality'] for r in prs if r['arm'] == arm and r['trial'] in judged]), 1)} / "
                f"{fmt(mean([judged[r['trial']]['consistency'] for r in prs if r['arm'] == arm and r['trial'] in judged]), 1)}" for arm in arms) + " |")
        ens = [r for r in prs if r["arm"] == "ens"]
        if ens and p.get("facts"):
            L += ["", "Where key facts surfaced in **ens** trials (hook = SessionStart listen, recall = `ens recall`, work = files it read):", ""]
            for fact in p["facts"]:
                where = [",".join(r["surfaced"].get(fact) or ["nowhere"]) for r in ens]
                L.append(f"- {fact}: " + "; ".join(where))
        L.append("")
    L += ["## Ensemble use in ens trials", "", "| trial | ens calls |", "|---|---|"]
    for r in rows:
        if r["arm"] != "off":
            L.append(f"| {r['trial']} | {', '.join(r['ens_calls']) or '-'} |")
    out = os.path.join(abdir(a.base), "report.md")
    with open(out, "w") as f:
        f.write("\n".join(L) + "\n")
    lab.say(f"report: {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("history"); h.add_argument("base"); h.add_argument("--model")
    t = sub.add_parser("trials"); t.add_argument("base")
    t.add_argument("--arms", default="ens,off"); t.add_argument("--reps", type=int, default=1)
    t.add_argument("--probes"); t.add_argument("--jobs", type=int, default=4); t.add_argument("--model")
    t.add_argument("--max-turns", type=int, default=40); t.add_argument("--timeout", type=int, default=1500)
    j = sub.add_parser("judge"); j.add_argument("base"); j.add_argument("--judge-model", default="sonnet")
    j.add_argument("--jobs", type=int, default=4)
    r = sub.add_parser("report"); r.add_argument("base")
    rs = sub.add_parser("rescore"); rs.add_argument("base")
    a = ap.parse_args()
    {"history": cmd_history, "trials": cmd_trials, "judge": cmd_judge, "report": cmd_report, "rescore": cmd_rescore}[a.cmd](a)


if __name__ == "__main__":
    main()
