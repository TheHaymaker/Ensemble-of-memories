# Does Ensemble improve outcomes on new work?

Controlled A/B, 2026-11-27. Run `ab1`, harness `harness/eval/ab.py`. $1.56 for the history, $9.90 for 39 trials, about $0.5 for the judge: **about $12 in total**.

## Verdict

**Yes, but narrowly.** Ensemble did not make Claude better at the work itself. Every arm passed every task check (60/60 both ways) and every test suite. Where it helped was in carrying knowledge **the repo doesn't contain**, and only there:

| | with Ensemble | no Ensemble |
|---|---|---|
| task checks (did what was asked) | 60/60 | 60/60 |
| memory checks (consistent with earlier decisions) | **39/48 (81%)** | 30/48 (62%) |
| blind judge: consistency with earlier decisions (1-5) | **3.61** | 2.94 |
| blind judge: quality (1-5) | 3.72 | 3.67 |
| turns per session | 11.4 | 8.5 (+34%) |
| cost per session | $0.26 | $0.24 (+6%) |
| wall time | 58 s | 46 s (+26%) |

All of the gain came from 2 of the 6 probes. On the other 4, both arms scored the same, because the earlier decision could already be read in the code, tests or README.

## What helped, and how

1. **Remembering a preference that was only ever said in conversation.** In the history, the baker said "whenever we show grams, whole grams only" while no grams code existed yet. Later, asked to add `to_grams`, all 3 Ensemble sessions printed whole grams even for small amounts (1 tsp sugar is "4 g"). All 3 sessions without Ensemble chose "4.2 g". That's 3/3 vs 0/3 (Fisher p = 0.10; the direction is clear but the sample is small). Judge consistency: 4.7 vs 2.0.
2. **A child project inheriting its parent's conventions.** meal-planner has none of recipe-core's code. With Ensemble, all 3 sessions displayed kitchen fractions ("1/3 cup", "1 1/2 cup") like the parent does. Without it, 0/3 did (6/6 vs 0/6 checks, p = 0.002).
3. **No measurable help where the code already says it.** Following the `RecipeError` rule, keeping the float decision when it was re-proposed (with the baker's reason), and the 240 ml cup in recipe-core all scored the same in both arms. Claude reads the code and README well enough on its own.

**Which mechanism carried it.** The **SessionStart hook** (`ens --listen` output injected at session start) carried the facts that made a difference, in 6 of 6 winning trials. `ens recall` showed up mainly on probes where the code already held the answer, so in this test recall added no outcome on its own beyond what listen gave. Family inheritance worked through birth sayings shown by the hook. Lessons, dreams and poems played no visible part. The night's dream memories surfaced but changed no result.

## What hurt, or didn't work

- **The child inherited a stale decision.** recipe-core's first memory ("snap to fractions only when exact, else 2 decimals, never approximate") was overturned one session later by the baker's rule (always the nearest eighth, "a pinch" below 1/8 tsp). The old memory was never marked superseded, and it had 2 uses against 0 for the new one. So birth sayings handed the child the **outdated** rule. All 3 child sessions faithfully built it: "0.7 cup oil", "0.04 tsp salt", no "a pinch". This is why the blind judge gave the child's display consistency only 1.7. The memory carried over cleanly. It just carried the wrong thing.
- **Advice was shown and then ignored.** The "cup = 240 ml" saying appeared at start in all 3 child sessions combining cup and ml, and all 3 kept the vendored 236.6. It's labelled "advice only", and the task didn't ask, so this is defensible. But surfacing alone doesn't mean using.
- **Overhead with nothing to gain.** On the control probe, where nothing from history was needed, Ensemble added about 3 turns (11.7 vs 8.3) and about $0.06 per session, with identical results.
- **The empty-memory arm** (Ensemble installed, nothing remembered; 3 trials) scored like no Ensemble on memory checks (4/9) at Ensemble's turn count. The ritual itself is pure overhead. The value is all in the content.

## Recommendations (each testable with this harness)

1. When a session overturns a memory, mark the old one superseded. Perhaps `ens remember --replaces m00001`, or have `use-memory` while contradicting not count as a use. Also exclude superseded and contradicted memories from birth sayings. Expected effect: mp-display moves from following the stale rule to the current one.
2. Rank birth sayings by recency as well as uses, so a fresh decision isn't outranked by an old one.
3. Keep listen at session start as the main channel: that's where the value shows up. Make it cheap on unrelated tasks (the control-probe overhead).

## Limits

- I wrote the probes knowing the history, and they're chosen to cover ways memory could matter, not a random sample of real work. The "memory checks" measure consistency with prior decisions, which is the claimed benefit.
- 3 reps per cell (1 for the empty arm). Only large effects show up. The 2 wins are large and consistent, but the overall memory-check gap gives p ≈ 0.07 on its own.
- One history and one model. A longer history, where lessons form, could change the picture.
- The judge (Sonnet) saw the diff and final message with Ensemble mentions redacted, plus the facts a teammate would know.

## Reproduce

```bash
python3 harness/lab.py setup && .lab/venv/bin/pip install model2vec
python3 harness/eval/ab.py history ab1
python3 harness/eval/ab.py trials ab1 --arms ens,off --reps 3
python3 harness/eval/ab.py judge ab1      # report: runs/ab1-ab/report.md
```

The full per-probe tables are in [results-ab1-tables.md](results-ab1-tables.md).
