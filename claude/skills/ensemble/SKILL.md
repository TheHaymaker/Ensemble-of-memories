---
name: ensemble
description: Shared project memory and coordination (Ensemble). Use at the start of work in a project to see what is known and decided, to remember decisions and lessons, to recall past context before re-deciding something, and to vote on open questions with other agents.
allowed-tools: Bash(ens *)
---

# Ensemble

Ensemble is this project's long-lived memory and its shared score. Run commands with `ens`
in Bash. Every command accepts `--agent NAME`: subagents use their own name (builder,
reviewer, tester, ...); the main session is the conductor (the default).

## Every task

1. `ens listen` first. It shows open questions and where the group stands, your strongest
   memories, any lesson or family advice relevant to an open question, and suggestions.
2. Before deciding something that might have been decided before: `ens recall "the question in plain words"`.
   Use `--strength 0.9` only when it really matters: strong, close cues wake dormant memories.
3. When you rely on a recalled memory: `ens use-memory m00012`. This is what makes knowledge last,
   confirms dream and family ideas, and eventually turns memories into lessons.
4. When you learn or decide something worth keeping: `ens remember "one plain sentence" --importance 0.7`.
   Remember decisions, constraints, gotchas and why. Not chatter, not things git already records.
5. Keep your note current: `ens write-note "what I am doing, what I need"` (overwrites; not a log).

## Decisions with other agents

- Conductor: `ens open-question rotate-weekly --text "Should staging creds rotate weekly?"`
- Anyone: `ens vote rotate-weekly yes 0.8 --agent reviewer` (confidence 0-1; votes fade, re-vote to keep them)
- Conductor: `ens close-question rotate-weekly` (the verdict is remembered). `ens next-beat` advances time.

## Labels to respect

- "(imagined)" memories came from dreams, poems or excursions. They are ideas, never facts.
- "OUTDATED: see m00007" means a newer memory replaced it: use the newer one.
- "family saying ... advice only" is a relative project's lesson. Adopt it (`ens adopt-saying s0004`)
  only if it fits, then use it to confirm it.

## When listen says

- "sleep is due": run the `ensemble-night` skill.
- "suggest: ... ready for a new generation", or proposed kin: tell the user and ask. Only run
  `ens approve-generation`, `ens declare-milestone "..."` or `ens approve-kin other-project` when the user says so.

Other commands: `ens lessons`, `ens read-part builder`, `ens family-tree`, `ens family-reunion`, `ens whoami`, `ens help`.
