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


def test_the_hook_never_blocks_a_session():
    out = run(["--listen"], "/proc/forbidden/ensemble")
    assert out.startswith("Ensemble unavailable")
    return "with an unusable ENSEMBLE_HOME the SessionStart hook prints a note instead of failing"


def test_projects_follow_the_working_folder_and_join_the_family():
    h = tempfile.mkdtemp()
    a, b = os.path.join(h, "alpha"), os.path.join(h, "beta")
    os.makedirs(a); os.makedirs(b)
    run(["remember", "alpha thing"], h, project=None, cwd=a)
    run(["remember", "beta thing"], h, project=None, cwd=b, env_extra={"ENSEMBLE_PARENTS": "alpha"})
    who = json.loads(run(["whoami"], h, project=None, cwd=b))
    fam = json.load(open(os.path.join(h, "family", "family.json")))
    assert who["project"] == "beta" and fam["members"]["beta"]["parents"] == ["alpha"]
    assert "alpha thing" not in run(["listen"], h, project=None, cwd=b)
    return "each folder is its own project with its own memory; ENSEMBLE_PARENTS made beta a child of alpha"


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
