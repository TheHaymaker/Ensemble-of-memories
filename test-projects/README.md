# Test projects

Small, real, runnable Python projects (stdlib only; `python3 -m unittest discover -s tests` in each)
for Claude to work on while Family Matters remembers. Each `tasks.json` holds session prompts plus
`expect`: what a good session would remember. The harness hides `tasks.json` from Claude.

```
recipe-core (founder)                    trail-log (unrelated founder)
├── meal-planner                         
│   └── grocery-bot   (third generation)
└── pantry-tracker
```

The tasks are written so themes recur down the family and memory can matter:

- **Float noise** (`0.30000000000000004`) appears in recipe-core, again in meal-planner's shopping list,
  in pantry-tracker's display and as money in grocery-bot. Does a blessing-and-a-curse (a lesson) or advice from the founder help
  the descendants?
- **Units across dimensions** (cups of flour to grams, ml + cups of milk, pack sizes in another unit).
- **Revisits:** a later task asks to re-decide something (`floats-again`), to test recall and use.
- **Overturns:** a later task replaces an earlier fact (`us-cup-240` changes the cup from 236.6 to
  240 ml; `sunday-users` qualifies Monday weeks), for dreams to `substitute` or `qualify`.
- **Kinship bait:** trail-log is unrelated but learns the same display lesson, so Thanksgiving (a reunion) might
  propose it as kin.

Relationships are in `family.json`; the harness reads it to set `FAM_PARENTS`.
