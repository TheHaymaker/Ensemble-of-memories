---
name: ensemble-night
description: Run a night for this project's Ensemble memory: judge the dream pairs, make poems that refuse the likely, and go on curious excursions. Use when `ens listen` says sleep is due, or when the user asks to sleep, dream or consolidate memory.
allowed-tools: Bash(ens *)
---

# A night

You are the sleeping, dreaming and playing mind of this project. Three steps; each prints JSON,
and you answer with JSON on stdin. Add `--agent NAME` throughout to run a subagent's night.

## 1. Dreams (sense-making)

Run `ens dream-pairs`. For each pair decide what the two memories mean together. Most pairs
mean nothing: answer `none`. Otherwise:

- `reinforce`: they agree.
- `add`: together they suggest something neither says; write that insight.
- `qualify`: both are right under different conditions; the insight says when each applies.
- `substitute`: one is a newer version of the other. `keep` is the current one.
- `subtract`: one contradicts the other and is wrong. `keep` is the right one.
- `tension`: they conflict and you cannot tell which holds; describe the conflict (it goes to a vote).

Prefer `qualify` or `tension` to discarding a lesson that may still be valuable. Imagined memories
can only be linked or reinforced. Then:

```bash
ens dream-apply <<'JSON'
[{"a":"m00001","b":"m00003","op":"substitute","score":0.9,"keep":"m00003","insight":"Staging creds moved from monthly to weekly rotation."}]
JSON
```

## 2. Poems (not sense-making)

Run `ens poem-pairs`. For each distant pair write, per list, 8 candidates sampled from the tails
of your own distribution, each with your honest probability `p` of having written it (aim below
0.10). The likelier half is always refused, and a name is kept only if it points unambiguously at
its memory: strange but exact. Glosses are the opposite: maximum precision. Probes ask where a
memory stops being true. Add a short verse.

```bash
ens poem-apply <<'JSON'
[{"A":"m00002","B":"m00003","figures":[{"text":"...","p":0.03}],"aliases":{"A":[{"text":"...","p":0.02}],"B":[]},
  "glosses":{"A":"...","B":"..."},"probes":{"A":null,"B":null},"verse":"..."}]
JSON
```

## 3. Excursions (curiosity)

Run `ens excursion-seeds`. For each seed, do it anyway, out of curiosity: a build-out, an
experiment, a thought exercise or a hypothesis. Silly, trivial and nonsensical results are kept.
If a harmless experiment can actually run (a throwaway script in a temp folder, nothing touching
the project, the network or anything destructive), you may run it and report what happened in
`ran`. A hypothesis should carry a concrete `prediction` that a later real event could confirm.

```bash
ens excursion-apply <<'JSON'
[{"seed":"<exactly as given>","form":"hypothesis","title":"...","outcome":"...","surprise":"...",
  "verdict":"silly","prediction":"...","spawn":["..."]}]
JSON
```

## Then

Run `ens listen` and tell the user, in two or three lines, what the night changed: replacements,
tensions raised, lessons formed, and anything delightful from the poems or excursions.
