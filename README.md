# Ensemble monorepo

| folder | what |
|---|---|
| [`packages/ensemble`](packages/ensemble) | Ensemble itself: the `ens` CLI, skills, SessionStart hook, MCP server, memory, dreams, poems, excursions and families. Install with `packages/ensemble/install.sh --hook`. |
| [`test-projects`](test-projects) | Small realistic projects to run Claude sessions against, related as a family (see `test-projects/family.json`). Each has a `tasks.json` of session prompts. |
| [`harness`](harness) | `lab.py`: runs headless Claude sessions and nights against the test projects, each run in its own isolated Ensemble home, with snapshots and a report. |

Quick start:

```bash
python3 harness/lab.py setup                                   # once: .lab/venv with Ensemble's deps
python3 harness/lab.py play smoke1 harness/scenarios/smoke.json --fake   # offline, seconds
python3 harness/lab.py play smoke2 harness/scenarios/smoke.json          # real Claude, a few minutes
open runs/smoke2/report.md
```

Ensemble's own tests: `cd packages/ensemble && python3 test_claude_code.py` (and the other `test_*.py`).
