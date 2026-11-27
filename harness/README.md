# lab: an autonomous test bench for Ensemble

`lab.py` runs Claude sessions against the [test projects](../test-projects), lets them form memories
with Ensemble, runs nights (dreams, poems, excursions), reunions and comings of age, and records
what memory looked like after every step. Stdlib Python; Ensemble itself runs in `.lab/venv`.

```bash
python3 harness/lab.py setup                     # once (add --full for MCP and embedding extras)
python3 harness/lab.py play saga1 harness/scenarios/family-saga.json
python3 harness/lab.py report saga1              # rewritten after every play anyway
```

## What a run is

`runs/<name>/` (git-ignored):

| path | what |
|---|---|
| `app/` | a frozen copy of `packages/ensemble` (code and skills) taken at `new`. Edit Ensemble, start a new run, compare the two. `meta.json` records the commit and whether it had uncommitted changes. |
| `bin/ens` | wrapper: the frozen `ens.py` with this run's `ENSEMBLE_HOME` |
| `home/` | this run's `ENSEMBLE_HOME`. Your real `~/.ensemble` is never touched. |
| `work/<project>/` | a git repo copy of each test project (without `tasks.json`, so Claude never sees the expected answers), with project-level skills in `.claude/skills/` and `.claude/settings.json` holding the SessionStart hook (`bin/ens --listen`), the env, and allowed tools. One commit per step, so `git log -p` shows what each session changed. |
| `transcripts/` | each Claude session's stream-json transcript |
| `snapshots/NNN-label/` | a copy of `home/` after each step, plus `summary.json` (counts per tier, lessons, ideas, imagined, outdated, poems, excursions, family members, traits, sayings, every memory's head) |
| `log.jsonl` | one line per step: cost, turns, the `ens` commands Claude ran, births, outputs |
| `report.md` | sessions table, memory over time, family, what each step added, and a rough check of expected memories |
| `progress.json` | finished scenario steps; re-running `play` resumes after the last one |

## Scenarios

A scenario is JSON: `projects` (default all), `env` (e.g. `ENSEMBLE_SLEEP_AT`), `nudge`,
`beats_per_session`, and `steps`. Steps:

| step | does |
|---|---|
| `{"do": "session", "project": p, "task": id}` or `"prompt": "..."` | one headless Claude session |
| `{"do": "sessions", "project": p, "tasks": "all" \| [ids]}` | one session per task, in order |
| `{"do": "night", "project": p}` | Claude runs the `ensemble-night` skill |
| `{"do": "reunion"}` | `ens family-reunion` |
| `{"do": "milestone", "project": p, "note": "..."}` | `ens declare-milestone`: p comes of age as p@2 |
| `{"do": "approve-generation", "project": p}` | approve a pending coming-of-age suggestion |
| `{"do": "ens", "project": p, "args": [...]}` | any `ens` command |
| `{"do": "snapshot", "label": "..."}` | an extra snapshot |

Included: `smoke` (2 sessions and a night), `no-nudge` (does Claude use Ensemble unprompted?),
`family-saga` (three generations, an unrelated founder, reunions, a coming of age; about 24
sessions and 7 nights), `many-nights` (for `--fake`: enough repetition to reach lessons and sayings).

## Families and births

A project joins the Ensemble family at its first step, and its parents (from
`test-projects/family.json`) join first. Order in the scenario is therefore order of birth: a
child born after its parent has lived inherits the parent's traits and marks as they are then.
`ENSEMBLE_PARENTS` only matters at that first join, which is why the harness controls it.

## `--fake`

`fake_agent.py` drives `ens` the way the skills ask, without a model: listen, recall, use what it
finds, remember the task's expected memories, and simple deterministic night verdicts. Use it to
test the harness and Ensemble's mechanics quickly and for free (`many-nights` takes about a minute).
It says nothing about whether Claude uses Ensemble well.

## Choices I made that you may want to change

- **Isolation from your setup.** Sessions run with `--setting-sources project,local`, so your user
  settings and hooks (including an installed Ensemble hook) don't load. Skills in `~/.claude/skills`
  may still load next to the project copies; if you've installed Ensemble globally, both have the
  same names, which I haven't tested.
- **Your own Claude memory.** Sessions get `autoMemoryEnabled: false` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`
  (my guess at the switch), and the harness drops memory and extra-directory variables inherited from a
  parent Claude session. Without that, a test session run from inside a Claude session edited the
  parent's memory files.
- **Nudge on by default.** A one-line `--append-system-prompt` says the project uses Ensemble. Without
  it a short `-p` task may never touch the skill; `no-nudge` measures that.
- **One beat per session.** Only `ens next-beat` advances Ensemble's clock, and the skill doesn't say
  when to call it, so in real use memories may never fade or get spaced promotions. The harness calls
  it once after each session (`beats_per_session`, or `"beats"` per step; 0 turns it off).
- **Allowed tools.** Read/Edit/Write/Glob/Grep, the Skill tool, and Bash limited to `ens`, `python`,
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
ens RUN PROJECT -- <args>            claude RUN PROJECT  (interactive, same setup)
snapshot RUN LABEL                   report RUN                        list
```
