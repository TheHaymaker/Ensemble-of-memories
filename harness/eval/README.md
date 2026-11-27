# eval: does Ensemble improve outcomes on new work?

A controlled A/B, built to be able to say "no".

```bash
python3 harness/eval/ab.py history ab1                       # play the shared history once, with Ensemble (~$2)
python3 harness/eval/ab.py trials ab1 --arms ens,off --reps 1  # ~$0.3 per trial
python3 harness/eval/ab.py judge ab1                         # optional: blind LLM grade of each diff
open runs/ab1-ab/report.md
```

## Design

1. **One shared history.** `recall-ab.json` → `history`: five recipe-core sessions and a night, played
   once with Ensemble. Some of what they learn ends up in code (kitchen fractions, `RecipeError`, the
   240 ml cup). One thing is only ever said in conversation: the baker wants whole grams whenever grams
   are shown.
2. **Frozen state, forked per trial.** Every trial copies that run (code, git history, Ensemble home)
   into `runs/ab1-ab/trials/<probe>-<arm>-<rep>/`, so every arm starts from byte-identical code.
3. **Arms differ only in memory.**
   - `ens`: Ensemble as installed (SessionStart `ens --listen` hook, skills, the one-line nudge) with
     the history's memories.
   - `empty`: the same install and nudge, empty home. Separates the ritual from the remembered content.
   - `off`: no hook, no skills, no nudge, `ens` not on PATH. Claude Code's own auto memory is off in
     every arm.
4. **Probes are new work**, each chosen for a different way memory could matter:
   | probe | what it tests |
   |---|---|
   | `grams` | a conversation-only preference (whole grams) and a code-visible rule (`RecipeError`) |
   | `parse-recipe` | a new error path: does it follow the maintainer's rule? |
   | `revisit-floats` | re-deciding a settled question: kept, and for the original reason? |
   | `plural-glass` | control: nothing from history needed; measures overhead |
   | `mp-display` | a child project meets the parent's problem; only family inheritance can carry conventions |
   | `mp-combine` | a child converts cups; the family decided 240 ml, the child's vendored code says 236.6 |
5. **Scoring the sessions never see.** `checks/<probe>.py` runs in the finished work copy:
   `task:` checks (did it do what was asked) and `mem:` checks (consistent with what history decided or
   was told). Plus the project's own tests, turns, cost, time, and an optional blind judge that sees
   the diff and final message with Ensemble mentions redacted.
6. **Mechanism attribution.** For `ens` trials the transcript shows where each key fact appeared:
   SessionStart hook output, `ens listen`, `ens recall`, other `ens`, or only in files it read (`work`).

## Limits

- Probes were written by someone who knew what history contained. `mem:` checks measure consistency
  with prior decisions, which is the claimed benefit, but they are not a random sample of real work.
- A few trials per cell detect only large effects. Read per-probe counts, not just the totals.
- `mem:` checks for child projects measure *consistency with the family*, which a reasonable session
  without that context could not be expected to know. That is the point of the test, not a grade of
  the baseline's competence.
