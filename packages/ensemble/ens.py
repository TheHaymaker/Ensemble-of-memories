"""ens: Ensemble for Claude Code, as a command (used by the ensemble skills) or an MCP server.

    ens listen | ens remember "..." | ens dream-pairs | ...      (see `ens help`)
    ens mcp        claude mcp add --transport stdio --scope user ensemble -- ens mcp

Layout (ENSEMBLE_HOME, default ~/.ensemble):
    family/                         the family: tree, traits, marks, sayings, heirlooms, wisdom
    projects/<member>/state/        that project's Ensemble (parts, questions, score)
    projects/<member>/memory/<agent>/   each agent's own tiered memory

The project is ENSEMBLE_PROJECT, else the folder Claude Code was started in. A project joins
the family as a founder the first time, or as a child of ENSEMBLE_PARENTS (comma-separated).
Every tool takes an optional `agent` (default "conductor"), so subagents can be other players.

Claude is the judge, poet and explorer: the night tools work in two steps. The first returns
what to judge (pairs, distant pairs, seeds); Claude answers with JSON; the second applies it.

Environment:
    ENSEMBLE_HOME       state folder (default ~/.ensemble)
    ENSEMBLE_PROJECT    project name (default: the working folder's name)
    ENSEMBLE_PARENTS    parent projects, used once when the project first joins the family
    ENSEMBLE_ROSTER     players (default conductor,builder,reviewer,tester)
    ENSEMBLE_EMBEDDER   keywords (default) | hybrid | model2vec | gemini | st   (fixed once a store exists)
    ENSEMBLE_SLEEP_AT   new memories that make sleep due (default 30)
    ENSEMBLE_WEAVE      1: a night first weaves earlier one-line figures into one longer poem (default 0:
                        an experiment that showed no measurable benefit; poems stay a playful one-liner feature)
    ENSEMBLE_POEM_LENS  1: dreams, poems and excursions see the latest woven poem as a lens (default 0:
                        in two blind A/Bs it made no measurable difference; see harness/README.md)
    ENSEMBLE_EXCURSIONS excursion seeds per night (default 1)
    ENSEMBLE_NIGHT_SEED fixes which pairs and seeds a night picks (experiments: two arms see the same ones)

`ens --listen` prints the conductor's view, never failing: use it as a SessionStart hook. On a new
session (the hook's input says source "startup") it first advances the beat: one session, one beat.
"""
import json
import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from family import Family                     # noqa: E402
from family_view import render_html, to_mermaid  # noqa: E402
from mdensemble import MdEnsemble             # noqa: E402
from memory import MemoryStore                # noqa: E402
from tools import Player                      # noqa: E402

HOME = os.path.expanduser(os.environ.get("ENSEMBLE_HOME", "~/.ensemble"))
ROSTER = [r.strip() for r in os.environ.get("ENSEMBLE_ROSTER", "conductor,builder,reviewer,tester").split(",") if r.strip()]
SLEEP_AT = int(os.environ.get("ENSEMBLE_SLEEP_AT", "30"))
WEAVE = os.environ.get("ENSEMBLE_WEAVE", "0") != "0"
POEM_LENS = os.environ.get("ENSEMBLE_POEM_LENS", "0") != "0"
EXCURSIONS = int(os.environ.get("ENSEMBLE_EXCURSIONS", "1"))


def _seed(step):
    """A night step's random seed: fixed by ENSEMBLE_NIGHT_SEED (per step), else fresh."""
    fixed = os.environ.get("ENSEMBLE_NIGHT_SEED")
    return (int(fixed) * 7919 + step) % (1 << 30) if fixed else random.randrange(1 << 30)
LENS = ("A poem woven on an earlier night from this memory's one-line figures. It is a lens, not "
        "evidence: let it suggest where a memory bends, what two memories share, or what to try; "
        "decide only from the memories themselves (and the code, if you check).")


def project_name():
    if os.environ.get("ENSEMBLE_PROJECT"):
        return os.environ["ENSEMBLE_PROJECT"]
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return os.path.basename(os.path.abspath(base)) or "default"


def make_embedder():
    kind = os.environ.get("ENSEMBLE_EMBEDDER", "keywords")
    if kind == "keywords":
        return None
    import embeddings as E
    return {"model2vec": E.Model2VecEmbedder, "hybrid": E.HybridEmbedder, "gemini": E.GeminiEmbedder,
            "st": E.SentenceTransformerEmbedder}[kind]()


_EMB = None
_EMB_LOADED = False


def emb():
    global _EMB, _EMB_LOADED
    if not _EMB_LOADED:
        _EMB, _EMB_LOADED = make_embedder(), True
    return _EMB


def paths(member):
    root = os.path.join(HOME, "projects", member.replace("/", "_"))
    return os.path.join(root, "state"), os.path.join(root, "memory")


def family():
    return Family(os.path.join(HOME, "family"), emb())


def member():
    """The living generation of this project, joining the family if it is new."""
    f, proj = family(), project_name()
    fam = f._load()
    living = [(m["gen"], n) for n, m in fam["members"].items()
              if n.split("@")[0] == proj and m["status"] == "living"]
    if living:
        return max(living)[1]
    if any(n.split("@")[0] == proj for n in fam["members"]):
        raise RuntimeError(f"{proj} has no living generation")
    parents = [p.strip() for p in os.environ.get("ENSEMBLE_PARENTS", "").split(",") if p.strip()]
    parents = [current(f, p) for p in parents]
    f.birth(proj, os.path.join(paths(proj)[1], "conductor"), [p for p in parents if p])
    return proj


def current(f, proj):
    fam = f._load()
    living = [(m["gen"], n) for n, m in fam["members"].items() if n.split("@")[0] == proj and m["status"] == "living"]
    return max(living)[1] if living else None


def player(agent="conductor"):
    m = member()
    state, mem = paths(m)
    roster = ROSTER if agent in ROSTER else ROSTER + [agent]
    ens = MdEnsemble(state, roster)
    store = MemoryStore(os.path.join(mem, agent), emb())
    return Player(ens, agent, store, family=family() if agent == "conductor" else None, family_member=m)


def listen_text(agent="conductor"):
    p = player(agent)
    out = p.listen()
    pressure = p.memory.sleep_pressure()
    if pressure >= SLEEP_AT:
        out += f"\nsleep is due ({pressure} new memories): run /ensemble-night"
    return out


# ------------------------------------------------- the two-step night protocol
def _pending(agent, kind, data=None):
    """Save step 1's plan for step 2 (data given), or load it. Step 2 needs step 1's exact plan."""
    p = os.path.join(paths(member())[1], agent, f"pending_{kind}.json")
    if data is None:
        step1 = {"dream": "dream-pairs", "poem": "poem-pairs", "excursion": "excursion-seeds",
                 "weave": "poem-weave"}[kind]
        if not os.path.exists(p):
            raise RuntimeError(f"nothing pending: run `ens {step1}` first")
        with open(p) as f:
            pend = json.load(f)
        if "plan" not in pend:
            raise RuntimeError(f"this pending step is from an older ens: run `ens {step1}` again")
        return pend
    with open(p, "w") as f:
        json.dump(data, f)


def _done_pending(agent, kind):
    """Step 2 applied: drop the plan so the same answers can't be applied twice."""
    try:
        os.remove(os.path.join(paths(member())[1], agent, f"pending_{kind}.json"))
    except FileNotFoundError:
        pass


def _unmatched(note, keys):
    return f"; {len(keys)} {note}: {', '.join(keys[:5])}{' ...' if len(keys) > 5 else ''}" if keys else ""


def _dry_run(agent, run):
    """Run a night step on a copy of the memory, recording what it would ask Claude."""
    src = os.path.join(paths(member())[1], agent)
    MemoryStore(src, emb())
    tmp = tempfile.mkdtemp()
    try:
        dst = os.path.join(tmp, "m")
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".lock"))
        return run(MemoryStore(dst, emb()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _lens(agent, out):
    """Add the latest woven poem to a night step's JSON (ENSEMBLE_POEM_LENS=1)."""
    if POEM_LENS:
        woven = player(agent).memory.composed()
        if woven:
            out["poem"] = {"title": woven[-1]["title"], "text": woven[-1]["text"], "read_as": LENS}
    return out


def _brief(m):
    return {"id": m["id"], "text": m["text"], **{k: m[k] for k in ("tier", "origin", "src") if k in m}}


# ------------------------------------------------------------------ commands
COMMANDS = {}


def tool(fn):
    COMMANDS[fn.__name__] = fn
    return fn


def _safe(call):
    try:
        return call()
    except Exception as err:
        return f"error: {type(err).__name__}: {err}"


@tool
def listen(agent: str = "conductor") -> str:
    """See the ensemble at once: the beat, changed parts, every open question's verdict, your
    strongest memories, relevant lessons and family advice. Call this first."""
    return _safe(lambda: listen_text(agent))


@tool
def read_part(name: str, agent: str = "conductor") -> str:
    """Read one player's current note and declared votes."""
    return _safe(lambda: player(agent).read_part(name))


@tool
def write_note(text: str, agent: str = "conductor") -> str:
    """Replace your note with your current state (overwrites; not a log)."""
    return _safe(lambda: player(agent).write_note(text))


@tool
def vote(question: str, answer: str, confidence: float, agent: str = "conductor") -> str:
    """Vote yes/no (or an option) with confidence 0-1. Re-voting replaces your vote; votes fade."""
    return _safe(lambda: player(agent).vote(question, answer, confidence))


@tool
def open_question(question: str, text: str = "", options: list[str] | None = None) -> str:
    """Conductor: open a question (yes/no unless options are given). text says what is being decided."""
    return _safe(lambda: player("conductor").open_question(question, options, text or None))


@tool
def close_question(question: str) -> str:
    """Conductor: close a question. The verdict is remembered; a tension question resolves the tension."""
    return _safe(lambda: player("conductor").close_question(question))


@tool
def next_beat() -> str:
    """Conductor: advance time one beat (votes and memories fade a little)."""
    return _safe(lambda: player("conductor").next_beat())


@tool
def remember(text: str, importance: float = 0.5, replaces: str = "", agent: str = "conductor") -> str:
    """Store something worth remembering (importance 0-1). If it overturns an earlier memory, pass
    --replaces m00003: the old one is marked replaced and no longer shown or handed down."""
    return _safe(lambda: player(agent).remember(text, importance, replaces))


@tool
def replace_memory(old_id: str, new_id: str, agent: str = "conductor") -> str:
    """Mark old_id as overturned by new_id (both already stored): a decision changed or a fact went stale."""
    return _safe(lambda: player(agent).replace_memory(old_id, new_id))


@tool
def recall(cue: str, strength: float = 0.5, agent: str = "conductor") -> str:
    """Search memory by meaning. Only a strong (0.8+), closely matching cue wakes a dormant memory."""
    return _safe(lambda: player(agent).recall(cue, strength))


@tool
def use_memory(memory_id: str, agent: str = "conductor") -> str:
    """Say you relied on a memory: it strengthens, and ideas get confirmed this way."""
    return _safe(lambda: player(agent).use_memory(memory_id))


@tool
def lessons(agent: str = "conductor") -> str:
    """List hardened lessons (they do not fade; only a vote overturns one)."""
    return _safe(lambda: player(agent).lessons())


@tool
def adopt_saying(saying_id: str) -> str:
    """Take a family saying or heirloom (s0004, h0005) into the conductor's memory as an unproven idea."""
    return _safe(lambda: player("conductor").adopt_saying(saying_id))


@tool
def dream_pairs(agent: str = "conductor", cycles: int = 4, pairs_per_cycle: int = 12) -> str:
    """Night, step 1: the memory pairs tonight's sleep will replay, for you to judge. Answer each
    with dream_apply. Run through the /ensemble-night skill."""
    def go():
        seed = _seed(1)
        seen = []

        def record(a, b, sim):
            seen.append({"a": _brief(a), "b": _brief(b), "similarity": round(sim, 2)})
            return None
        plan = _dry_run(agent, lambda s: s.sleep(record, cycles, pairs_per_cycle, rng=random.Random(seed)))["plan"]
        _pending(agent, "dream", {"cycles": cycles, "ppc": pairs_per_cycle, "plan": plan})
        return json.dumps(_lens(agent, {"pairs": seen, "answer_with": f"write a JSON list to {ANSWER_FILE}, then ens dream-apply --file {ANSWER_FILE} (or the dream_apply tool). Each item: "
                           "{a, b, op: none|reinforce|add|qualify|substitute|subtract|tension, score 0-1, "
                           "keep: id (substitute/subtract), insight: one sentence or null}"}), separators=(",", ":"))
    return _safe(go)


@tool
def dream_apply(verdicts: str, agent: str = "conductor") -> str:
    """Night, step 2: apply your verdicts (JSON list) to the real memory. Pairs you skip count as fruitless."""
    def go():
        pend = _pending(agent, "dream")
        table = {}
        for v in json.loads(verdicts):
            if v.get("op") in (None, "none"):
                continue
            v = dict(v)
            if v.get("keep"):
                v["drop"] = v["b"] if v["keep"] == v["a"] else v["a"]
            table[tuple(sorted((v["a"], v["b"])))] = v
        asked = set()
        def judge(a, b, sim):
            key = tuple(sorted((a["id"], b["id"])))
            asked.add(key)
            return table.get(key)
        p = player(agent)
        report = p.memory.sleep(judge, pend["cycles"], pend["ppc"], min_score=p.min_score, plan=pend["plan"])["report"]
        _done_pending(agent, "dream")
        shown = {tuple(sorted(x)) for ps in pend["plan"] for x in ps}
        return (report
                + _unmatched("verdicts were not for a pair shown (ignored)", [f"{a}-{b}" for a, b in table if (a, b) not in shown])
                + _unmatched("verdicts were for pairs whose memories changed since (skipped)",
                             [f"{a}-{b}" for a, b in table if (a, b) in shown and (a, b) not in asked]))
    return _safe(go)


@tool
def poem_pairs(agent: str = "conductor", pairs: int = 3) -> str:
    """Poem-making, step 1: disparate memory pairs to make poems from. Not sense-making: refuse
    the likely. Answer with poem_apply."""
    def go():
        seed, seen = _seed(2), []

        def record(a, b, sim):
            seen.append({"A": _brief(a), "B": _brief(b)})
            return None
        plan = _dry_run(agent, lambda s: s.compose(record, pairs, rng=random.Random(seed))).get("plan", [])
        _pending(agent, "poem", {"pairs": pairs, "plan": plan})
        return json.dumps(_lens(agent, {"pairs": seen, "answer_with": f"write a JSON list to {ANSWER_FILE}, then ens poem-apply --file {ANSWER_FILE} (or poem_apply), one item per pair: "
                           "{A: id, B: id, figures: [{text, p}] x8, aliases: {A: [{text, p}] x8, B: [...]}, "
                           "glosses: {A, B}, probes: {A, B}, verse}. p = your honest probability of writing "
                           "it; sample from the tails (p < 0.10). The likelier half is always refused."}), separators=(",", ":"))
    return _safe(go)


@tool
def poem_apply(poems: str, agent: str = "conductor") -> str:
    """Poem-making, step 2: keep the least likely precise candidates; store figures, names, probes, verse."""
    def go():
        pend = _pending(agent, "poem")
        table = {tuple(sorted((w["A"], w["B"]))): w for w in json.loads(poems)}

        def poet(a, b, sim):
            w = table.get(tuple(sorted((a["id"], b["id"]))))
            if w and w["A"] != a["id"]:                     # keep sides aligned with this call
                w = dict(w, aliases={"A": w.get("aliases", {}).get("B", []), "B": w.get("aliases", {}).get("A", [])},
                         glosses={"A": w.get("glosses", {}).get("B"), "B": w.get("glosses", {}).get("A")},
                         probes={"A": w.get("probes", {}).get("B"), "B": w.get("probes", {}).get("A")})
            return w
        report = player(agent).memory.compose(poet, pend["pairs"], plan=pend["plan"])
        _done_pending(agent, "poem")
        used = {tuple(sorted((a, b))) for _, a, b in report["plan"]}
        return report["report"] + _unmatched("poems were not for a pair shown, or its memories are gone (ignored)",
                                             [f"{a}-{b}" for a, b in table if (a, b) not in used])
    return _safe(go)


@tool
def excursion_seeds(agent: str = "conductor", n: int = 0) -> str:
    """Excursions, step 1: seeds to explore out of curiosity (silly is fine). Answer with excursion_apply."""
    def go():
        seed, seen, k = _seed(3), [], n or EXCURSIONS

        def record(s, context):
            seen.append({"seed": s, "context": context})
            return None
        plan = _dry_run(agent, lambda s: s.wander(record, k, rng=random.Random(seed)))["plan"]
        _pending(agent, "excursion", {"n": k, "plan": plan})
        return json.dumps(_lens(agent, {"seeds": seen, "answer_with": f"write a JSON list to {ANSWER_FILE}, then ens excursion-apply --file {ANSWER_FILE} (or excursion_apply). Each item: {{seed, form: "
                           "build-out|experiment|thought-exercise|hypothesis, title, outcome, surprise, verdict, "
                           "prediction (hypotheses), spawn: [<=2 ideas], ran: what happened if you actually ran "
                           "something}"}), separators=(",", ":"))
    return _safe(go)


@tool
def excursion_apply(notes: str, agent: str = "conductor") -> str:
    """Excursions, step 2: keep every field note (marked imagined), spawned ideas and predictions."""
    def go():
        pend = _pending(agent, "excursion")
        table = {n["seed"]: n for n in json.loads(notes)}
        report = player(agent).memory.wander(lambda s, c: table.get(s), pend["n"], plan=pend["plan"])
        _done_pending(agent, "excursion")
        used = {p["seed"] for p in report["plan"]}
        return report["report"] + _unmatched("notes were not for a seed shown, or its memories are gone (ignored)",
                                             [s[:40] for s in table if s not in used])
    return _safe(go)


@tool
def poem_weave(agent: str = "conductor") -> str:
    """Night, first step: weave the one-line figures of earlier nights into one longer poem
    (consolidation). Answer with weave_apply. Prints {"skip": ...} when there is nothing to weave."""
    def go():
        if not WEAVE:
            return json.dumps({"skip": "weaving is off (ENSEMBLE_WEAVE=0): go on to the dreams"})
        seen = {}

        def record(figures, verses):
            seen.update(figures=figures, verses=verses)
            return None
        plan = _dry_run(agent, lambda s: s.weave(record))
        if not seen:
            return json.dumps({"skip": plan["report"] + ": go on to the dreams"})
        _pending(agent, "weave", {"plan": plan["plan"]})
        return json.dumps({**seen, "answer_with": f"write a JSON object to {ANSWER_FILE}, then ens weave-apply --file "
                           f"{ANSWER_FILE}: {{title, text: the poem, 8-24 lines, newlines as \\n, "
                           "from: [ids of the figures it draws on]}. One poem that reads the figures together: "
                           "keep their strangeness and exact referents, let them answer and complicate each "
                           "other, don't explain them or end on a moral."}, separators=(",", ":"))
    return _safe(go)


@tool
def weave_apply(woven: str, agent: str = "conductor") -> str:
    """Night, weave step 2: keep the woven poem; its figures are marked woven."""
    def go():
        pend = _pending(agent, "weave")
        w = json.loads(woven)
        if isinstance(w, list):
            w = w[0] if w else {}
        report = player(agent).memory.weave(lambda f, v: w, plan=pend["plan"])
        _done_pending(agent, "weave")
        return report["report"]
    return _safe(go)


@tool
def family_tree() -> str:
    """Draw the family tree: writes an HTML page and returns its path plus a Mermaid version."""
    def go():
        member()
        path = os.path.join(HOME, "family", "tree.html")
        render_html(family(), path, "Ensemble family")
        return f"open {path}\n\n```mermaid\n{to_mermaid(family())}\n```"
    return _safe(go)


@tool
def approve_generation() -> str:
    """Approve the conductor's suggestion that this project come of age as a new generation."""
    def go():
        m, f = member(), family()
        child = _next_name(m)
        out = f.approve(m, os.path.join(paths(child)[1], "conductor"))
        return f"{m} retired; {out['name']} begins with {out['heirlooms']} heirlooms and settings {out['settings']}"
    return _safe(go)


@tool
def decline_generation() -> str:
    """Decline the suggestion for now (quiet for 14 nights)."""
    return _safe(lambda: (family().decline(member()), "declined")[1])


@tool
def declare_milestone(note: str) -> str:
    """You (the human) declare a milestone: the project comes of age now."""
    def go():
        m, f = member(), family()
        out = f.milestone(m, os.path.join(paths(_next_name(m))[1], "conductor"), note)
        return f"{m} came of age as {out['name']}: {note}"
    return _safe(go)


@tool
def approve_kin(other_project: str) -> str:
    """Approve a proposed kinship between this project and another (they will count as siblings)."""
    def go():
        f = family()
        f.approve_kin(member(), current(f, other_project) or other_project)
        return f"{project_name()} and {other_project} are now kin"
    return _safe(go)


@tool
def family_reunion() -> str:
    """Gather the family: lessons become sayings, adopted sayings are scored, wisdom and kinship found."""
    def go():
        member()
        out = family().reunion()
        kin = "; ".join(f"{k['a']} + {k['b']} ({k['shared_lessons']} shared lessons)" for k in out["kin_suggestions"])
        return (f"{out['told']} new sayings, {out['confirmed']} confirmed, {out['contradicted']} contradicted; "
                f"wisdom: {out['wisdom'] or 'none new'}; proposed kin: {kin or 'none'}")
    return _safe(go)


@tool
def whoami(agent: str = "conductor") -> str:
    """Where this project's ensemble and memory live, and its family settings."""
    def go():
        m = member()
        state, mem = paths(m)
        f = family()
        return json.dumps({"project": project_name(), "member": m, "state": state, "memory": os.path.join(mem, agent),
                           "embedder": os.environ.get("ENSEMBLE_EMBEDDER", "keywords"),
                           "traits": f.traits(m), "settings": f.expression(f.traits(m))}, separators=(",", ":"))
    return _safe(go)


def _next_name(m):
    base = m.split("@")[0]
    return f"{base}@{int(m.split('@')[1]) + 1 if '@' in m else 2}"


def serve_mcp():
    try:
        from mcp.server.mcpserver import MCPServer as Server     # MCP Python SDK 2.x
    except ImportError:                                          # 1.x
        from mcp.server.fastmcp import FastMCP as Server
    server = Server("ensemble", instructions=(
        "Shared memory and coordination for this project. Call listen first in a task. Remember what "
        "is worth keeping (with replaces=<old id> when it overturns an earlier memory); use_memory when you "
        "rely on something; vote on open questions. When listen "
        "says sleep is due, run the /ensemble-night skill."))
    for fn in COMMANDS.values():
        server.tool()(fn)
    server.run("stdio")


USAGE = """ens: shared memory and coordination for this project (Ensemble)

  ens listen                                start here: beat, questions, memories, lessons, family advice
  ens remember "text" [--importance 0.7] [--replaces m00003]   ens replace-memory m00003 m00009
  ens recall "cue" [--strength 0.9]         ens use-memory m00012
  ens write-note "text"   ens read-part builder   ens vote q yes 0.8   ens lessons
  ens open-question q --text "what is being decided"   ens close-question q   ens next-beat
  ens dream-pairs | ens dream-apply --file .ensemble-answer.json      (night: Claude judges)
  ens poem-weave  | ens weave-apply --file ...   (night: older figures woven into one poem)
  ens poem-pairs  | ens poem-apply --file ...   ens excursion-seeds | ens excursion-apply --file ...
  ens family-tree   ens family-reunion   ens approve-generation   ens decline-generation
  ens declare-milestone "v2 rewrite"   ens approve-kin other-project   ens adopt-saying s0004   ens whoami
  ens mcp                                   run as an MCP server instead
Every command takes --agent NAME (default conductor) and --help. JSON for *-apply: --file PATH (a file
named .ensemble-* is deleted once applied), stdin, or one argument."""


def session_started():
    """True when Claude Code's SessionStart hook says a new session started (not a resume, /clear or
    compaction). Nothing else moves Ensemble's clock in everyday use, so without this, memories never
    fade or get spaced promotions."""
    import select
    try:
        if sys.stdin is None or sys.stdin.isatty() or not select.select([sys.stdin], [], [], 1.0)[0]:
            return False                                       # run by hand, or nothing piped in
        return json.loads(sys.stdin.read() or "{}").get("source") == "startup"
    except (ValueError, OSError, AttributeError):
        return False


def cli(argv):
    import inspect
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE); return 0
    if argv[0] == "mcp":
        serve_mcp(); return 0
    if argv[0] == "--listen":                                  # SessionStart hook
        try:
            if session_started():                              # a new session is one beat of the clock
                player("conductor").next_beat()
            print("Ensemble (this project's shared memory):\n" + listen_text())
        except Exception as err:                               # never block a session start
            print(f"Ensemble unavailable: {err}")
        return 0
    name = argv[0].replace("-", "_")
    fn = COMMANDS.get(name)
    if fn is None:
        print(f"unknown command {argv[0]}\n\n{USAGE}"); return 2
    params = inspect.signature(fn).parameters
    json_param = next((p for p in ("verdicts", "poems", "notes", "woven") if p in params), None)
    if any(a in ("-h", "--help") for a in argv[1:]):
        print(command_help(argv[0], fn, json_param)); return 0
    kwargs, pos, i, answer_file = {}, [], 1, None
    while i < len(argv):
        a = argv[i]
        if a == "--file" and json_param and i + 1 < len(argv):
            answer_file = argv[i + 1]; i += 2
        elif a.startswith("--") and a[2:].replace("-", "_") in params and i + 1 < len(argv):
            kwargs[a[2:].replace("-", "_")] = argv[i + 1]; i += 2
        else:
            pos.append(a); i += 1
    free = [p for p in params if p not in kwargs]
    for p, v in zip(free, pos):
        kwargs[p] = v
    if json_param and json_param not in kwargs:
        if answer_file:
            with open(answer_file) as f:
                kwargs[json_param] = f.read()
        elif not sys.stdin.isatty():
            kwargs[json_param] = sys.stdin.read()
        if not (kwargs.get(json_param) or "").strip():
            print(f"error: no answer given. Write the JSON to a file and run: ens {argv[0]} --file {ANSWER_FILE}")
            return 2
    for p, v in list(kwargs.items()):                          # cast to the annotated type
        ann = params[p].annotation
        if ann in (int, float):
            kwargs[p] = ann(v)
        elif "list" in str(ann) and isinstance(v, str):
            kwargs[p] = [x.strip() for x in v.split(",") if x.strip()]
    out = fn(**kwargs)
    print(out)
    if answer_file and not out.startswith("error:") and os.path.basename(answer_file).startswith(".ensemble-"):
        os.remove(answer_file)                                 # a scratch answer, applied: tidy it away
    return 0


ANSWER_FILE = ".ensemble-answer.json"


def command_help(name, fn, json_param):
    import inspect
    doc = inspect.getdoc(fn) or ""
    opts = [f"--{p.replace('_', '-')}" + (f" (default {v.default})" if v.default is not inspect.Parameter.empty else "")
            for p, v in inspect.signature(fn).parameters.items() if p != json_param]
    out = f"ens {name}: {doc}\n\noptions: {', '.join(opts) or 'none'}"
    if json_param:
        out += (f"\n\nThe answer is JSON. Write it to a file (e.g. {ANSWER_FILE} with your Write tool) and run "
                f"`ens {name} --file {ANSWER_FILE}`; a file named .ensemble-* is deleted once applied. "
                f"Piping it on stdin also works.")
    return out


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
