<p align="center">
  <img src="assets/banner.svg" alt="Family Matters: memory for Claude Code that fades, dreams and runs in the family" width="640">
</p>

<p align="center">
  <b>Long-lived, per-project memory for Claude Code.</b><br>
  It remembers what was decided and why, lets what stops mattering fade,<br>
  and passes what it learned down to the projects that come after.
</p>

---

## TL;DR

- **What it is:** a small `ens` CLI, two Claude Code skills and a SessionStart hook. Claude remembers decisions, recalls them before re-deciding, and starts every session with a short briefing on what this project knows.
- **Why:** a new session only knows what's in the repo. Decisions and preferences that were only ever *said* ("whole grams only, please") get lost. Family Matters keeps them.
- **Does it work?** In a controlled A/B on real Claude sessions, it raised consistency with earlier decisions from **30/48 to 39/48**, and followed a preference that was only ever said in conversation **3/3 times vs 0/3** without it. Almost all of that came through the session-start briefing. Where the code already showed the answer, it made no difference. ([details](#what-the-lab-found))
- **What it costs:** about a third more turns per session and roughly 6% more spend in that test.
- **What makes it different:**
  - **[Decay](#decay-forgetting-on-purpose).** Memories fade unless they're used, go dormant, and can be revived. What keeps proving useful hardens into lessons that never fade. The briefing stays around 200 tokens however much is stored.
  - **[Generations and epigenetics](#generations-and-epigenetics).** Related projects form a family. Children are born hearing their parents' best-tested knowledge as advice, inherit their temperament as traits, and carry big experiences (like a credential leak) as epigenetic marks that weaken with each generation. A project that outgrows its world comes of age as a new generation.
  - **[Nights](#nights).** Dreams revisit and reconcile memories while Claude sleeps on it.
- **Install:** `cd packages/ensemble && ./install.sh --hook`. No API keys, no server, plain files in `~/.ensemble`.

```console
$ ens listen
beat 0 | changed: none
memory: 3 active, 0 dormant, 0 lessons
  m00001 short 0.80: Whenever we show grams, whole grams only (the baker asked)
  m00002 short 0.70: Errors raise RecipeError, never ValueError
  m00003 short 0.60: A cup is 240 ml in this project
```

## Install

```bash
git clone https://github.com/TheHaymaker/ensemble-of-memories
cd ensemble-of-memories/packages/ensemble
./install.sh --hook          # add --mcp to also register it as an MCP server
```

This installs:

- **the `ens` command** in `~/.local/bin`, with its own Python environment in `~/.ensemble/venv`;
- **two skills** in `~/.claude/skills`: `ensemble` (everyday use) and `ensemble-night` (dreams, poems, excursions);
- **with `--hook`, a SessionStart hook** that runs `ens --listen`, so every session opens knowing the project's state. Your `~/.claude/settings.json` is backed up and merged, not replaced.

Then just work. Claude uses the skills by itself. Run `/ensemble-night` when `ens listen` says sleep is due, and use `ens listen`, `ens recall "..."`, `ens family-tree` and `ens help` from your terminal. The full guide is in [`packages/ensemble/README.md`](packages/ensemble/README.md).

## How it works

### A session

```mermaid
flowchart LR
    S([Session starts]) -->|SessionStart hook| L["ens listen<br/><i>briefing: strongest memories,<br/>lessons, family advice</i>"]
    L --> W[Claude works on the task]
    W -->|before re-deciding| R["ens recall"]
    R --> W
    W -->|decided or learned something| M["ens remember"]
    W -->|a memory shaped the work| U["ens use-memory"]
    M --> Store[(project memory<br/>~/.ensemble)]
    U --> Store
    R -.-> Store
    Store -.->|next session| L
```

The briefing stays small (about 150 to 200 tokens of memory) however much the project has stored, because only the strongest active memories make it in.

### Nights

When enough new memories have piled up, `ens listen` says sleep is due and `/ensemble-night` runs one. Claude plays every part. Each step is a two-step exchange: `ens` proposes, Claude answers, and `ens` applies the answers.

```mermaid
flowchart TB
    due{{"ens listen: sleep is due"}} --> D
    subgraph night ["/ensemble-night"]
        direction TB
        D["<b>Dreams</b><br/>pairs new memories with older and dormant ones.<br/>Claude judges: reinforce, link, qualify,<br/>replace, contradict, or flag a tension"]
        P["<b>Poems</b><br/>one-line figures from unrelated memories,<br/>plus probes on where a lesson stops holding"]
        E["<b>Excursions</b><br/>curious what-ifs: thought experiments<br/>and hypotheses, kept as <i>imagined</i>"]
        D --> P --> E
    end
    E --> LS["Lessons form from memories that keep proving useful"]
    LS --> next([next morning's briefing])
```

The trust rules are strict. Anything a dream, poem or excursion makes is labelled *imagined* and stays an unconfirmed idea until a waking session actually uses it. Dreams can't overrule a waking memory or weaken a lesson. Poems are a playful extra: they add search keys and odd questions, and they settle nothing.

## Decay: forgetting on purpose

Most memory tools only grow. Family Matters forgets, on purpose, so the briefing stays short and current. Every memory has a strength that fades a little each beat, at a rate set by its tier, and only being **used** slows it down.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Short: ens remember
    Short --> Intermediate: 2 spaced uses
    Intermediate --> Long: 5 spaced uses
    Short --> Dormant: faded below 0.05
    Intermediate --> Dormant
    Long --> Dormant
    Dormant --> Short: revived by a strong, close recall
    Dormant --> Archive: untouched for a long time
    Intermediate --> Lesson: used often, consolidated,<br/>reinforced in a dream
    Long --> Lesson
    Archive --> Short: restore
```

| tier | keeps per beat | how a memory gets there |
|---|---|---|
| short | 80% | every new memory starts here |
| intermediate | 95% | 2 uses, at least 3 beats apart |
| long | 99% | 5 spaced uses |
| dormant | stops fading | strength fell below 0.05; left out of the briefing, still searchable |
| lesson | never fades | used 4+ times, consolidated for 2 nights, reinforced in a dream; only a vote overturns it |

- **Spacing, not cramming.** Several uses in one beat count once. Only uses spread over time promote a memory.
- **Buffs.** Every use permanently raises a memory's floor a little (the n-th use adds 0.02/n, up to 0.15). After about 7 uses it can never go dormant.
- **Revival.** A dormant memory wakes only when a recall is both strong and close to it, then has to earn its place again.
- **Archiving.** A dormant memory that nights keep finding no use for, and that nobody touches for a long time, moves to a compressed archive. `restore()` brings it back.
- **Replacement.** When a newer memory overturns an older one, the older is cut to 30% strength and marked **OUTDATED**, pointing to the newer.

The result is a flat briefing. In a 500-beat simulation with 2,000 memories, the summary stayed under about 200 tokens while 1,425 memories sat dormant on disk.

## Generations and epigenetics

Projects form families. Each project keeps its own memory, and what passes between relatives is advice and temperament, never rules.

```mermaid
flowchart TB
    RC["recipe-core"] -->|sayings, heirlooms,<br/>traits, marks| MP["meal-planner"]
    RC --> PT["pantry-tracker"]
    MP --> GB["grocery-bot"]
    RC -. comes of age .-> RC2["recipe-core@2"]
    MP <-. "kinship (you approve)" .-> TL["trail-log"]
```

**Born with advice.** Start a project with `ENSEMBLE_PARENTS=recipe-core` and it's born hearing its parent's 3 most relied-on memories as **sayings**, lessons first. They show up in the briefing as "advice only". The child adopts one only if it fits, and it then has to be confirmed by use like any new idea. A few specific memories can also be handed down intact as **heirlooms**.

**Traits.** Curiosity, skepticism, steadiness and expressiveness are read from how each project actually lived, and they tune its settings: excursions per night, how high the dream judge's bar is, how many uses it takes to confirm an idea or form a lesson. A child starts from a blend of its relatives' traits (parent 1, grandparent 0.5, sibling 0.3, aunt or uncle 0.15), and its own experience takes over as it lives.

**Epigenetic marks.** A big experience, like a credential leak, leaves a **mark**: heightened sensitivity to that theme, so related memories count for more.

```mermaid
flowchart LR
    E(["a credential leak"]) -->|"mark(theme), strength 1.0"| G["grandparent"]
    G -->|"passes on at half strength"| P["parent: 0.5"]
    P -->|"half again"| C["child: 0.25"]
    P -. "a calm life fades it<br/>by 0.85 per night" .-> P
    C -. "a similar experience<br/>renews it to full" .-> C
```

**Generations.** A long-lived project **comes of age** when the world its memories describe has changed, not when it gets big. Family Matters suggests it when a lot of its knowledge has been overturned, after 60 nights, or when memories mention a release, rewrite or migration. You decide. The current generation then retires as the parent: its lessons become sayings, its most relied-on memories become heirlooms, and `project@2` starts fresh while hearing its predecessor as advice.

**Reunions** gather the family: lessons are told, adopted sayings that held up gain weight, those voted down lose it, and lessons that recur across members become family wisdom. When unrelated projects keep learning the same lessons, a reunion proposes kinship for you to approve. `ens family-tree` draws it all as an HTML page and a Mermaid chart.

## What the lab found

This repo is also a lab. `harness/lab.py` runs real, headless Claude sessions against the small [test projects](test-projects), each in an isolated Ensemble home, and reports what memory looked like after every step.

The recall A/B ([PR #9](https://github.com/TheHaymaker/ensemble-of-memories/pull/9)) built up a history of decisions on a recipe project, then gave fresh sessions new tasks with and without memory, 3 reps each, scored by checks and a blind judge:

| | with memory | without |
|---|---|---|
| did what was asked | 60/60 | 60/60 |
| **consistent with earlier decisions** | **39/48 (81%)** | 30/48 (62%) |
| a preference only ever said in conversation | **3/3** | 0/3 |
| a child project following its parent's conventions | **6/6 checks** | 0/6 |
| blind judge, consistency (1 to 5) | **3.61** | 2.94 |
| blind judge, quality (1 to 5) | 3.72 | 3.67 |
| turns per session | 11.4 | 8.5 |
| cost per session | $0.26 | $0.24 |

**The honest reading:** memory doesn't make Claude better at the work itself. It helps by carrying knowledge the repo doesn't contain. On probes where the earlier decision was visible in the code, tests or README, both arms scored the same. The session-start briefing carried every winning trial; dreams and poems played no visible part in that test. Samples are small, so only large effects show up. One failure it surfaced, a child inheriting a decision its parent had since overturned, is being fixed.

## This repo

| folder | what |
|---|---|
| [`packages/ensemble`](packages/ensemble) | The engine (Ensemble): the `ens` CLI, skills, SessionStart hook, MCP server, memory, dreams, poems, excursions and families. Install with `packages/ensemble/install.sh --hook`. |
| [`test-projects`](test-projects) | Small realistic projects to run Claude sessions against, related as a family (see `test-projects/family.json`). Each has a `tasks.json` of session prompts. |
| [`harness`](harness) | `lab.py`: runs headless Claude sessions and nights against the test projects, each run in its own isolated Ensemble home, with snapshots and a report. |
| [`assets`](assets) | the logo and banner |

Lab quick start:

```bash
python3 harness/lab.py setup                                   # once: .lab/venv with Ensemble's deps
python3 harness/lab.py play smoke1 harness/scenarios/smoke.json --fake   # offline, seconds
python3 harness/lab.py play smoke2 harness/scenarios/smoke.json          # real Claude, a few minutes
open runs/smoke2/report.md
```

Ensemble's own tests: `cd packages/ensemble && python3 test_claude_code.py` (and the other `test_*.py`).

<sub>Under the hood, Family Matters is built on **Ensemble**, which is why the command is `ens` and the package lives in `packages/ensemble`. Ensemble started as shared state for a group of agents, held in a single audio file where every vote is a tone and the mix is the tally. That engine is still there (`ensemble.py`), next to the plain-markdown backend that Claude Code uses.</sub>
