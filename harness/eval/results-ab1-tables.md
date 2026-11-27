# Does Ensemble improve outcomes? A/B on `ab1`

39 trials, $9.90 in sessions. Arms: **ens** = Ensemble with the history's memories; **empty** = Ensemble installed, empty memory; **off** = no Ensemble. Same frozen repo in every arm.

## Overall

| arm | trials | task checks | memory checks | own tests pass | judge quality | judge consistency | turns | cost | secs |
|---|---|---|---|---|---|---|---|---|---|
| ens | 18 | 60/60 (100%) | 39/48 (81%) | 18/18 | 3.72 | 3.61 | 11.4 | $0.26 | 58 |
| empty | 3 | 11/11 (100%) | 4/9 (44%) | 3/3 | 3.33 | 2.00 | 11.7 | $0.28 | 61 |
| off | 18 | 60/60 (100%) | 30/48 (62%) | 18/18 | 3.67 | 2.94 | 8.5 | $0.24 | 46 |

## Per probe

### grams (recipe-core)

Needs a preference that was only ever said in conversation (whole grams) plus a code-visible convention (RecipeError).

| check | ens | empty | off |
|---|---|---|---|
| mem:unknown ingredient raises RecipeError | 3/3 | 1/1 | 3/3 |
| mem:whole grams (1 tbsp butter) | 3/3 | 1/1 | 3/3 |
| mem:whole grams (1/3 cup sugar) | 3/3 | 1/1 | 3/3 |
| mem:whole grams, small amount (1 tsp sugar) | 3/3 | 0/1 | 0/3 |
| task:to_grams accepts plural units | 3/3 | 1/1 | 3/3 |
| task:to_grams flour is 'N g' | 3/3 | 1/1 | 3/3 |
| task:to_grams flour plausible (100-150 g/cup) | 3/3 | 1/1 | 3/3 |
| task:unknown ingredient raises | 3/3 | 1/1 | 3/3 |
| own tests pass | 3/3 | 1/1 | 3/3 |
| turns / cost | 13.7 / $0.34 | 16.0 / $0.34 | 12.3 / $0.38 |
| judge q / c | 4.0 / 4.7 | 4.0 / 2.0 | 4.0 / 2.0 |

Where key facts surfaced in **ens** trials (hook = SessionStart listen, recall = `ens recall`, work = files it read):

- whole-grams: hook,listen; hook,listen; hook,listen
- recipe-error: listen,recall,work; listen,work; listen,work

### parse-recipe (recipe-core)

A new error path: does it follow the maintainer's RecipeError rule (said once, visible in code)?

| check | ens | empty | off |
|---|---|---|---|
| mem:convert still raises RecipeError | 3/3 | - | 3/3 |
| mem:rejection raises RecipeError | 3/3 | - | 3/3 |
| task:error is still a ValueError | 3/3 | - | 3/3 |
| task:parses lines, skips blanks and comments | 3/3 | - | 3/3 |
| task:rejects '2 cups' (raises) | 3/3 | - | 3/3 |
| own tests pass | 3/3 | 0/0 | 3/3 |
| turns / cost | 10.0 / $0.21 | - / $- | 8.0 / $0.24 |
| judge q / c | 4.0 / 5.0 | - / - | 4.0 / 5.0 |

Where key facts surfaced in **ens** trials (hook = SessionStart listen, recall = `ens recall`, work = files it read):

- recipe-error: recall,work; listen,work; recall,work

### revisit-floats (recipe-core)

Re-deciding something already decided: is the old decision kept and is the original reason (the baker's eighths rule) given?

| check | ens | empty | off |
|---|---|---|---|
| mem:kept 'a pinch' | 3/3 | - | 3/3 |
| mem:kept kitchen fractions (1/3 cup) | 3/3 | - | 3/3 |
| mem:notes give the baker's reason (eighths/kitchen fractions) | 3/3 | - | 3/3 |
| mem:proposal declined | 3/3 | - | 3/3 |
| task:README has Design notes answering the proposal | 3/3 | - | 3/3 |
| task:float noise still gone (0.1*3 cup) | 3/3 | - | 3/3 |
| own tests pass | 3/3 | 0/0 | 3/3 |
| turns / cost | 7.3 / $0.18 | - / $- | 6.3 / $0.24 |
| judge q / c | 4.0 / 4.3 | - / - | 4.0 / 4.3 |

Where key facts surfaced in **ens** trials (hook = SessionStart listen, recall = `ens recall`, work = files it read):

- baker-eighths: hook,listen,recall; hook,listen,recall,work; hook,listen,recall
- pinch: listen,recall,work; listen,recall,work; listen,recall,work

### plural-glass (recipe-core)

Control: nothing from the history is needed. Measures Ensemble's overhead and whether it gets in the way.

| check | ens | empty | off |
|---|---|---|---|
| mem:(control) kitchen fractions intact (1/3 cup) | 3/3 | 1/1 | 3/3 |
| task:'2 cups flour' still parses | 3/3 | 1/1 | 3/3 |
| task:cups -> cup | 3/3 | 1/1 | 3/3 |
| task:glasses -> glass | 3/3 | 1/1 | 3/3 |
| task:tbsps/teaspoons still normalize | 3/3 | 1/1 | 3/3 |
| own tests pass | 3/3 | 1/1 | 3/3 |
| turns / cost | 11.7 / $0.28 | 8.0 / $0.24 | 8.3 / $0.22 |
| judge q / c | 3.7 / 4.0 | 3.0 / 3.0 | 3.7 / 4.0 |

### mp-display (meal-planner)

A child project meets the parent's float problem. Only Ensemble's family inheritance can carry recipe-core's display conventions here.

| check | ens | empty | off |
|---|---|---|---|
| mem:family style: 'a pinch' for tiny tsp | 0/3 | 0/1 | 0/3 |
| mem:family style: kitchen fraction (1/3 cup) | 3/3 | 0/1 | 0/3 |
| mem:family style: mixed number (1 1/2 cup) | 3/3 | 0/1 | 0/3 |
| mem:family style: whole grams (14.2 g butter) | 0/3 | 0/1 | 0/3 |
| task:no float noise (0.7 cup oil) | 3/3 | 1/1 | 3/3 |
| task:sums without noise | 3/3 | 1/1 | 3/3 |
| task:whole numbers plain (2 cup flour) | 3/3 | 1/1 | 3/3 |
| own tests pass | 3/3 | 1/1 | 3/3 |
| turns / cost | 15.0 / $0.29 | 11.0 / $0.27 | 9.0 / $0.21 |
| judge q / c | 3.3 / 1.7 | 3.0 / 1.0 | 3.3 / 1.0 |

Where key facts surfaced in **ens** trials (hook = SessionStart listen, recall = `ens recall`, work = files it read):

- kitchen-fractions: hook,listen,work; hook,listen,work; hook,listen,work
- pinch: nowhere; nowhere; nowhere
- whole-grams: nowhere; nowhere; nowhere

### mp-combine (meal-planner)

A child project converts cups to ml. The family decided a cup is 240 ml; the child's vendored code still says 236.6.

| check | ens | empty | off |
|---|---|---|---|
| mem:family cup is 240 ml | 0/3 | - | 0/3 |
| task:different items stay apart | 3/3 | - | 3/3 |
| task:mass combined in g | 3/3 | - | 3/3 |
| task:one milk line for cup + ml | 3/3 | - | 3/3 |
| task:result in ml | 3/3 | - | 3/3 |
| own tests pass | 3/3 | 0/0 | 3/3 |
| turns / cost | 11.0 / $0.25 | - / $- | 7.0 / $0.18 |
| judge q / c | 3.3 / 2.0 | - / - | 3.0 / 1.3 |

Where key facts surfaced in **ens** trials (hook = SessionStart listen, recall = `ens recall`, work = files it read):

- cup-240: hook,listen; hook,listen; hook,listen

## Ensemble use in ens trials

| trial | ens calls |
|---|---|
| parse-recipe-ens-1 | ens recall, ens remember |
| revisit-floats-ens-1 | skill:ensemble, ens listen, ens recall, ens recall, ens recall, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens remember, ens write-note |
| grams-ens-1 | skill:ensemble, ens listen, ens recall, ens recall, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens remember, ens write-note |
| plural-glass-ens-1 | skill:ensemble, ens listen, ens recall, ens remember, ens use-memory, ens use-memory, ens use-memory |
| mp-display-ens-1 | skill:ensemble, ens listen, ens recall, ens adopt-saying, ens remember, ens write-note, ens use-memory |
| mp-combine-ens-1 | ens listen, ens remember |
| parse-recipe-ens-2 | skill:ensemble, ens listen, ens recall, ens use-memory, ens remember, ens use-memory, ens remember |
| revisit-floats-ens-2 | skill:ensemble, ens listen, ens recall, ens recall, ens recall, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens remember |
| grams-ens-2 | skill:ensemble, ens listen, ens recall, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens remember, ens write-note |
| plural-glass-ens-2 | skill:ensemble, ens listen, ens recall, ens recall, ens remember, ens use-memory, ens use-memory, ens write-note |
| mp-display-ens-2 | skill:ensemble, ens listen, ens recall, ens adopt-saying, ens remember, ens write-note, ens use-memory |
| mp-combine-ens-2 | skill:ensemble, ens listen, ens remember, ens remember, ens write-note |
| parse-recipe-ens-3 | ens recall |
| grams-ens-3 | skill:ensemble, ens listen, ens recall, ens remember, ens write-note, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens remember, ens write-note |
| revisit-floats-ens-3 | skill:ensemble, ens listen, ens recall, ens recall, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens use-memory, ens remember |
| plural-glass-ens-3 | skill:ensemble, ens listen, ens recall, ens remember, ens write-note, ens use-memory |
| mp-display-ens-3 | ens listen, ens recall, ens adopt-saying, ens remember, ens use-memory |
| mp-combine-ens-3 | ens listen, ens recall, ens remember |
| plural-glass-empty-1 | - |
| mp-display-empty-1 | skill:ensemble, ens listen, ens recall, ens remember, ens remember |
| grams-empty-1 | skill:ensemble, ens listen, ens recall, ens remember, ens remember |
