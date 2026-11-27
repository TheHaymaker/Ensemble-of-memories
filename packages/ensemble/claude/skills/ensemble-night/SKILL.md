---
name: ensemble-night
description: Run a night for this project's Ensemble memory: weave earlier poems into one, judge the dream pairs, make poems that refuse the likely, and go on curious excursions. Use when `ens listen` says sleep is due, or when the user asks to sleep, dream or consolidate memory.
allowed-tools: Bash(ens *)
---

# A night

You are the sleeping, dreaming and playing mind of this project. A weave and three steps; each prints JSON,
and you answer with JSON in a file. Add `--agent NAME` throughout to run a subagent's night.

**How to answer:** write the JSON with your Write tool to `.ensemble-answer.json` in the project
folder, then run the apply command with `--file .ensemble-answer.json`. Ensemble deletes that file
once it has applied it. Don't put JSON on the command line or in a heredoc: Claude Code's shell
check refuses quoted braces in commands. `ens <command> --help` explains any step.

## 0. Weave (consolidating the poems)

Run `ens poem-weave`. It is off unless this project opted in, so it usually prints `skip`: then go on
to the dreams. Otherwise it shows the one-line
figures earlier nights left behind, each with the memories it came from, and recent verses. Compose
ONE poem from them, 8 to 24 lines: read the figures together so they answer and complicate each other.
Keep their strangeness and their exact referents; don't explain them, summarize the project, or end
on a moral. `from` lists the figure ids the poem draws on (at least two).

`.ensemble-answer.json`:

```json
{"title":"...","text":"line one\nline two\n...","from":["m00011","m00014","m00017"]}
```

then `ens weave-apply --file .ensemble-answer.json`.

From here on, a step's JSON may carry a `poem`: the latest woven poem. Read it before you answer.
It is a lens, not evidence: it may show you where a memory bends or what two memories share, but
decide from the memories (and the code) alone.

## 1. Dreams (sense-making)

Run `ens dream-pairs`. For each pair decide what the two memories mean together. Most pairs
mean nothing: answer `none`. Otherwise:

- `reinforce`: they agree.
- `add`: together they suggest something neither says; write that insight.
- `qualify`: both are right under different conditions; the insight says when each applies.
- `substitute`: one is a newer version of the other. `keep` is the current one.
- `subtract`: one contradicts the other and is wrong. `keep` is the right one.
- `tension`: they conflict and you cannot tell which holds; describe the conflict (it goes to a vote).

Only `add`, `qualify` and `tension` insights are kept, as new memories; leave `insight` null for the
rest. An insight is a claim about the project that would help a later session decide something,
not a to-do ("add a test for ...") and not a restatement of the pair. When in doubt, `none`.
Prefer `qualify` or `tension` to discarding a lesson that may still be valuable. Imagined memories
can only be linked or reinforced. Then:

`.ensemble-answer.json`:

```json
[{"a":"m00001","b":"m00003","op":"substitute","score":0.9,"keep":"m00003","insight":"Staging creds moved from monthly to weekly rotation."}]
```

then `ens dream-apply --file .ensemble-answer.json`.

## 2. Poems (not sense-making)

Run `ens poem-pairs`. For each distant pair write, per list, 8 candidates sampled from the tails
of your own distribution, each with your honest probability `p` of having written it (aim below
0.10). The likelier half is always refused, and a name is kept only if it points unambiguously at
its memory: strange but exact. Glosses are the opposite: maximum precision. Probes ask where a
memory stops being true. Add a short verse.

`.ensemble-answer.json`:

```json
[{"A":"m00002","B":"m00003","figures":[{"text":"...","p":0.03}],"aliases":{"A":[{"text":"...","p":0.02}],"B":[]},
  "glosses":{"A":"...","B":"..."},"probes":{"A":null,"B":null},"verse":"..."}]
```

then `ens poem-apply --file .ensemble-answer.json`.

## 3. Excursions (curiosity)

Run `ens excursion-seeds`. For each seed, do it anyway, out of curiosity: a build-out, an
experiment, a thought exercise or a hypothesis. Silly, trivial and nonsensical results are kept.
If a harmless experiment can actually run (a throwaway script in a temp folder, nothing touching
the project, the network or anything destructive), you may run it and report what happened in
`ran`. A hypothesis should carry a concrete `prediction` that a later real event could confirm.

`.ensemble-answer.json`:

```json
[{"seed":"<exactly as given>","form":"hypothesis","title":"...","outcome":"...","surprise":"...",
  "verdict":"silly","prediction":"...","spawn":["..."]}]
```

then `ens excursion-apply --file .ensemble-answer.json`.

## Then

Run `ens listen` and tell the user, in two or three lines, what the night changed: replacements,
tensions raised, lessons formed, and anything delightful from the poems or excursions.
