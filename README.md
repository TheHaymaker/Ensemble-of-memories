<p align="center">
  <img src="assets/banner.svg" alt="Family Matters: memory for Claude Code that fades, dreams and runs in the family" width="640">
</p>

<p align="center">
  <b>Long-lived, per-project memory for Claude Code.</b><br>
  It never forgets what was decided and why, represses what stops mattering,<br>
  hardens what keeps proving useful into a blessing and a curse, and hands its generational trauma down to the projects that come after.
</p>

---

## TL;DR

- **What it is:** a small `fam` CLI, two Claude Code skills and a SessionStart hook. Claude remembers decisions (`fam never-forget`), brings them up before re-deciding (`fam bring-up`), and starts every session with the family gossip (`fam gossip`): a short briefing on what this project knows.
- **Why:** a new session only knows what's in the repo. Decisions and preferences that were only ever *said* ("whole grams only, please") get lost. Family Matters keeps them, and will bring them up again. And again.
- **Does it work?** In a controlled A/B on real Claude sessions, it raised consistency with earlier decisions from **30/48 to 39/48**, and followed a preference that was only ever said in conversation **3/3 times vs 0/3** without it. Almost all of that came through the session-start briefing. Where the code already showed the answer, it made no difference. ([details](#what-the-lab-found))
- **What it costs:** about a third more turns per session and roughly 6% more spend in that test.
- **What makes it different:**
  - **[Decay](#decay-forgetting-on-purpose).** Memories fade unless they're used, get repressed, and can be recovered. What keeps proving useful hardens into a **blessing-and-a-curse** that never fades (`fam lessons`, `fam blessings` or `fam curses` lists them). The briefing stays around 200 tokens however much is stored.
  - **[Generations and epigenetics](#generations-and-epigenetics).** Related projects form a family. Children are born hearing their parents' best-tested knowledge as unsolicited advice, inherit their temperament as traits, and carry big experiences (like a credential leak) as inherited **generational trauma** that weakens with each generation. A project that outgrows its world moves out as a new generation.
  - **[Nights: "That's not how I remember it"](#nights-thats-not-how-i-remember-it).** Dreams revisit and reconcile memories while Claude sleeps on it.
- **Install:** `cd packages/family-matters && ./install.sh --hook`. No API keys, no server, plain files in `~/.family-matters`.

```console
$ fam gossip
beat 0 | changed: none
memory: 3 active, 0 repressed, 0 blessings-and-curses
  m00001 short 0.80: Whenever we show grams, whole grams only (the baker asked)
  m00002 short 0.70: Errors raise RecipeError, never ValueError
  m00003 short 0.60: A cup is 240 ml in this project
```

## Install

```bash
git clone https://github.com/TheHaymaker/ensemble-of-memories
cd ensemble-of-memories/packages/family-matters
./install.sh --hook          # add --mcp to also register it as an MCP server
```

This installs:

- **the `fam` command** in `~/.local/bin`, with its own Python environment in `~/.family-matters/venv`;
- **skills** in `~/.claude/skills`: `family-matters` (everyday use) and `thats-not-how-i-remember-it` (a night: dreams, poems, excursions), with seven aliases for the night named after other family sayings;
- **with `--hook`, a SessionStart hook** that runs `fam --listen` (family gossip), so every session opens knowing the project's state. Your `~/.claude/settings.json` is backed up and merged, not replaced.

Then just work. Claude uses the skills by itself. Run `/thats-not-how-i-remember-it` when `fam gossip` says therapy is overdue, and use `fam gossip`, `fam bring-up "..."`, `fam tree` and `fam help` from your terminal. The full guide, with every command and what the family calls things, is in [`packages/family-matters/README.md`](packages/family-matters/README.md).

**Coming from Ensemble?** Re-run `./install.sh`. It moves `~/.ensemble` to `~/.family-matters`, keeps `ens` working as a shim for `fam`, and swaps in the new skills and hook. Old command names (`ens listen`, `ens remember`, `ens lessons`) and `ENSEMBLE_*` variables still work.

## How it works

### A session

```mermaid
flowchart LR
    S([Session starts]) -->|SessionStart hook| L["fam gossip<br/><i>briefing: strongest memories,<br/>blessings-and-curses, family advice</i>"]
    L --> W[Claude works on the task]
    W -->|before re-deciding| R["fam bring-up"]
    R --> W
    W -->|decided or learned something| M["fam never-forget"]
    W -->|a memory shaped the work| U["fam told-you-so"]
    M --> Store[(project memory<br/>~/.family-matters)]
    U --> Store
    R -.-> Store
    Store -.->|next session| L
```

The briefing stays small (about 150 to 200 tokens of memory) however much the project has stored, because only the strongest active memories make it in.

### Nights: "That's not how I remember it"

When enough unprocessed memories have piled up, `fam gossip` says therapy is overdue and `/thats-not-how-i-remember-it` runs a night. Every family saying that describes a night works too: `/things-will-look-better-in-the-morning`, `/we-dont-talk-about-that`, `/lets-not-air-dirty-laundry`, `/who-told-you-that`, `/youll-understand-when-youre-older`, `/dont-make-me-come-in-there` and `/go-to-your-room-and-think-about-what-you-did`. Claude plays every part. Each step is a two-step exchange: `fam` proposes, Claude answers, and `fam` applies the answers.

```mermaid
flowchart TB
    due{{"fam gossip: therapy is overdue"}} --> D
    subgraph night ["/thats-not-how-i-remember-it"]
        direction TB
        D["<b>Dreams</b><br/>pairs new memories with older and repressed ones.<br/>Claude judges: reinforce, link, qualify,<br/>replace, contradict, or flag a tension"]
        P["<b>Poems</b><br/>one-line figures from unrelated memories,<br/>plus probes on where a blessing-and-a-curse stops holding"]
        E["<b>Excursions</b><br/>curious what-ifs: thought experiments<br/>and hypotheses, kept as <i>imagined</i>"]
        D --> P --> E
    end
    E --> LS["Blessings-and-curses form from memories that keep proving useful"]
    LS --> next([next morning's briefing])
```

The trust rules are strict. Anything a dream, poem or excursion makes is labelled *imagined* and stays an unconfirmed idea until a waking session actually uses it. Dreams can't overrule a waking memory or soften a blessing-and-a-curse. Poems are a playful extra: they add search keys and odd questions, and they settle nothing.

## Decay: forgetting on purpose

Most memory tools only grow. Family Matters represses, on purpose, so the briefing stays short and current. Every memory has a strength that fades a little each beat, at a rate set by its tier, and only being **used** slows it down.

```mermaid
stateDiagram-v2
    direction LR
    state "Blessing and a curse" as Blessing
    [*] --> Short: fam never-forget
    Short --> Intermediate: 2 spaced uses
    Intermediate --> Long: 5 spaced uses
    Short --> Repressed: faded below 0.05
    Intermediate --> Repressed
    Long --> Repressed
    Repressed --> Short: recovered by a strong, close bring-up
    Repressed --> Attic: untouched for a long time
    Intermediate --> Blessing: used often, consolidated,<br/>reinforced in a dream
    Long --> Blessing
    Attic --> Short: restore
```

| tier | keeps per beat | how a memory gets there |
|---|---|---|
| short | 80% | every new memory starts here |
| intermediate | 95% | 2 uses, at least 3 beats apart |
| long | 99% | 5 spaced uses |
| repressed | stops fading | strength fell below 0.05; left out of the briefing, still searchable |
| blessing-and-a-curse | never fades | used 4+ times, consolidated for 2 nights, reinforced in a dream; only settling an argument (a vote) overturns it |

- **Spacing, not cramming.** Several uses in one beat count once. Only uses spread over time promote a memory.
- **Buffs.** Every use permanently raises a memory's floor a little (the n-th use adds 0.02/n, up to 0.15). After about 7 uses it can never be repressed.
- **Recovered memories.** A repressed memory comes back only when a bring-up is both strong and close to it, then has to earn its place again.
- **The attic.** A repressed memory that therapy keeps finding no use for, and that nobody touches for a long time, goes up to a compressed archive. `restore()` brings it back down.
- **Revisionist history.** When a newer memory overturns an older one (`fam revise-history`, or `--replaces`), the older is cut to 30% strength and marked **OUTDATED**, pointing to the newer, and is never handed down.

The result is a flat briefing. In a 500-beat simulation with 2,000 memories, the summary stayed under about 200 tokens while 1,425 memories sat repressed on disk.

## Generations and epigenetics

Projects form families. Each project keeps its own memory, and what passes between relatives is advice, temperament and baggage, never rules.

```mermaid
flowchart TB
    RC["recipe-core"] -->|advice, baggage,<br/>traits, generational trauma| MP["meal-planner"]
    RC --> PT["pantry-tracker"]
    MP --> GB["grocery-bot"]
    RC -. moves out .-> RC2["recipe-core@2"]
    MP <-. "adoption (you approve)" .-> TL["trail-log"]
```

**Born with unsolicited advice.** Start a project with `FAM_PARENTS=recipe-core` and it's born hearing its parent's 3 most relied-on memories as **advice**, blessings-and-curses first. It shows up in the briefing as "unsolicited, advice only". The child takes it (`fam take-advice`) only if it fits, and it then has to be confirmed by use like any new idea. A few specific memories can also be handed down intact as **baggage**.

**Traits.** Curiosity, skepticism, steadiness and expressiveness are read from how each project actually lived, and they tune its settings: excursions per night, how high the dream judge's bar is, how many uses it takes to confirm an idea or form a blessing-and-a-curse. A child starts from a blend of its relatives' traits (parent 1, grandparent 0.5, sibling 0.3, aunt or uncle 0.15), and its own experience takes over as it lives.

**Generational trauma (epigenetic marks).** A big experience, like a credential leak, leaves **generational trauma**: heightened sensitivity to that theme, so related memories count for more. Like all good trauma, it gets passed down. `fam generational-trauma` (or `fam received-wisdom`) lists it.

```mermaid
flowchart LR
    E(["a credential leak"]) -->|"generational trauma(theme), strength 1.0"| G["grandparent"]
    G -->|"passes on at half strength"| P["parent: 0.5"]
    P -->|"half again"| C["child: 0.25"]
    P -. "a calm life fades it<br/>by 0.85 per night" .-> P
    C -. "a similar experience<br/>renews it to full" .-> C
```

**Generations.** A long-lived project **moves out** when the world its memories describe has changed, not when it gets big. Family Matters suggests it when a lot of its knowledge has been overturned, after 60 nights, or when memories mention a release, rewrite or migration. You decide (`fam move-out`, or `fam stay-home` to put it off), or have a `fam midlife-crisis "v2 rewrite"` and do it now. The current generation then retires as the parent: its blessings-and-curses become advice, its most relied-on memories become baggage, and `project@2` starts fresh while hearing its predecessor as advice.

**Thanksgiving** (`fam thanksgiving`, the family reunion) gathers everyone: blessings-and-curses are retold as advice, advice that was taken and held up gains weight, advice that was voted down loses it, and a blessing-and-a-curse that recurs across members becomes family lore. When unrelated projects keep learning the same lessons, Thanksgiving proposes an adoption for you to approve (`fam adopt`). `fam tree` draws it all, skeletons included, as an HTML page and a Mermaid chart.

## What the lab found

This repo is also a lab. `harness/lab.py` runs real, headless Claude sessions against the small [test projects](test-projects), each in an isolated Family Matters home, and reports what memory looked like after every step.

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

**The honest reading:** memory doesn't make Claude better at the work itself. It helps by carrying knowledge the repo doesn't contain. On probes where the earlier decision was visible in the code, tests or README, both arms scored the same. The session-start briefing (family gossip) carried every winning trial; dreams and poems played no visible part in that test. Samples are small, so only large effects show up. One failure it surfaced, a child inheriting a decision its parent had since overturned, is being fixed.

## This repo

| folder | what |
|---|---|
| [`packages/family-matters`](packages/family-matters) | The `fam` CLI, skills, SessionStart hook, MCP server, memory, dreams, poems, excursions and families, on the Ensemble engine. Install with `packages/family-matters/install.sh --hook`. |
| [`test-projects`](test-projects) | Small realistic projects to run Claude sessions against, related as a family (see `test-projects/family.json`). Each has a `tasks.json` of session prompts. |
| [`harness`](harness) | `lab.py`: runs headless Claude sessions and nights against the test projects, each run in its own isolated home, with snapshots and a report. |
| [`assets`](assets) | the logo and banner |

Lab quick start:

```bash
python3 harness/lab.py setup                                   # once: .lab/venv with the deps
python3 harness/lab.py play smoke1 harness/scenarios/smoke.json --fake   # offline, seconds
python3 harness/lab.py play smoke2 harness/scenarios/smoke.json          # real Claude, a few minutes
open runs/smoke2/report.md
```

Its own tests: `cd packages/family-matters && python3 test_claude_code.py` (and the other `test_*.py`).

<sub>Under the hood, Family Matters is built on **Ensemble**, which is why the engine's files keep that name and `ens` still works as an alias for `fam`. Ensemble started as shared state for a group of agents, held in a single audio file where every vote is a tone and the mix is the tally. That engine is still there (`ensemble.py`), next to the plain-markdown backend that Claude Code uses.</sub>
