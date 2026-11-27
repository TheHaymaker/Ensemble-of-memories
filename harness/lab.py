#!/usr/bin/env python3
"""lab: run Claude sessions against the test projects with Ensemble, in an isolated home per run.

    python3 harness/lab.py setup                         one-time: a venv with Ensemble's deps (.lab/venv)
    python3 harness/lab.py play saga1 harness/scenarios/family-saga.json     run a whole scenario
    python3 harness/lab.py play smoke harness/scenarios/smoke.json --fake    same, no Claude (offline stand-in)
    python3 harness/lab.py play saga4 harness/scenarios/family-saga.json --env ENSEMBLE_EMBEDDER=hybrid
    python3 harness/lab.py report saga1                  write runs/saga1/report.md

Step by step:
    new RUN [--projects a,b] [--env K=V]...             make runs/RUN: frozen Ensemble copy, work copies, empty home
    session RUN PROJECT TASK_ID [--prompt "..."]        one headless Claude session on one task
    night RUN PROJECT                                    one headless /ensemble-night
    reunion RUN | milestone RUN PROJECT "note" | approve-generation RUN PROJECT
    ens RUN PROJECT -- <ens args>                        run `ens` as that project, in that run's home
    claude RUN PROJECT                                   open an interactive Claude in that project, same setup
    snapshot RUN LABEL | report RUN | list

Nothing touches ~/.ensemble or ~/.claude: each run has its own ENSEMBLE_HOME, its own copy of
Ensemble's code (so later edits don't change a run halfway), and project-level skills and hook
inside each work copy. See harness/README.md.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PKG = os.path.join(REPO, "packages", "ensemble")
TEST_PROJECTS = os.path.join(REPO, "test-projects")
RUNS = os.environ.get("LAB_RUNS", os.path.join(REPO, "runs"))
VENV = os.environ.get("LAB_VENV", os.path.join(REPO, ".lab", "venv"))
VPY = os.path.join(VENV, "bin", "python")

# Tools a headless session may use without asking. Work copies are throwaway, but Bash is still
# your machine, so it is limited to the commands a session on these projects needs.
ALLOWED_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "TodoWrite", "Skill",
                 "Bash(ens:*)", "Bash(python3:*)", "Bash(python:*)", "Bash(git:*)",
                 "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(grep:*)", "Bash(mkdir:*)"]

# Guess: without a nudge, Claude may not reach for the ensemble skill in a short -p task. The
# nudge names the skill and nothing else; scenarios can turn it off ("nudge": false) to measure that.
NUDGE = ("This project uses Ensemble for long-lived memory (the `ensemble` skill, `ens` in Bash). "
         "Use it as the skill describes.")
INHERITED_DROP = ("CLAUDE_MEMORY_STORES", "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE", "CLAUDE_ADDITIONAL_DIRECTORIES",
                  "CLAUDE_CODE_CHILD_NOTES_DIR",
                  # set when the harness itself runs inside a cloud Claude session; with them, project
                  # hooks (the SessionStart `ens --listen`) silently don't run
                  "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_IGNORE_PERSISTED_TRUST")
NIGHT_PROMPT = "Run the ensemble-night skill now: dreams, poems and excursions. Then summarize what changed."


# ------------------------------------------------------------------ helpers
def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rd(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def wr(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(data, f, indent=2)
    os.replace(path + ".tmp", path)


def say(msg):
    print(f"[lab] {msg}", flush=True)


def family_spec():
    return rd(os.path.join(TEST_PROJECTS, "family.json"))["projects"]


def tasks_of(project):
    return rd(os.path.join(TEST_PROJECTS, project, "tasks.json"), {"tasks": []})["tasks"]


def task(project, tid):
    for t in tasks_of(project):
        if t["id"] == tid:
            return t
    raise SystemExit(f"no task {tid} in test-projects/{project}/tasks.json")


class Run:
    def __init__(self, name):
        self.name, self.dir = name, os.path.join(RUNS, name)
        self.home = os.path.join(self.dir, "home")
        self.app = os.path.join(self.dir, "app")
        self.bin = os.path.join(self.dir, "bin")
        self.work = os.path.join(self.dir, "work")

    @property
    def meta(self):
        return rd(os.path.join(self.dir, "meta.json"))

    def exists(self):
        return os.path.exists(os.path.join(self.dir, "meta.json"))

    def need(self):
        if not self.exists():
            raise SystemExit(f"no run {self.name}: `lab new {self.name}` or `lab play {self.name} SCENARIO`")
        return self

    def log(self, **entry):
        with open(os.path.join(self.dir, "log.jsonl"), "a") as f:
            f.write(json.dumps({"at": now(), **entry}) + "\n")

    def seq(self):
        os.makedirs(os.path.join(self.dir, "snapshots"), exist_ok=True)
        return len(os.listdir(os.path.join(self.dir, "snapshots")))

    def env(self, project, extra=None):
        # Keep sessions out of the caller's own Claude memory: drop memory and extra-directory
        # settings inherited from a parent Claude session, and turn auto memory off (a guess at
        # the switch; harmless if ignored).
        e = {k: v for k, v in os.environ.items() if k not in INHERITED_DROP}
        e["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        e.update({"ENSEMBLE_HOME": self.home, "ENSEMBLE_PROJECT": project,
                  "ENSEMBLE_PARENTS": ",".join(family_spec().get(project, {}).get("parents", [])),
                  "PATH": self.bin + os.pathsep + e.get("PATH", "")})
        e.update(self.meta.get("env", {}))
        e.update(extra or {})
        return e

    def ens(self, project, *args, stdin=None, extra_env=None, check=True):
        r = subprocess.run([os.path.join(self.bin, "ens"), *args], input=stdin, text=True, capture_output=True,
                           cwd=os.path.join(self.work, project), env=self.env(project, extra_env))
        out = (r.stdout + r.stderr).strip()
        if check and (r.returncode or out.startswith("error:")):
            raise RuntimeError(f"ens {' '.join(args)} ({project}): {out}")
        return out

    # --- the family
    def members(self):
        return rd(os.path.join(self.home, "family", "family.json"), {"members": {}})["members"]

    def joined(self, project):
        return any(n.split("@")[0] == project for n in self.members())

    def ensure_joined(self, project):
        """A project joins the family at its first use, after its parents (else it would be a founder)."""
        for p in family_spec().get(project, {}).get("parents", []):
            self.ensure_joined(p)
        if not self.joined(project):
            self.ens(project, "whoami")
            m = self.members()
            name = max((n for n in m if n.split("@")[0] == project), key=lambda n: m[n]["gen"])
            say(f"{project} joined the family (gen {m[name]['gen']}, parents {m[name]['parents'] or 'none'})")
            self.log(step="born", project=project, gen=m[name]["gen"], parents=m[name]["parents"],
                     born_traits=m[name].get("born_traits"), marks=m[name].get("marks"))


# ------------------------------------------------------------------ setup / new
def cmd_setup(a):
    if not os.path.exists(VPY):
        say(f"creating {VENV}")
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
    pkgs = ["-r", os.path.join(PKG, "requirements.txt")] if a.full else ["numpy", "wordfreq"]
    subprocess.run([VPY, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([VPY, "-m", "pip", "install", "-q", *pkgs], check=True)
    say("ready. `claude` must be on PATH and signed in for real (non --fake) runs.")


def git_rev():
    def g(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()
    return {"sha": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain", "--", "packages/ensemble"))}


def new_run(name, projects=None, env=None, scenario=None):
    if not os.path.exists(VPY):
        raise SystemExit("run `python3 harness/lab.py setup` first")
    r = Run(name)
    if r.exists():
        raise SystemExit(f"run {name} exists ({r.dir}); pick another name or delete it")
    spec = family_spec()
    projects = projects or list(spec)
    os.makedirs(r.dir, exist_ok=True)
    # a frozen copy of Ensemble's code and skills, like install.sh makes
    shutil.copytree(PKG, r.app, ignore=shutil.ignore_patterns("test_*", "*.png", "*.wav", "*.html", "__pycache__",
                                                               "simulate.py", "compare.py", "calibrate.py"))
    os.makedirs(r.bin, exist_ok=True)
    ens = os.path.join(r.bin, "ens")
    with open(ens, "w") as f:
        f.write(f'#!/bin/sh\nexport ENSEMBLE_HOME="{r.home}"\nexec "{VPY}" "{os.path.join(r.app, "ens.py")}" "$@"\n')
    os.chmod(ens, 0o755)
    for p in projects:
        dst = os.path.join(r.work, p)
        shutil.copytree(os.path.join(TEST_PROJECTS, p), dst, ignore=shutil.ignore_patterns("tasks.json", "__pycache__"))
        for s in ("ensemble", "ensemble-night"):
            os.makedirs(os.path.join(dst, ".claude", "skills", s))
            shutil.copy(os.path.join(r.app, "claude", "skills", s, "SKILL.md"), os.path.join(dst, ".claude", "skills", s))
        settings = {
            "env": {"ENSEMBLE_HOME": r.home, "ENSEMBLE_PROJECT": p},
            "autoMemoryEnabled": False,
            "permissions": {"allow": ALLOWED_TOOLS},
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": f"{ens} --listen"}]}]},
        }
        wr(os.path.join(dst, ".claude", "settings.json"), settings)
        with open(os.path.join(dst, ".gitignore"), "w") as f:
            f.write("__pycache__/\n*.pyc\n")
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=lab", "-c", "user.email=lab@localhost",
                                                     "commit", "-qm", "start"]):
            subprocess.run(["git", *args], cwd=dst, check=True)
    os.makedirs(r.home, exist_ok=True)
    wr(os.path.join(r.dir, "meta.json"), {"created": now(), "projects": projects, "env": env or {},
                                           "ensemble": git_rev(), "scenario": scenario})
    snapshot(r, "new")
    say(f"run {name} ready in {r.dir}")
    return r


def parse_env(pairs):
    return dict(p.split("=", 1) for p in pairs or [])


def cmd_new(a):
    new_run(a.run, a.projects.split(",") if a.projects else None, parse_env(a.env))


# ------------------------------------------------------------------ sessions
def ens_calls(transcript_path):
    """The ens commands a session ran, from its stream-json transcript."""
    calls = []
    with open(transcript_path) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            for c in (msg.get("content") if isinstance(msg, dict) else None) or []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and isinstance(c.get("input"), dict):
                    cmd = c["input"].get("command") or ""
                    calls += [m.group(1) for m in re.finditer(r"(?:^|[;&|]\s*|\n)\s*(ens\s+[\w-]+)", cmd)]
                    if c.get("name") == "Skill":
                        calls.append(f"skill:{c['input'].get('skill', '?')}")
    return calls


def run_claude(r, project, prompt, label, a, nudge=True):
    path = os.path.join(r.dir, "transcripts", f"{r.seq():03d}-{label}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    argv = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--setting-sources", "project,local", "--permission-mode", "acceptEdits",
            "--allowedTools", *ALLOWED_TOOLS, "--max-turns", str(a.max_turns)]
    if a.model:
        argv += ["--model", a.model]
    if nudge:
        argv += ["--append-system-prompt", NUDGE]
    say(f"claude: {label}")
    with open(path, "w") as out:
        p = subprocess.run(argv, cwd=os.path.join(r.work, project), env=r.env(project), stdout=out, stdin=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT, text=True, timeout=a.timeout)
    result = {}
    with open(path) as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "result":
                result = ev
    return {"transcript": os.path.relpath(path, r.dir), "exit": p.returncode,
            "cost_usd": result.get("total_cost_usd"), "turns": result.get("num_turns"),
            "error": result.get("is_error"), "result": (result.get("result") or "")[:2000],
            "ens_calls": ens_calls(path)}


def commit_work(r, project, msg):
    d = os.path.join(r.work, project)
    subprocess.run(["git", "add", "-A"], cwd=d)
    subprocess.run(["git", "-c", "user.name=lab", "-c", "user.email=lab@localhost", "commit", "-qm", msg,
                    "--allow-empty"], cwd=d)


def advance(r, project, beats):
    # The SessionStart hook advances one beat per new session. Extra beats here model time passing
    # between sessions (scenario "beats_per_session" or a step's "beats"; default 0).
    for _ in range(beats):
        r.ens(project, "next-beat")


def do_session(r, project, tid, a, prompt=None, nudge=True, beats=1):
    r.ensure_joined(project)
    t = task(project, tid) if tid else {"id": "adhoc", "prompt": prompt, "expect": []}
    prompt = prompt or t["prompt"]
    label = f"{project}-{t['id']}"
    if a.fake:
        import fake_agent
        info = fake_agent.session(r, project, t)
    else:
        info = run_claude(r, project, prompt, label, a, nudge)
    advance(r, project, beats)
    commit_work(r, project, label)
    snap = snapshot(r, label)
    r.log(step="session", project=project, task=t["id"], fake=a.fake, nudge=nudge, snapshot=snap, **info)
    say(f"{label}: ens calls {len(info.get('ens_calls', []))}, cost {info.get('cost_usd')}")


def do_night(r, project, a, nudge=True):
    r.ensure_joined(project)
    label = f"{project}-night"
    if a.fake:
        import fake_agent
        info = fake_agent.night(r, project)
    else:
        info = run_claude(r, project, NIGHT_PROMPT, label, a, nudge)
    commit_work(r, project, label)
    snap = snapshot(r, label)
    r.log(step="night", project=project, fake=a.fake, snapshot=snap, **info)
    say(f"{label}: done")


def any_project(r):
    return next((p for p in r.meta["projects"] if r.joined(p)), r.meta["projects"][0])


def do_ens_step(r, project, args, label):
    r.ensure_joined(project)
    out = r.ens(project, *args)
    snap = snapshot(r, label)
    r.log(step="ens", project=project, args=args, out=out[:4000], snapshot=snap)
    say(f"{label}: {out[:300]}")
    return out


def cmd_session(a):
    do_session(Run(a.run).need(), a.project, a.task, a, a.prompt, not a.no_nudge, a.beats)


def cmd_night(a):
    do_night(Run(a.run).need(), a.project, a, not a.no_nudge)


def cmd_reunion(a):
    r = Run(a.run).need()
    do_ens_step(r, any_project(r), ["family-reunion"], "reunion")


def cmd_milestone(a):
    do_ens_step(Run(a.run).need(), a.project, ["declare-milestone", a.note], f"{a.project}-milestone")


def cmd_approve_generation(a):
    do_ens_step(Run(a.run).need(), a.project, ["approve-generation"], f"{a.project}-new-generation")


def cmd_ens(a):
    r = Run(a.run).need()
    r.ensure_joined(a.project)
    args = a.args[1:] if a.args[:1] == ["--"] else a.args
    print(r.ens(a.project, *args, stdin=None if sys.stdin.isatty() else sys.stdin.read(), check=False))


def cmd_claude(a):
    r = Run(a.run).need()
    r.ensure_joined(a.project)
    os.chdir(os.path.join(r.work, a.project))
    os.execvpe("claude", ["claude", "--setting-sources", "project,local"], r.env(a.project))


# ------------------------------------------------------------------ scenarios
def cmd_play(a):
    sc = rd(a.scenario)
    if sc is None:
        raise SystemExit(f"no scenario {a.scenario}")
    r = Run(a.run)
    if not r.exists():
        new_run(a.run, sc.get("projects"), {**sc.get("env", {}), **parse_env(a.env)},
                os.path.relpath(os.path.abspath(a.scenario), REPO))
    prog_path = os.path.join(r.dir, "progress.json")
    prog = rd(prog_path, {"done": []})
    steps = expand(sc["steps"])
    nudge_default = sc.get("nudge", True)
    beats = sc.get("beats_per_session", 0)
    for i, s in enumerate(steps):
        if i in prog["done"]:
            continue
        if a.until is not None and i >= a.until:
            break
        say(f"step {i + 1}/{len(steps)}: {json.dumps(s)}")
        nudge = s.get("nudge", nudge_default)
        do = s["do"]
        if do == "session":
            do_session(r, s["project"], s.get("task"), a, s.get("prompt"), nudge, s.get("beats", beats))
        elif do == "night":
            do_night(r, s["project"], a, nudge)
        elif do == "reunion":
            do_ens_step(r, any_project(r), ["family-reunion"], "reunion")
        elif do == "milestone":
            do_ens_step(r, s["project"], ["declare-milestone", s["note"]], f"{s['project']}-milestone")
        elif do == "approve-generation":
            do_ens_step(r, s["project"], ["approve-generation"], f"{s['project']}-new-generation")
        elif do == "ens":
            do_ens_step(r, s["project"], s["args"], s.get("label", f"{s['project']}-ens"))
        elif do == "snapshot":
            snapshot(r, s["label"])
        else:
            raise SystemExit(f"unknown step {do}")
        prog["done"].append(i)
        wr(prog_path, prog)
    write_report(r)
    say(f"report: {os.path.join(r.dir, 'report.md')}")


def expand(steps):
    """{"do": "sessions", "project": p, "tasks": "all" | [ids]} becomes one session step per task."""
    out = []
    for s in steps:
        if s["do"] == "sessions":
            ids = [t["id"] for t in tasks_of(s["project"])] if s.get("tasks", "all") == "all" else s["tasks"]
            out += [{**{k: v for k, v in s.items() if k not in ("do", "tasks")}, "do": "session", "task": t} for t in ids]
        else:
            out.append(s)
    return out


# ------------------------------------------------------------------ snapshots
WORD = re.compile(r"[a-z0-9]{3,}")


def words(text):
    return set(WORD.findall(text.lower()))


def tier(m):
    return "dormant" if m.get("dormant") else {0: "short", 1: "intermediate", 2: "long"}.get(m.get("c"), "?")


IMAGINED = ("poem", "probe", "excursion", "prediction")


def summarize_home(home):
    """Plain-file reading of an ENSEMBLE_HOME (no Ensemble imports, so any version can be compared)."""
    out = {"projects": {}, "family": {}}
    proot = os.path.join(home, "projects")
    for member in sorted(os.listdir(proot)) if os.path.isdir(proot) else []:
        mroot = os.path.join(proot, member, "memory")
        agents = {}
        for agent in sorted(os.listdir(mroot)) if os.path.isdir(mroot) else []:
            idx = rd(os.path.join(mroot, agent, "index.json"))
            if not idx:
                continue
            ms = idx["m"]
            tiers = {}
            for m in ms.values():
                tiers[tier(m)] = tiers.get(tier(m), 0) + 1

            def count(path, prefix):
                p = os.path.join(mroot, agent, path)
                return sum(1 for ln in open(p) if ln.startswith(prefix)) if os.path.exists(p) else 0
            agents[agent] = {
                "beat": idx["beat"], "pressure": idx.get("pressure", 0), "total": len(ms), "tiers": tiers,
                "lessons": sum(1 for m in ms.values() if m.get("lesson")),
                "waking": sum(1 for m in ms.values() if m.get("origin") in ("waking", None)),
                "dream_ideas": sum(1 for m in ms.values() if m.get("origin") == "dream"),
                "confirmed": sum(1 for m in ms.values() if m.get("origin") == "confirmed"),
                "inherited": sum(1 for m in ms.values() if m.get("origin") == "inherited"),
                "imagined": sum(1 for m in ms.values() if m.get("src") in IMAGINED),
                "outdated": sum(1 for m in ms.values() if m.get("superseded_by")),
                "poems": count("poems.md", "*beat"), "excursions": count("excursions.md", "- beat"),
                "memories": [{"id": k, "head": m["head"], "tier": tier(m), "uses": m.get("uses", 0),
                              "src": m.get("src"), "origin": m.get("origin"), "lesson": m.get("lesson", False),
                              "outdated": bool(m.get("superseded_by"))} for k, m in sorted(ms.items())],
            }
        out["projects"][member] = agents
    fam = rd(os.path.join(home, "family", "family.json"))
    if fam:
        out["family"] = {
            "members": {n: {"gen": m["gen"], "status": m["status"], "parents": m["parents"],
                            "born_traits": m.get("born_traits"), "marks": len(m.get("marks", [])),
                            "suggestion": bool(m.get("suggest") or m.get("suggestion"))}
                        for n, m in fam["members"].items()},
            "sayings": len(fam.get("sayings", {})), "heirlooms": len(fam.get("heirlooms", {})),
            "wisdom": len(fam.get("wisdom", [])), "kin": fam.get("kin", {}),
        }
    return out


def snapshot(r, label):
    name = f"{r.seq():03d}-{label}"
    d = os.path.join(r.dir, "snapshots", name)
    if os.path.isdir(r.home):
        shutil.copytree(r.home, os.path.join(d, "home"), ignore=shutil.ignore_patterns(".lock", "*.tmp"))
    wr(os.path.join(d, "summary.json"), {"label": label, "at": now(), **summarize_home(r.home)})
    return name


def cmd_snapshot(a):
    say(snapshot(Run(a.run).need(), a.label))


# ------------------------------------------------------------------ report
def rubric(r, summary):
    """Rough check (keyword overlap, a guess at a metric): did the expected memory form at all?"""
    rows = []
    for e in (json.loads(l) for l in open(os.path.join(r.dir, "log.jsonl")) if l.strip()):
        if e.get("step") != "session":
            continue
        proj = e["project"]
        try:
            expect = task(proj, e["task"])["expect"]
        except SystemExit:
            continue
        mems = []
        for member, agents in summary["projects"].items():
            if member.split("@")[0] == proj:
                for ag in agents.values():
                    mems += [m["head"] for m in ag["memories"] if m["src"] not in IMAGINED]
        for x in expect:
            best = max((len(words(x) & words(h)) / max(1, len(words(x))), h) for h in mems) if mems else (0, "")
            rows.append((proj, e["task"], x, round(best[0], 2), best[1]))
    return rows


def money(x):
    return "" if x is None else f"${x:.2f}"


def write_report(r):
    snaps = sorted(os.listdir(os.path.join(r.dir, "snapshots")))
    sums = [rd(os.path.join(r.dir, "snapshots", s, "summary.json")) for s in snaps]
    log = [json.loads(l) for l in open(os.path.join(r.dir, "log.jsonl"))] if os.path.exists(
        os.path.join(r.dir, "log.jsonl")) else []
    meta = r.meta
    L = [f"# Run {r.name}", "",
         f"Created {meta['created']}; Ensemble at `{meta['ensemble']['sha'][:10]}`"
         f"{' (with uncommitted changes)' if meta['ensemble']['dirty'] else ''}; scenario `{meta.get('scenario')}`; "
         f"env overrides {meta.get('env') or 'none'}.", ""]

    sessions = [e for e in log if e["step"] in ("session", "night")]
    if sessions:
        cost = sum(e.get("cost_usd") or 0 for e in sessions)
        L += ["## Sessions", "", f"{len(sessions)} sessions, ${cost:.2f} total.", "",
              "| # | step | project | task | ens calls | turns | cost | notes |", "|---|---|---|---|---|---|---|---|"]
        for i, e in enumerate(sessions, 1):
            calls = e.get("ens_calls") or []
            uniq = sorted(set(c.split()[-1] if c.startswith("ens") else c for c in calls))
            note = "fake" if e.get("fake") else ("**never used ens**" if not calls else "")
            if e.get("error"):
                note += " error"
            L.append(f"| {i} | {e['step']} | {e['project']} | {e.get('task', '')} | {len(calls)}: {', '.join(uniq)} | "
                     f"{e.get('turns') or ''} | {money(e.get('cost_usd'))} | {note} |")
        L.append("")

    L += ["## Memory over time (conductor)", "",
          "| snapshot | project | total | short/int/long/dormant | lessons | unconfirmed ideas | confirmed | inherited | imagined | outdated | poems | excursions | pressure | beat |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    shown = {}
    for s, sm in zip(snaps, sums):
        for member, agents in sm["projects"].items():
            c = agents.get("conductor")
            if not c:
                continue
            key = json.dumps({k: v for k, v in c.items() if k != "memories"}, sort_keys=True)
            if shown.get(member) == key:                     # unchanged since its last row
                continue
            shown[member] = key
            t = c["tiers"]
            L.append(f"| {s} | {member} | {c['total']} | {t.get('short', 0)}/{t.get('intermediate', 0)}/{t.get('long', 0)}/"
                     f"{t.get('dormant', 0)} | {c['lessons']} | {c['dream_ideas']} | {c['confirmed']} | {c['inherited']} | "
                     f"{c['imagined']} | {c['outdated']} | {c['poems']} | {c['excursions']} | {c['pressure']} | {c['beat']} |")
    L.append("")

    last = sums[-1] if sums else {"projects": {}, "family": {}}
    fam = last.get("family") or {}
    if fam:
        L += ["## Family (latest)", "",
              f"{fam['sayings']} sayings, {fam['heirlooms']} heirlooms, {fam['wisdom']} pieces of wisdom.", "",
              "| member | gen | status | parents | marks | born traits |", "|---|---|---|---|---|---|"]
        for n, m in sorted(fam["members"].items(), key=lambda x: (x[1]["gen"], x[0])):
            bt = ", ".join(f"{k} {v}" for k, v in (m.get("born_traits") or {}).items())
            L.append(f"| {n} | {m['gen']} | {m['status']} | {', '.join(m['parents']) or '-'} | {m['marks']} | {bt} |")
        L.append("")

    # what changed at each step: new memory heads
    L += ["## What each step added", ""]
    prev = {}
    for s, sm in zip(snaps, sums):
        lines = []
        for member, agents in sm["projects"].items():
            for ag, c in agents.items():
                before = prev.get((member, ag), {})
                for m in c["memories"]:
                    old = before.get(m["id"])
                    if old is None:
                        tag = "lesson" if m["lesson"] else (m["src"] if m["src"] in IMAGINED else m["origin"])
                        lines.append(f"- {member}/{ag} {m['id']} new ({tag}): {m['head'][:110]}")
                    elif m["lesson"] and not old["lesson"]:
                        lines.append(f"- {member}/{ag} {m['id']} became a lesson: {m['head'][:110]}")
                    elif m["outdated"] and not old["outdated"]:
                        lines.append(f"- {member}/{ag} {m['id']} marked outdated: {m['head'][:110]}")
                prev[(member, ag)] = {m["id"]: m for m in c["memories"]}
        if lines:
            L += [f"**{s}**", ""] + lines[:40] + ([f"- ... {len(lines) - 40} more"] if len(lines) > 40 else []) + [""]

    rows = rubric(r, last) if log else []
    if rows:
        L += ["## Expected memories (rough keyword match)", "",
              "Each task in tasks.json lists what a good session should remember. Score = share of the expected "
              "sentence's words found in the closest memory. A crude signal, not a grade.", "",
              "| project | task | expected | score | closest memory |", "|---|---|---|---|---|"]
        for proj, tid, x, sc, h in rows:
            L.append(f"| {proj} | {tid} | {x[:80]} | {sc} | {h[:80]} |")
        L.append("")

    with open(os.path.join(r.dir, "report.md"), "w") as f:
        f.write("\n".join(L))


def cmd_report(a):
    r = Run(a.run).need()
    write_report(r)
    say(os.path.join(r.dir, "report.md"))


def cmd_list(a):
    for n in sorted(os.listdir(RUNS)) if os.path.isdir(RUNS) else []:
        m = rd(os.path.join(RUNS, n, "meta.json"))
        if m:
            print(f"{n}\t{m['created']}\t{m.get('scenario') or ''}")


# ------------------------------------------------------------------ cli
def main(argv=None):
    sys.path.insert(0, HERE)
    ap = argparse.ArgumentParser(prog="lab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *args, claude=False):
        p = sub.add_parser(name)
        for x in args:
            p.add_argument(x)
        if claude:
            p.add_argument("--fake", action="store_true", help="offline stand-in instead of Claude")
            p.add_argument("--model")
            p.add_argument("--max-turns", type=int, default=40)
            p.add_argument("--timeout", type=int, default=1800)
            p.add_argument("--no-nudge", action="store_true")
        p.set_defaults(fn=fn)
        return p

    add("setup", cmd_setup).add_argument("--full", action="store_true", help="also the MCP and embedding extras")
    p = add("new", cmd_new, "run")
    p.add_argument("--projects")
    p.add_argument("--env", action="append")
    p = add("session", cmd_session, "run", "project", claude=True)
    p.add_argument("task", nargs="?")
    p.add_argument("--prompt")
    p.add_argument("--beats", type=int, default=0)
    add("night", cmd_night, "run", "project", claude=True)
    add("reunion", cmd_reunion, "run")
    add("milestone", cmd_milestone, "run", "project", "note")
    add("approve-generation", cmd_approve_generation, "run", "project")
    p = add("ens", cmd_ens, "run", "project")
    p.add_argument("args", nargs=argparse.REMAINDER)
    add("claude", cmd_claude, "run", "project")
    p = add("play", cmd_play, "run", "scenario", claude=True)
    p.add_argument("--until", type=int, help="stop before this step index (resume later with the same command)")
    p.add_argument("--env", action="append", help="KEY=VALUE added to the scenario's env, e.g. ENSEMBLE_EMBEDDER=hybrid")
    add("snapshot", cmd_snapshot, "run", "label")
    add("report", cmd_report, "run")
    add("list", cmd_list)
    a = ap.parse_args(argv)
    if a.cmd == "session" and not a.task and not a.prompt:
        ap.error("give a task id or --prompt")
    a.fn(a)


if __name__ == "__main__":
    main()
