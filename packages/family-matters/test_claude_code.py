"""The Claude Code layer: the fam command, the therapy (night) protocol, the hook, and the MCP mode.
Run: python3 test_claude_code.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENS = [sys.executable, os.path.join(HERE, "fam.py")]


def run(args, home, project="proj", stdin=None, env_extra=None, cwd=None):
    env = dict(os.environ, FAM_HOME=home, FAM_PROJECT=project, PYTHONWARNINGS="ignore", **(env_extra or {}))
    if project is None:
        env.pop("FAM_PROJECT")
    r = subprocess.run(ENS + args, input=stdin, capture_output=True, text=True, env=env, cwd=cwd, timeout=120)
    return r.stdout.strip()


def test_everyday_commands():
    h = tempfile.mkdtemp()
    assert run(["never-forget", "the staging database password rotates monthly", "--importance", "0.7"], h) == "stored m00001"
    hit = run(["bring-up", "staging password", "--strength", "0.6"], h)
    run(["start-argument", "rotate-weekly", "--text", "Rotate staging creds weekly?"], h)
    run(["take-sides", "rotate-weekly", "yes", "0.8", "--agent", "reviewer"], h)
    heard = run(["dinner"], h)
    assert "m00001" in hit and "rotate-weekly: YES" in heard and "(Rotate staging creds weekly?)" in heard
    return "never-forget, bring-up, start-argument, take-sides (as a subagent), dinner: all through the fam command"


def test_a_night_through_the_cli():
    h = tempfile.mkdtemp()
    run(["never-forget", "the staging database password rotates monthly"], h)
    run(["never-forget", "the staging db password now rotates weekly instead"], h)
    pairs = json.loads(run(["dream-pairs"], h))["pairs"]
    assert any({p["a"]["id"], p["b"]["id"]} == {"m00001", "m00002"} for p in pairs)
    report = run(["dream-apply"], h, stdin=json.dumps([{"a": "m00001", "b": "m00002", "op": "substitute", "score": 0.9,
                                                       "keep": "m00002", "insight": "Moved to weekly."}]))
    outdated = run(["bring-up", "how often does the staging password rotate", "--strength", "0.6"], h)
    assert "1 substitute" in report and "m00002 [" in outdated and "m00001 [" not in outdated, outdated
    pp = json.loads(run(["poem-pairs"], h))["pairs"]
    a, b = pp[0]["A"]["id"], pp[0]["B"]["id"]
    poem = run(["poem-apply"], h, stdin=json.dumps([{"A": a, "B": b, "figures": [{"text": "x", "p": 0.3}, {"text": "y", "p": 0.01}],
                                                    "aliases": {"A": [], "B": []}, "verse": "two lines"}]))
    seed = json.loads(run(["excursion-seeds"], h))["seeds"][0]["seed"]
    ex = run(["excursion-apply"], h, stdin=json.dumps([{"seed": seed, "form": "thought-exercise", "title": "t",
                                                        "outcome": "o", "verdict": "silly"}]))
    assert "1 figures" in poem and "1 excursions (1 silly)" in ex
    return "dream-pairs -> Claude's verdicts -> dream-apply; poem and excursion steps the same way"


def test_answers_from_a_file_and_help():
    """Claude Code refuses quoted braces on a command line (heredocs included), so the night skill
    answers through a file. In a 30-session run every night hit that refusal before this."""
    h, cwd = tempfile.mkdtemp(), tempfile.mkdtemp()
    run(["never-forget", "the staging database password rotates monthly"], h, cwd=cwd)
    run(["never-forget", "the staging db password now rotates weekly instead"], h, cwd=cwd)
    shown = json.loads(run(["dream-pairs"], h, cwd=cwd))
    assert "--file .fam-answer.json" in shown["answer_with"]
    ans = os.path.join(cwd, ".fam-answer.json")
    with open(ans, "w") as f:
        json.dump([{"a": "m00001", "b": "m00002", "op": "substitute", "score": 0.9, "keep": "m00002"}], f)
    report = run(["dream-apply", "--file", ".fam-answer.json"], h, cwd=cwd, stdin="")
    assert "1 substitute" in report and not os.path.exists(ans), report
    keep = os.path.join(cwd, "verdicts.json")                    # a file not named .fam-* is left alone
    run(["dream-pairs"], h, cwd=cwd)
    with open(keep, "w") as f:
        f.write("[]")
    run(["dream-apply", "--file", "verdicts.json"], h, cwd=cwd, stdin="")
    assert os.path.exists(keep)
    helped = run(["dream-apply", "--help"], h, cwd=cwd, stdin="")
    assert helped.startswith("fam dream-apply:") and "--file" in helped and "error" not in helped
    assert run(["never-forget", "--help"], h, cwd=cwd, stdin="").startswith("fam never-forget:")
    run(["dream-pairs"], h, cwd=cwd)
    empty = run(["dream-apply"], h, cwd=cwd, stdin="")
    assert empty.startswith("error: no answer given") and "--file" in empty, empty
    return "dream-apply --file applies and tidies .fam-answer.json; --help explains instead of crashing"


def test_every_verdict_given_is_applied():
    """dream-apply judges exactly the pairs dream-pairs showed, even though applying verdicts
    (and memories written in between) would change what fresh sampling picks."""
    h = tempfile.mkdtemp()
    topics = ["staging", "prod", "deploy", "creds", "tests", "ci", "db", "cache", "auth", "logging"]
    for i in range(1, 37):
        run(["never-forget", f"The {topics[i % 10]} setting number {i} uses rotation policy {i % 4} and owner team {i % 3}"], h)
    pairs = json.loads(run(["dream-pairs"], h))["pairs"]
    run(["never-forget", "a subagent wrote this between the two steps"], h)
    verdicts = [{"a": p["a"]["id"], "b": p["b"]["id"], "op": "add", "score": 0.9, "insight": f"link {i}"}
                for i, p in enumerate(pairs)]
    verdicts.append({"a": "m00001", "b": "m00037", "op": "reinforce", "score": 0.9, "insight": None})
    report = run(["dream-apply"], h, stdin=json.dumps(verdicts))
    again = run(["dream-apply"], h, stdin=json.dumps(verdicts))
    assert f"{len(pairs)} pairs; {len(pairs)} add" in report, report
    assert "1 verdicts were not for a pair shown (ignored): m00001-m00037" in report, report
    assert again.startswith("error") and "dream-pairs" in again, again
    pp = json.loads(run(["poem-pairs"], h))["pairs"]
    run(["never-forget", "another memory between the poem steps"], h)
    poem = run(["poem-apply"], h, stdin=json.dumps([{"A": x["A"]["id"], "B": x["B"]["id"], "figures": [], "aliases": {},
                                                     "verse": "v"} for x in pp]))
    assert f"{len(pp)} verses" in poem and "ignored" not in poem, poem
    return f"all {len(pairs)} 'add' verdicts applied despite a write in between; a stray verdict reported; no double apply"


def test_weave_then_the_poem_is_a_lens_in_every_step():
    h = tempfile.mkdtemp()
    for i, t in enumerate(["the staging database password rotates monthly", "the cafeteria closes early on fridays",
                           "deploys freeze on tuesdays", "the printer on floor 3 jams on duplex",
                           "audit logs are kept for 90 days", "tokens expire after one hour"]):
        run(["never-forget", t], h)
    assert "skip" in json.loads(run(["poem-weave"], h))          # off by default
    h_env = {"FAM_WEAVE": "1"}
    assert "skip" in json.loads(run(["poem-weave"], h, env_extra=h_env))   # on, but no figures yet
    for _ in range(2):
        pp = json.loads(run(["poem-pairs"], h))["pairs"]
        run(["poem-apply"], h, stdin=json.dumps([{"A": x["A"]["id"], "B": x["B"]["id"],
                                                  "figures": [{"text": "a plain one", "p": 0.4}, {"text": f"zeta-quill {x['A']['id']}", "p": 0.01}],
                                                  "aliases": {}, "verse": "v"} for x in pp]))
    shown = json.loads(run(["poem-weave"], h, env_extra=h_env))
    ids = [f["id"] for f in shown["figures"]]
    assert len(ids) >= 3 and shown["figures"][0]["from"]
    out = run(["weave-apply"], h, env_extra=h_env, stdin=json.dumps({"title": "Quills", "text": "a\nb\nc\nd", "from": ids}))
    assert out.startswith(f"wove {len(ids)} of {len(ids)}"), out
    assert "poem" not in json.loads(run(["dream-pairs"], h))       # the lens is off by default
    on = {"FAM_POEM_LENS": "1"}
    for step in ("dream-pairs", "poem-pairs", "excursion-seeds"):
        lens = json.loads(run([step], h, env_extra=on)).get("poem")
        assert lens and lens["title"] == "Quills" and "not evidence" in lens["read_as"], step
    assert "skip" in json.loads(run(["poem-weave"], h, env_extra={"FAM_WEAVE": "0"}))
    assert len(json.loads(run(["excursion-seeds"], h, env_extra={"FAM_EXCURSIONS": "3"}))["seeds"]) == 3
    fixed = {"FAM_NIGHT_SEED": "5"}
    pairs = lambda poems: json.loads(run(["poem-pairs"], h, env_extra=dict(fixed, FAM_POEM_LENS=poems)))["pairs"]
    assert pairs("0") == pairs("1")                            # a fixed seed: both arms of an experiment see the same pairs
    return "poem-weave -> weave-apply; the woven poem then rides along with dreams, poems and excursions (FAM_POEM_LENS=1)"


def test_the_hook_never_blocks_a_session():
    out = run(["--listen"], "/proc/forbidden/family")
    assert out.startswith("Family Matters unavailable")
    return "with an unusable FAM_HOME the SessionStart hook prints a note instead of failing"


def test_a_new_session_is_one_beat():
    """Only next-beat moved the clock, and nothing calls it in everyday use, so memories never faded or
    got spaced promotions. The SessionStart hook now advances one beat on a new session."""
    h = tempfile.mkdtemp()
    run(["never-forget", "deploys go out on tuesdays"], h)
    hook = lambda source: run(["--listen"], h, stdin=json.dumps({"hook_event_name": "SessionStart", "source": source}))
    assert "beat 1" in hook("startup") and "beat 2" in hook("startup")
    assert "beat 2" in hook("resume") and "beat 2" in hook("compact")       # not a new session
    assert "beat 2" in run(["--listen"], h, stdin="")                       # run by hand
    return "startup advances the beat; resume, compact and a manual --listen don't"


def test_projects_follow_the_working_folder_and_join_the_family():
    h = tempfile.mkdtemp()
    a, b = os.path.join(h, "alpha"), os.path.join(h, "beta")
    os.makedirs(a); os.makedirs(b)
    run(["never-forget", "alpha thing"], h, project=None, cwd=a)
    run(["never-forget", "beta thing"], h, project=None, cwd=b, env_extra={"FAM_PARENTS": "alpha"})
    who = json.loads(run(["identity-crisis"], h, project=None, cwd=b))
    fam = json.load(open(os.path.join(h, "family", "family.json")))
    assert who["project"] == "beta" and fam["members"]["beta"]["parents"] == ["alpha"]
    heard = run(["dinner"], h, project=None, cwd=b)
    own = [l for l in heard.splitlines() if l.startswith("  m0")]
    assert not any("alpha thing" in l for l in own), heard           # not in beta's own memory...
    assert any(l.startswith("family advice") and "alpha thing" in l and "your parent" in l
               for l in heard.splitlines()), heard                     # ...but told to it at birth, as advice
    assert "family advice" in run(["bring-up", "alpha thing"], h, project=None, cwd=b)
    return ("each folder is its own project with its own memory; FAM_PARENTS made beta a child of alpha, "
            "and alpha's knowledge reaches beta as advice")


def test_mcp_mode():
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    h = tempfile.mkdtemp()

    async def go():
        params = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "fam.py"), "mcp"],
                                       env=dict(os.environ, FAM_HOME=h, FAM_PROJECT="mcpproj"))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = [t.name for t in (await s.list_tools()).tools]
                await s.call_tool("never_forget", {"text": "deploys go out on tuesdays", "importance": 0.6})
                res = await s.call_tool("dinner", {})
                return tools, res.content[0].text
    tools, heard = anyio.run(go)
    assert {"dinner", "never_forget", "bring_up", "told_you_so", "lessons", "trauma", "dream_pairs", "dream_apply", "tree"} <= set(tools)
    assert "deploys go out on tuesdays" in heard
    return f"an MCP client listed {len(tools)} tools, stored a memory and heard it back"


def test_old_ensemble_names_still_work():
    """Ensemble became Family Matters: the old `ens` commands, ENSEMBLE_* variables, .ensemble-answer.json
    scratch files and an existing ~/.ensemble keep working, so nothing breaks for an old install."""
    h, cwd = tempfile.mkdtemp(), tempfile.mkdtemp()
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("FAM_", "ENSEMBLE_"))}
    old = lambda args, **kw: subprocess.run(ENS + args, capture_output=True, text=True, timeout=120, cwd=cwd,
                                            env=dict(clean, ENSEMBLE_HOME=h, ENSEMBLE_PROJECT="legacy",
                                                     PYTHONWARNINGS="ignore"), **kw).stdout.strip()
    assert old(["remember", "the staging database password rotates monthly"]) == "stored m00001"
    assert "m00001" in old(["recall", "staging password", "--strength", "0.6"])
    assert "m00001" in old(["listen"]) and old(["lessons"]).startswith("no blessings or curses yet")
    assert old(["use-memory", "m00001"]).startswith("m00001 now")
    assert json.loads(old(["whoami"]))["project"] == "legacy"
    old(["remember", "the staging db password now rotates weekly instead"])
    old(["dream-pairs"])
    with open(os.path.join(cwd, ".ensemble-answer.json"), "w") as f:
        json.dump([{"a": "m00001", "b": "m00002", "op": "substitute", "score": 0.9, "keep": "m00002"}], f)
    assert "1 substitute" in old(["dream-apply", "--file", ".ensemble-answer.json"], input="")
    assert not os.path.exists(os.path.join(cwd, ".ensemble-answer.json"))
    # an existing ~/.ensemble is used until install.sh moves it; a fresh machine gets ~/.family-matters
    home = tempfile.mkdtemp()
    os.makedirs(os.path.join(home, ".ensemble"))
    where = lambda: json.loads(subprocess.run(ENS + ["identity-crisis"], capture_output=True, text=True, cwd=cwd,
                                              env=dict(clean, HOME=home, FAM_PROJECT="p")).stdout)["memory"]
    assert where().startswith(os.path.join(home, ".ensemble", ""))
    os.makedirs(os.path.join(home, ".family-matters"))
    assert where().startswith(os.path.join(home, ".family-matters", ""))
    return "ens-era commands, ENSEMBLE_* variables, .ensemble-answer.json and an unmigrated ~/.ensemble all still work"

def test_lessons_and_trauma_answer_to_several_names():
    """Lessons (blessings-and-curses) answer to lessons, blessings, curses and blessing-and-a-curse;
    inherited marks (trauma) to trauma, generational-trauma, wisdom and received-wisdom."""
    h = tempfile.mkdtemp()
    run(["never-forget", "staging creds rotate weekly"], h)
    names = ["lessons", "blessings", "curses", "blessing-and-a-curse"]
    assert {run([n], h) for n in names} == {"no blessings or curses yet (give it time)"}
    names = ["trauma", "generational-trauma", "wisdom", "received-wisdom"]
    assert {run([n], h) for n in names} == {"no trauma (yet)"}
    sys.path.insert(0, HERE)
    from family import Family
    Family(os.path.join(h, "family")).mark("proj", "credential leak")
    assert {run([n], h) for n in names} == {"trauma: credential leak 1.00 (lived)"}
    return "4 names for lessons, 4 for trauma; trauma lists lived and inherited marks"

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
