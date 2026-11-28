# lab: an autonomous test bench for Family Matters

`lab.py` runs Claude sessions against the [test projects](../test-projects), lets them form memories
with Family Matters, runs nights (dreams, poems, excursions), reunions and comings of age, and records
what memory looked like after every step. Stdlib Python; Family Matters itself runs in `.lab/venv`.

```bash
python3 harness/lab.py setup                     # once (add --full for MCP and embedding extras)
# Recall with embeddings: install model2vec into .lab/venv, then add --env FAM_EMBEDDER=hybrid to play
python3 harness/lab.py play saga1 harness/scenarios/family-saga.json
python3 harness/lab.py report saga1              # rewritten after every play anyway
```

## What a run is

`runs/<name>/` (git-ignored):

| path | what |
|---|---|
| `app/` | a frozen copy of `packages/family-matters` (code and skills) taken at `new`. Edit Family Matters, start a new run, compare the two. `meta.json` records the commit and whether it had uncommitted changes. |
| `bin/fam` | wrapper: the frozen `fam.py` with this run's `FAM_HOME` (`bin/ens` points at it, as install.sh leaves it) |
| `home/` | this run's `FAM_HOME`. Your real `~/.family-matters` is never touched. |
| `work/<project>/` | a git repo copy of each test project (without `tasks.json`, so Claude never sees the expected answers), with project-level skills in `.claude/skills/` and `.claude/settings.json` holding the SessionStart hook (`bin/fam --listen`), the env, and allowed tools. One commit per step, so `git log -p` shows what each session changed. |
| `transcripts/` | each Claude session's stream-json transcript |
| `snapshots/NNN-label/` | a copy of `home/` after each step, plus `summary.json` (counts per tier, blessings-and-curses (lessons), ideas, imagined, outdated, poems, excursions, family members, traits, advice (sayings), every memory's head) |
| `log.jsonl` | one line per step: cost, turns, the `fam` commands Claude ran, births, outputs |
| `report.md` | sessions table, memory over time, family, what each step added, and a rough check of expected memories |
| `progress.json` | finished scenario steps; re-running `play` resumes after the last one |

## Scenarios

A scenario is JSON: `projects` (default all), `env` (e.g. `FAM_SLEEP_AT`), `nudge`,
`beats_per_session`, and `steps`. Steps:

| step | does |
|---|---|
| `{"do": "session", "project": p, "task": id}` or `"prompt": "..."` | one headless Claude session |
| `{"do": "sessions", "project": p, "tasks": "all" \| [ids]}` | one session per task, in order |
| `{"do": "night", "project": p}` | Claude runs the `thats-not-how-i-remember-it` skill (a night) |
| `{"do": "reunion"}` | `fam thanksgiving` (the family reunion) |
| `{"do": "milestone", "project": p, "note": "..."}` | `fam midlife-crisis`: p comes of age as p@2 |
| `{"do": "approve-generation", "project": p}` | `fam move-out`: approve a pending coming-of-age suggestion |
| `{"do": "fam", "project": p, "args": [...]}` | any `fam` command (`"do": "ens"` still works) |
| `{"do": "snapshot", "label": "..."}` | an extra snapshot |

Included: `smoke` (2 sessions and a night), `no-nudge` (does Claude use Family Matters unprompted?),
`family-saga` (three generations, an unrelated founder, reunions, a coming of age; about 24
sessions and 7 nights), `many-nights` (for `--fake`: enough repetition to reach blessings-and-curses and advice).

## Families and births

A project joins the family at its first step, and its parents (from
`test-projects/family.json`) join first. Order in the scenario is therefore order of birth: a
child born after its parent has lived inherits the parent's traits and trauma (marks) as they are then.
`FAM_PARENTS` only matters at that first join, which is why the harness controls it.

## `--fake`

`fake_agent.py` drives `fam` the way the skills ask, without a model: dinner, bring-up, told-you-so what it
finds, never-forget the task's expected memories, and simple deterministic night verdicts. Use it to
test the harness and Family Matters' mechanics quickly and for free (`many-nights` takes about a minute).
It says nothing about whether Claude uses Family Matters well.

## Choices I made that you may want to change

- **Isolation from your setup.** Sessions run with `--setting-sources project,local`, so your user
  settings and hooks (including an installed Family Matters hook) don't load. Skills in `~/.claude/skills`
  may still load next to the project copies; if you've installed Family Matters globally, both have the
  same names, which I haven't tested.
- **Your own Claude memory.** Sessions get `autoMemoryEnabled: false` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
  (my guess at the switch), and the harness drops memory and extra-directory variables inherited from a
  parent Claude session. Without that, a test session run from inside a Claude session edited the
  parent's memory files.
- **Nudge on by default.** A one-line `--append-system-prompt` says the project uses Family Matters. Without
  it a short `-p` task may never touch the skill; `no-nudge` measures that.
- **One beat per session.** The SessionStart hook (`fam --listen`) advances Family Matters' clock once per
  new session. `beats_per_session` (or `"beats"` per step) adds more, to model days between sessions.
  The harness drops a few variables a parent cloud Claude session sets, without which project hooks
  don't run in the child sessions.
- **Allowed tools.** Read/Edit/Write/Glob/Grep, the Skill tool, and Bash limited to `fam` (and `ens`), `python`,
  `git`, `ls`, `cat`, `head`, `grep`, `mkdir`, with `--permission-mode acceptEdits`. Anything else is
  refused rather than asked, which shows up in the transcript.
- **Expected memories.** Each task lists what a good session would remember. The report's match is
  word overlap with the closest memory: a crude signal for "did anything like this form", not a grade.

## Commands

```
setup [--full]                       new RUN [--projects a,b] [--env K=V]
play RUN SCENARIO [--fake] [--until N] [--model M] [--max-turns N] [--no-nudge]
session RUN PROJECT TASK|--prompt .. night RUN PROJECT
reunion RUN                          milestone RUN PROJECT "note"      approve-generation RUN PROJECT
fam RUN PROJECT -- <args>            claude RUN PROJECT  (interactive, same setup)
snapshot RUN LABEL                   report RUN                        list
```

## Experiment: woven poems in the night (`poem_ab.py`)

Asks: does weaving the night's one-line figures into one longer poem, and showing that poem to
dreams, poem-making and excursions as a lens, make those steps more useful? `lab.py fork` copies a
run as it stands, so both arms start from the same memory and code. `FAM_NIGHT_SEED` gives both
arms the same pairs and seeds. A blind Claude judge then grades every item from both arms against
the code, with the items shuffled together.

```bash
python3 harness/poem_ab.py base pab1                          # 3 projects: 3 sessions, a night, 1 session
python3 harness/poem_ab.py arms pab1 --tag 2 --night-seed 11  # fork into control / poems, one night each
python3 harness/poem_ab.py judge pab1 --tag 2 && python3 harness/poem_ab.py report pab1 --tag 2
```

Results, 2026-11-27 (recipe-core, pantry-tracker, grocery-bot; about 35 items per arm per run). "Valuable" means the
judge found the item true of the code, new, and at least somewhat useful:

| run | probes valuable | dream verdicts valuable | excursions valuable | all valuable | cost per night |
|---|---|---|---|---|---|
| 1, unmatched pairs: control / poems | 6/18 / 1/18 | 5/6 / 8/9 | 7/9 / 4/9 | 18/33 / 13/36 | $0.54 / $0.57 |
| 2, matched pairs: control / poems | 0/17 / 3/18 | 4/6 / 5/9 | 6/9 / 7/9 | 10/32 / 15/36 | $0.54 / $0.62 |

With matched pairs (run 2), no difference was significant: every Fisher p was 0.23 or higher. Run 1's
lower probe grounding for the poems arm (p = 0.001) came with different pairs in each arm, and the
matched run didn't reproduce it. Which pairs a night draws matters far more than the lens: control probes were grounded 17/18 in run 1 and 5/17 in run 2. Longer poems were set aside after this: weaving (`FAM_WEAVE`) and the lens
(`FAM_POEM_LENS`) are both off by default and kept only for experiments, and the one-line poems stay
as a playful feature. A real effect would need several seeds per project to show through the noise.
