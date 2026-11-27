"""The Claude Code layer: the ens command, the night protocol, the hook, and the MCP mode.
Run: python3 test_claude_code.py"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENS = [sys.executable, os.path.join(HERE, "ens.py")]


def run(args, home, project="proj", stdin=None, env_extra=None, cwd=None):
    env = dict(os.environ, ENSEMBLE_HOME=home, ENSEMBLE_PROJECT=project, PYTHONWARNINGS="ignore", **(env_extra or {}))
    if project is None:
        env.pop("ENSEMBLE_PROJECT")
    r = subprocess.run(ENS + args, input=stdin, capture_output=True, text=True, env=env, cwd=cwd, timeout=120)
    return r.stdout.strip()


def test_everyday_commands():
    h = tempfile.mkdtemp()
    assert run(["remember", "the staging database password rotates monthly", "--importance", "0.7"], h) == "stored m00001"
    hit = run(["recall", "staging password", "--strength", "0.6"], h)
    run(["open-question", "rotate-weekly", "--text", "Rotate staging creds weekly?"], h)
    run(["vote", "rotate-weekly", "yes", "0.8", "--agent", "reviewer"], h)
    heard = run(["listen"], h)
    assert "m00001" in hit and "rotate-weekly: YES" in heard and "(Rotate staging creds weekly?)" in heard
    return "remember, recall, open-question, vote (as a subagent), listen: all through the ens command"


def test_a_night_through_the_cli():
    h = tempfile.mkdtemp()
    run(["remember", "the staging database password rotates monthly"], h)
    run(["remember", "the staging db password now rotates weekly instead"], h)
    pairs = json.loads(run(["dream-pairs"], h))["pairs"]
    assert any({p["a"]["id"], p["b"]["id"]} == {"m00001", "m00002"} for p in pairs)
    report = run(["dream-apply"], h, stdin=json.dumps([{"a": "m00001", "b": "m00002", "op": "substitute", "score": 0.9,
                                                       "keep": "m00002", "insight": "Moved to weekly."}]))
    outdated = run(["recall", "how often does the staging password rotate", "--strength", "0.6"], h)
    assert "1 substitute" in report and "OUTDATED: see m00002" in outdated
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
    run(["remember", "the staging database password rotates monthly"], h, cwd=cwd)
    run(["remember", "the staging db password now rotates weekly instead"], h, cwd=cwd)
    shown = json.loads(run(["dream-pairs"], h, cwd=cwd))
    assert "--file .ensemble-answer.json" in shown["answer_with"]
    ans = os.path.join(cwd, ".ensemble-answer.json")
    with open(ans, "w") as f:
        json.dump([{"a": "m00001", "b": "m00002", "op": "substitute", "score": 0.9, "keep": "m00002"}], f)
    report = run(["dream-apply", "--file", ".ensemble-answer.json"], h, cwd=cwd, stdin="")
    assert "1 substitute" in report and not os.path.exists(ans), report
    keep = os.path.join(cwd, "verdicts.json")                    # a file not named .ensemble-* is left alone
    run(["dream-pairs"], h, cwd=cwd)
    with open(keep, "w") as f:
        f.write("[]")
    run(["dream-apply", "--file", "verdicts.json"], h, cwd=cwd, stdin="")
    assert os.path.exists(keep)
    helped = run(["dream-apply", "--help"], h, cwd=cwd, stdin="")
    assert helped.startswith("ens dream-apply:") and "--file" in helped and "error" not in helped
    assert run(["remember", "--help"], h, cwd=cwd, stdin="").startswith("ens remember:")
    run(["dream-pairs"], h, cwd=cwd)
    empty = run(["dream-apply"], h, cwd=cwd, stdin="")
    assert empty.startswith("error: no answer given") and "--file" in empty, empty
    return "dream-apply --file applies and tidies .ensemble-answer.json; --help explains instead of crashing"


def test_every_verdict_given_is_applied():
    """dream-apply judges exactly the pairs dream-pairs showed, even though applying verdicts
    (and memories written in between) would change what fresh sampling picks."""
    h = tempfile.mkdtemp()
    topics = ["staging", "prod", "deploy", "creds", "tests", "ci", "db", "cache", "auth", "logging"]
    for i in range(1, 37):
        run(["remember", f"The {topics[i % 10]} setting number {i} uses rotation policy {i % 4} and owner team {i % 3}"], h)
    pairs = json.loads(run(["dream-pairs"], h))["pairs"]
    run(["remember", "a subagent wrote this between the two steps"], h)
    verdicts = [{"a": p["a"]["id"], "b": p["b"]["id"], "op": "add", "score": 0.9, "insight": f"link {i}"}
                for i, p in enumerate(pairs)]
    verdicts.append({"a": "m00001", "b": "m00037", "op": "reinforce", "score": 0.9, "insight": None})
    report = run(["dream-apply"], h, stdin=json.dumps(verdicts))
    again = run(["dream-apply"], h, stdin=json.dumps(verdicts))
    assert f"{len(pairs)} pairs; {len(pairs)} add" in report, report
    assert "1 verdicts were not for a pair shown (ignored): m00001-m00037" in report, report
    assert again.startswith("error") and "dream-pairs" in again, again
    pp = json.loads(run(["poem-pairs"], h))["pairs"]
    run(["remember", "another memory between the poem steps"], h)
    poem = run(["poem-apply"], h, stdin=json.dumps([{"A": x["A"]["id"], "B": x["B"]["id"], "figures": [], "aliases": {},
                                                     "verse": "v"} for x in pp]))
    assert f"{len(pp)} verses" in poem and "ignored" not in poem, poem
    return f"all {len(pairs)} 'add' verdicts applied despite a write in between; a stray verdict reported; no double apply"


def test_weave_then_the_poem_is_a_lens_in_every_step():
    h = tempfile.mkdtemp()
    for i, t in enumerate(["the staging database password rotates monthly", "the cafeteria closes early on fridays",
                           "deploys freeze on tuesdays", "the printer on floor 3 jams on duplex",
                           "audit logs are kept for 90 days", "tokens expire after one hour"]):
        run(["remember", t], h)
    assert "skip" in json.loads(run(["poem-weave"], h))          # off by default
    h_env = {"ENSEMBLE_WEAVE": "1"}
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
    on = {"ENSEMBLE_POEM_LENS": "1"}
    for step in ("dream-pairs", "poem-pairs", "excursion-seeds"):
        lens = json.loads(run([step], h, env_extra=on)).get("poem")
        assert lens and lens["title"] == "Quills" and "not evidence" in lens["read_as"], step
    assert "skip" in json.loads(run(["poem-weave"], h, env_extra={"ENSEMBLE_WEAVE": "0"}))
    assert len(json.loads(run(["excursion-seeds"], h, env_extra={"ENSEMBLE_EXCURSIONS": "3"}))["seeds"]) == 3
    fixed = {"ENSEMBLE_NIGHT_SEED": "5"}
    pairs = lambda poems: json.loads(run(["poem-pairs"], h, env_extra=dict(fixed, ENSEMBLE_POEM_LENS=poems)))["pairs"]
    assert pairs("0") == pairs("1")                            # a fixed seed: both arms of an experiment see the same pairs
    return "poem-weave -> weave-apply; the woven poem then rides along with dreams, poems and excursions (ENSEMBLE_POEM_LENS=1)"


def test_the_hook_never_blocks_a_session():
    out = run(["--listen"], "/proc/forbidden/ensemble")
    assert out.startswith("Ensemble unavailable")
    return "with an unusable ENSEMBLE_HOME the SessionStart hook prints a note instead of failing"


def test_a_new_session_is_one_beat():
    """Only next-beat moved the clock, and nothing calls it in everyday use, so memories never faded or
    got spaced promotions. The SessionStart hook now advances one beat on a new session."""
    h = tempfile.mkdtemp()
    run(["remember", "deploys go out on tuesdays"], h)
    hook = lambda source: run(["--listen"], h, stdin=json.dumps({"hook_event_name": "SessionStart", "source": source}))
    assert "beat 1" in hook("startup") and "beat 2" in hook("startup")
    assert "beat 2" in hook("resume") and "beat 2" in hook("compact")       # not a new session
    assert "beat 2" in run(["--listen"], h, stdin="")                       # run by hand
    return "startup advances the beat; resume, compact and a manual --listen don't"


def test_projects_follow_the_working_folder_and_join_the_family():
    h = tempfile.mkdtemp()
    a, b = os.path.join(h, "alpha"), os.path.join(h, "beta")
    os.makedirs(a); os.makedirs(b)
    run(["remember", "alpha thing"], h, project=None, cwd=a)
    run(["remember", "beta thing"], h, project=None, cwd=b, env_extra={"ENSEMBLE_PARENTS": "alpha"})
    who = json.loads(run(["whoami"], h, project=None, cwd=b))
    fam = json.load(open(os.path.join(h, "family", "family.json")))
    assert who["project"] == "beta" and fam["members"]["beta"]["parents"] == ["alpha"]
    heard = run(["listen"], h, project=None, cwd=b)
    own = [l for l in heard.splitlines() if l.startswith("  m0")]
    assert not any("alpha thing" in l for l in own), heard           # not in beta's own memory...
    assert any(l.startswith("family saying") and "alpha thing" in l and "your parent" in l
               for l in heard.splitlines()), heard                     # ...but told to it at birth, as advice
    assert "family saying" in run(["recall", "alpha thing"], h, project=None, cwd=b)
    return ("each folder is its own project with its own memory; ENSEMBLE_PARENTS made beta a child of alpha, "
            "and alpha's knowledge reaches beta as advice")


def test_mcp_mode():
    import anyio
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    h = tempfile.mkdtemp()

    async def go():
        params = StdioServerParameters(command=sys.executable, args=[os.path.join(HERE, "ens.py"), "mcp"],
                                       env=dict(os.environ, ENSEMBLE_HOME=h, ENSEMBLE_PROJECT="mcpproj"))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = [t.name for t in (await s.list_tools()).tools]
                await s.call_tool("remember", {"text": "deploys go out on tuesdays", "importance": 0.6})
                res = await s.call_tool("listen", {})
                return tools, res.content[0].text
    tools, heard = anyio.run(go)
    assert {"listen", "remember", "dream_pairs", "dream_apply", "family_tree"} <= set(tools)
    assert "deploys go out on tuesdays" in heard
    return f"an MCP client listed {len(tools)} tools, stored a memory and heard it back"


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
