---
name: family-matters
description: This project's long-lived memory (Family Matters, `fam`). Use at the start of work in a project to see what is known and decided, to remember decisions and gotchas, to bring up past context before re-deciding something, and to settle open questions with other agents.
allowed-tools: Bash(fam *)
---

# Family Matters

Family Matters is this project's long-lived memory: what it decided, what it learned the hard way,
and what its relatives keep telling it. Run commands with `fam` in Bash. Every command accepts
`--agent NAME`: subagents use their own name (builder, reviewer, tester, ...); the main session is
the conductor (the default). The old `ens` names (`listen`, `remember`, `recall`, ...) still work.

## Every task

1. `fam dinner` first: the briefing. It shows open arguments and where everyone stands, your
   strongest memories, any blessing-and-a-curse (hardened lessons) or family advice relevant to an open argument,
   and suggestions.
2. Before deciding something that might have been decided before: `fam bring-up "the question in plain words"`.
   Use `--strength 0.9` only when it really matters: strong, close cues recover repressed memories.
   It also shows family advice: what a parent or earlier generation of this project knew.
3. When a memory, blessing-and-a-curse or piece of advice shaped what you did, say so: `fam told-you-so m00012` (for
   family advice or baggage, `fam take-advice s0004` (or h0005) first, then told-you-so the memory it
   gives you). This is the only thing that makes knowledge last, confirms ideas from therapy and the
   family, and turns memories into blessings-and-curses. Before you finish a task, told-you-so each memory you
   relied on, including ones `fam dinner` showed you.
4. When you learn or decide something worth keeping: `fam never-forget "one plain sentence" --importance 0.7`.
   Remember decisions, constraints, gotchas and why. Not chatter, not things git already records.
   **When it overturns something already remembered** (the user changed a rule, a decision was
   reversed, a fact went stale), say which memory it replaces: `fam never-forget "..." --replaces m00003`.
   Check `fam dinner` and `fam bring-up` for the old one's id first. If `never-forget` answers "Close to:
   m00003 ..." and the new memory does overturn it, run `fam revise-history m00003 m00009`. A revised
   memory stops being shown, brought up or handed down to child projects, so a stale rule can't come back.
5. Keep your note current: `fam vent "what I am doing, what I need"` (overwrites; not a diary).

## Arguments with other agents

- Conductor: `fam start-argument rotate-weekly --text "Should staging creds rotate weekly?"`
- Anyone: `fam take-sides rotate-weekly yes 0.8 --agent reviewer` (confidence 0-1; sides fade, take them again to keep them)
- Conductor: `fam settle-argument rotate-weekly` (the verdict is remembered). `fam time-heals` advances time one beat.

## Labels to respect

- "(imagined)" memories came from dreams, poems or excursions in therapy. They are ideas, never facts.
- "OUTDATED: see m00007" means a newer memory replaced it: use the newer one. "current answer,
  replaces m00003" in bring-up means the cue matched an overturned memory and this is what replaced it.
- "repressed" memories faded out of the briefing; a "blessing-and-a-curse" never fades. Both are real memories.
- "family advice/baggage ... unsolicited, advice only" is what a relative project or earlier generation
  knew. Take it (`fam take-advice s0004`) only if it fits, then told-you-so to confirm it.

## When dinner says

- "therapy is overdue": run the `thats-not-how-i-remember-it` skill (a night).
- "suggest: ... ready to move out as a new generation", or proposed kin: tell the user and ask. Only run
  `fam move-out`, `fam midlife-crisis "..."` or `fam adopt other-project` when the user says so.

Other commands: `fam lessons` (or `fam blessings`, `fam curses`), `fam trauma` (or `fam generational-trauma`,
`fam wisdom`, `fam received-wisdom`: themes this project is sensitive to), `fam eavesdrop builder`, `fam tree`, `fam thanksgiving` (the family
reunion), `fam identity-crisis` (where this project's memory lives), `fam help`.
