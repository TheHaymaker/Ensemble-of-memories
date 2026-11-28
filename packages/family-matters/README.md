<img src="../../assets/logo.svg" alt="Family Matters logo" width="96" align="right">

# Family Matters

Long-lived memory for Claude Code, with all the warmth and dysfunction of a real family. For the overview, results and diagrams, see the [main README](../../README.md). This page is the reference.

## Install

```bash
./install.sh --hook          # from this folder; add --mcp to also register an MCP server
```

- **`fam`** in `~/.local/bin`, with its own Python environment in `~/.family-matters/venv`.
- **Skills** in `~/.claude/skills`: `family-matters` (everyday use) and `thats-not-how-i-remember-it` (a night), plus seven aliases for the night: `/things-will-look-better-in-the-morning`, `/we-dont-talk-about-that`, `/lets-not-air-dirty-laundry`, `/who-told-you-that`, `/youll-understand-when-youre-older`, `/dont-make-me-come-in-there` and `/go-to-your-room-and-think-about-what-you-did`.
- **With `--hook`**, a SessionStart hook that runs the briefing (`fam --listen`). Your `~/.claude/settings.json` is backed up and merged, not replaced.

Claude then uses the skills on its own. Run a night when `fam gossip` says therapy is overdue.

**Projects** are named after the folder Claude Code starts in, or `FAM_PROJECT`. `FAM_PARENTS=other-project` makes a new project a child of another. Subagents pass `--agent NAME`. Moving out and adoption are always your call: the skill tells Claude to ask you first.

**Embeddings:** keyword matching by default, no setup. For meaning-based recall, set `FAM_EMBEDDER=hybrid` (keywords first, then a local model2vec model, about 30 MB), `model2vec` or `gemini` before a project's first use, and install that package into `~/.family-matters/venv`. On 15 labelled cues from real sessions, `hybrid` found 14, keywords 12 and model2vec alone 8.

**Upgrading an old `ens` install:** re-run `./install.sh` with the same flags. It moves `~/.ensemble` to `~/.family-matters` (leaving a symlink), makes `ens` a shim for `fam`, swaps in the new skills and hook, and with `--mcp` re-registers the server as `family-matters`. Old command names and `ENSEMBLE_*` variables still work.

## What the family calls things

Storage and the engine docs below keep the engine's words, so nothing on disk changed in the rename.

| command or name | what it is | engine's word |
|---|---|---|
| `fam gossip` | the session-start briefing | listen |
| `fam never-forget "..." [--replaces m00003]` | store a memory | remember |
| `fam bring-up "..."` | search memory | recall |
| `fam told-you-so m00012` | a memory helped (strengthens it) | use-memory |
| `fam revise-history OLD NEW` | a newer memory overturns an older one | replace-memory |
| `fam lessons` (or `blessings`, `curses`) | blessings-and-curses: hardened knowledge that never fades | lessons |
| repressed | faded out of the briefing, still searchable | dormant |
| `fam vent` / `fam eavesdrop builder` | your note / read another agent's | write-note / read-part |
| `fam start-argument` / `take-sides` / `settle-argument` | a question the household votes on | open-question / vote / close-question |
| `fam time-heals` | advance one beat | next-beat |
| `/thats-not-how-i-remember-it` | a night (therapy): dreams, poems, excursions | sleep |
| `fam take-advice s0004` | adopt unsolicited advice from a relative | adopt-saying |
| baggage | memories handed down intact | heirlooms |
| `fam generational-trauma` (or `received-wisdom`) | inherited sensitivity to a theme | epigenetic marks |
| family lore | a lesson several relatives learned on their own | family wisdom |
| `fam thanksgiving` | the family reunion | family-reunion |
| `fam move-out` / `fam stay-home` | accept or snooze a new generation | approve / decline-generation |
| `fam midlife-crisis "v2 rewrite"` | declare a milestone now | declare-milestone |
| `fam adopt other-project` | approve proposed kinship | approve-kin |
| `fam tree` / `fam identity-crisis` | draw the family / where this project lives | family-tree / whoami |

## Under the hood: the shared-score engine

The engine keeps its original file and class names (`ensemble.py`, `MdEnsemble`, `tools.Player`),
and the sections below use its vocabulary.

Shared state for a multi-agent system, held in **one fixed-size WAV file** (196,652 bytes, 2.05 s, 48 kHz mono 16-bit). It holds up to 9 agents and 32 open questions. The file never grows.

```
bins 5,7,9    PILOTS  fixed tones: find time offset and gain in any copy
bins 10-73    SCORE   consensus tones. A vote is a tone, + phase for yes, - for no,
                      scaled by confidence, plus a confidence-only "weight" tone.
                      Adding tones together does the tally: one FFT reads every question.
bins 80-457   PARTS   one OFDM band per agent (QPSK, zlib, CRC32), 953 compressed
                      bytes each. Each agent overwrites only its own band.
```

## The ideas

- **The mix is the tally.** Nobody counts votes. Agreement adds up and disagreement cancels out. A quiet vote tone under a loud weight tone means confident agents disagree, which is flagged as a conflict.
- **Listen first, read later.** `listen()` returns the beat, which parts changed, and every question's verdict in a few lines. Agents read individual parts only when it matters.
- **The score is checked against the parts.** Every agent declares its votes in its own part and also plays them into the score. `audit()` replays the declared votes and compares them with the score, which catches undeclared votes and damage.
- **Old notes fade.** Each beat multiplies the score by `gamma` (0.97 by default). Votes nobody re-affirms die out, so a crashed agent stops counting without any cleanup.
- **Flat memory.** Parts hold current state, not a log. Each part has a hard size cap, and the file's size is fixed.
- **Conflict-free merge.** Parts never overlap and the score is additive, so copies that diverged on two hosts merge as `a + b - base`.
- **Lossy transport.** The score survives MP3 compression and time shifts; the pilots realign and rescale the copy.

## Files

| file | what |
|---|---|
| `ensemble.py` | the storage engine |
| `tools.py` | `Player`: the LLM-facing tools (`listen`, `read_part`, `write_note`, `vote`, `withdraw`, `audit`, plus `open_question`, `close_question`, `next_beat` for the conductor) |
| `test_ensemble.py` | 9 robustness tests |
| `simulate.py` | 60-beat benchmark against a message thread and markdown files (`python3 simulate.py out md` for the markdown backend) |
| `mdensemble.py` | the same protocol on plain markdown files, with fade computed at read time, and `export_wav()` to render the state as a WAV |
| `test_md.py` | the same 9 tests on the markdown backend, plus export through MP3 |
| `memory.py`, `test_memory.py` | tiered memory store with dormancy, revival and buffs |
| `embeddings.py`, `calibrate.py`, `test_integration.py` | embedder adapters, threshold calibration, end-to-end tests |
| `dreams.py`, `poets.py`, `explorers.py`, `test_sleep.py`, `test_lessons.py`, `test_poems.py`, `test_excursions.py` | dream judges, poets, explorers and their tests |
| `family.py`, `family_view.py`, `test_family.py`, `test_generations.py` | families of projects: traits, marks (generational trauma), sayings (advice), heirlooms (baggage), reunions, coming of age, kinship |
| `fam.py`, `install.sh`, `claude/skills/*`, `test_claude_code.py` | Claude Code: the `fam` command and MCP mode, installer, skills, tests |
| `compare.py` | runs the benchmark on both backends and draws `head_to_head.png` |

## Use with Google ADK

```python
from google.adk.agents import Agent
from ensemble import Ensemble
from tools import Player

ROSTER = ["conductor", "backend", "frontend", "tests"]
mix = Ensemble("mix.wav", ROSTER)          # same path and roster for every agent

agents = [Agent(name=n, model="gemini-2.5-flash", tools=Player(mix, n).tools(),
                instruction="Each turn: listen() first. Read only the parts you need. "
                            "Keep your note to your current state. Vote on open questions.")
          for n in ROSTER]
```

## Test results

| test | result |
|---|---|
| 2,000 random writes | every part exact, file stayed 196,652 bytes |
| 300 random votes, withdrawals and beats | worst deviation from a plain ledger 0.004; audit clean |
| undeclared vote | caught by `audit()` |
| 8 processes writing at once | no lost writes; score matches the parts |
| shift 337 samples + gain 0.6 + noise | offset and gain recovered; verdicts match |
| MP3 at 128, 64 and 32 kbps | verdicts match, worst error 0.012; **parts destroyed** |
| three-way merge across two hosts | parts identical to doing every operation on one host; score within 0.001 |
| crashed agent | its confident "no" fades until the verdict flips |
| latency | about 1–3 ms per operation |

**Benchmark** (60 beats, 9 scripted agents; tokens are approximated as characters / 4):

| | conductor tokens | storage |
|---|---|---|
| message thread | 19,390 | 78 KB and growing |
| markdown files (read when changed) | 25,976 | 2.9 KB, flat |
| **shared score (audio)** | **4,648** | 196.7 KB, fixed |

Verdicts read from the score matched the ledger at all 120 checks. The audit caught the faulty agent the beat it acted.

## Markdown backend: head to head

`MdEnsemble` has the same interface, so `tools.Player` and the benchmark run on it unchanged.

| | conductor tokens | storage | per-op latency | limits |
|---|---|---|---|---|
| message thread | 19,390 | 78 KB, growing | | |
| plain markdown files | 25,976 | 2.9 KB | | |
| shared score, audio | 4,648 | 196.7 KB, fixed | 1-3 ms | 9 agents, 32 questions, 953 B parts |
| **shared score, markdown** | **4,613** | **3.4 KB, bounded** | **0.2-0.4 ms** | any agents, ~125 questions per 4 KB conductor file |

Markdown tallies are exact (no 0.001 grid), merges are exact, and the files can be read and diffed. Instead of the audio-style audit, the markdown audit checks that `score.md` still matches the parts it was built from, so a hand-edited summary is caught.

**Recommendation:** run the markdown backend and call `export_wav()` when you need audio: to listen in, to send the tally over an audio-only channel, or to test an audio-native model.

## Tiered memory (`memory.py`)

A memory store on plain files with four tiers. Strength fades each beat at the tier's rate, down to a permanent floor.

| tier | fades per beat | how a memory gets there |
|---|---|---|
| short | x0.80 | new memories |
| intermediate | x0.95 | 2 uses at least 3 beats apart |
| long | x0.99 | 5 spaced uses |
| dormant | stops fading | strength fell below 0.05; left out of the summary |

- **Buffs:** every use or recall raises the floor permanently. The n-th buff adds 0.02/n, and the floor is capped at 0.15. After 7 uses the floor sits above the dormant line, so the memory can never go dormant.
- **Spacing, not cramming:** uses in the same beat don't promote. Only spaced uses do.
- **Revival:** a dormant memory wakes only when similarity x cue strength >= 0.5. It returns to short-term with a buff, and sinks again unless it's used.
- **Flat reading:** agents read `summary.md`, the 12 strongest active memories (about 150-200 tokens), however many memories exist.
- **Similarity** is keyword overlap by default; pass `MemoryStore(root, similarity=...)` to use embeddings.
- **Agent tools:** `store.tools()` returns `memory_summary`, `remember`, `recall` and `use_memory`.

`test_memory.py` runs 6 tests and draws `memory_life.png` (300 beats, four example memories, tier counts against summary size). With 2,000 memories over 500 beats, the summary stayed under about 200 tokens while 1,425 memories sat dormant on disk.

## Embeddings and per-agent memory

```python
from embeddings import GeminiEmbedder          # or Model2VecEmbedder(), SentenceTransformerEmbedder()
from mdensemble import MdEnsemble
from memory import MemoryStore
from tools import Player

emb = GeminiEmbedder()                         # needs GOOGLE_API_KEY (or Vertex AI env settings)
mix = MdEnsemble("state", ["conductor", "backend", "frontend"])
players = {n: Player(mix, n, memory=MemoryStore(f"memory/{n}", emb)) for n in mix.roster}
tools = players["conductor"].tools()           # 12 tools for the conductor, 9 for the others
```

- **Each agent has private memory.** `listen()` adds its 5 strongest memories under the shared summary.
- **Memory tools:** `remember`, `recall` (search by meaning; a strong, close cue revives dormant memories) and `use_memory`.
- **Decisions become memories.** When the conductor closes a question, the verdict is stored in its memory, weighted by how clear the vote was.
- **One clock.** Memory fades on the score's beat.
- **Embedding calls never hold the lock.** Text is embedded before the store is locked, so a slow API call doesn't block other agents.
- **A store keeps its embedder.** Opening it with a different one is refused, since the vectors wouldn't be comparable.

**Calibrate on your machine before relying on revival.** `python3 calibrate.py gemini` scores 24 labeled pairs whose related cues mostly share no key words with the memory, then suggests `recall_min` and `revive`. Pass them as `MemoryStore(..., recall_min=, revive=)`. Results from this sandbox, where no real sentence model could be downloaded:

| embedder | AUC (1.0 = perfect, 0.5 = chance) |
|---|---|
| keywords | 0.64 |
| spaCy word vectors | 0.74 |
| test embedder (`ConceptEmbedder`, for tests only) | 0.82 |

The Gemini, model2vec and sentence-transformers adapters are written but **not run here**. I'd want at least 0.9 AUC before trusting revival.

`test_integration.py` runs 6 tests with the deterministic test embedder:
- a cue with no shared words revives the right memory, where keywords miss it;
- vectors persist across reopening;
- decisions are remembered, go dormant and are revived by a paraphrase;
- 8 processes write concurrently without loss;
- Google ADK builds all 12 tools;
- calibration runs.

## Sleep, daydreams, lessons and poems (`memory.py`, `dreams.py`, `poets.py`)

**Sleep** happens when enough new memories have built up (sleep pressure, 30 by default), not on a clock. A night is 4 cycles:
- **Consolidation phase:** recent memories are paired with their nearest older ones, together with any daydream proposals and open tensions.
- **Association phase:** distant pairs are drawn at random, and dormant memories get guaranteed turns, longest-unreplayed first.
- **The mix shifts through the night:** the cycles run 80, 60, 40 and then 20% consolidation.
- **Three-step locking:** each pass samples under the lock, judges without it, and applies under it.

A judge gives each pair one outcome:

| outcome | effect |
|---|---|
| reinforce | both decay slower; a dormant duplicate is merged into its partner |
| add | a new link, stored as an unconfirmed idea |
| qualify | both are right under different conditions: both kept at full strength, linked to a memory naming when each applies |
| substitute / subtract | the newer replaces or contradicts the older, which is cut to 30% and marked outdated (a replaced memory is no longer briefed or handed down) |
| tension | an unclear conflict: stored, and raised as a vote by the conductor; yes keeps the first memory, no the second, split keeps both |

**Trust rules:**
- **Dream ideas need confirmation.** A dream-made idea can't overrule a waking memory; the attempt becomes a tension instead. After 2 waking uses, the idea counts as confirmed.
- **Lessons are hardened.** Dreams can never weaken a lesson; only a vote can.
- **Poems settle nothing.** Dreams may link or reinforce a poem's lines, nothing more.

**Daydreams** (`Player.idle(focus)`) pair the memories closest to the current work with older or dormant ones. They can link, reinforce, qualify and raise tensions, but replacements and contradictions are only proposed, for the next sleep to re-judge.

**Vacating** archives a dormant memory when either of these holds:
- **Evidence:** it had 5 dream exposures with nothing coming of it, and sat untouched for 50 x (1 + uses + 2 x revivals) beats.
- **Backstop:** it sat untouched for 4 times that period.

Unconfirmed dream ideas get half the grace. A cheap similarity screen counts a dormant memory with no plausible partner as a fruitless exposure without a judge call. Archived memories go to `archive.jsonl.gz`; `search_archive()` and `restore()` bring them back.

**Lessons** (shown as *blessings-and-curses*) form at the end of a night from memories that:
- were learned or confirmed while awake;
- have been used 4 or more times (3 to 5, by the family's steadiness);
- have been consolidated (intermediate or long-term) for 2 nights;
- have been reinforced in a dream;
- are neither outdated nor in an open dispute.

Lessons don't fade, are listed in `lessons.md` (capped at 40), and appear in `listen()` on their own when an open question touches them.

**Poem-making** (`compose()`, run after each sleep when the Player has a poet) is not sense-making:
- **Disparate pairs:** it pairs the most unrelated memories, lessons and optional domain text.
- **Refusing the likely:** the poet offers many candidates per figure and alias, each with a likelihood: the model's token log-probs where available, its verbalized probability otherwise, and word frequency offline. The likelier half is always refused, and the least likely candidate that still passes the **precision gate** is kept. The gate requires a name to point unambiguously to its own memory.
- **Outputs:** kept names become extra search keys. Figures are unconfirmed ideas. Probes ask where a lesson stops holding. Verses go to `poems.md` (the last 12).
- **Poets:** `GeminiPoet` uses verbalized sampling and, on Vertex AI, real log-probs. `LlamaCppPoet` uses the XTC sampler on a local model. Neither was run here. `HeuristicPoet` is an offline lexicon.

**Excursions** (`wander()`, run after poem-making when the Player has an explorer) are curiosity that acts:
- **Seeds:** an unexplored poem figure, probe or dream link, or two unrelated memories ("what if X met Y?").
- **Forms:** the explorer does a build-out, an experiment, a thought exercise or a hypothesis, even when the idea is silly, trivial or nonsensical.
- **Field notes:** every note is kept as a memory marked *imagined*, with its verdict, plus up to 2 ideas it spawned. The last 20 notes are in `excursions.md`.
- **Never facts:** excursions can't settle anything.
- **Hypotheses can come true:** a hypothesis carries a prediction. When a later waking memory matches it, the hypothesis is confirmed and can climb toward a lesson.
- **Code only in your sandbox:** experiments run code only through a `runner` you pass in.
- **Explorers:** `GeminiExplorer` is an LLM, not run here; `HeuristicExplorer` uses templates.

**Tests:**
- `test_sleep.py` (9, plus the `sleep.png` long run: memories held level off around 500 with a compressed archive);
- `test_lessons.py` (5);
- `test_poems.py` (8);
- `test_excursions.py` (7).

## Families (`family.py`)

Projects form a family: resemblance, not rules. Each project keeps its own memory store; `family.json` holds only what passes between them.

- **Traits are tendencies read from how a project actually lived:**
  - curiosity (excursions per night);
  - skepticism (how many of its dream and poem ideas never got confirmed);
  - steadiness (how rarely its knowledge was overturned);
  - expressiveness (how many names its memories gained).

  They show up as settings: excursions per night, poem pairs, the judge's bar, uses needed to confirm an idea, and uses needed for a lesson. A child starts from its relatives' traits blended by closeness: parent 1, grandparent 0.5, sibling 0.3, aunt or uncle 0.15. Its own experience takes over as it lives, weighted nights / (nights + 3).
- **Epigenetic marks:** `mark(member, theme)` records a big experience as heightened sensitivity to a theme.
  - **Inheritance:** marks pass parent to child at half strength, so a grandparent's arrives as a quarter, unless a calm parent let it fade first.
  - **Renewal and fading:** a similar experience renews a mark at full strength; a calm life fades an inherited one by 0.85 per night.
  - **Effect:** a marked agent gives related memories more importance.
- **Told at birth:** when a child project is born, each parent tells it its 3 most relied-on memories
  (lessons first) as sayings, so a young parent with no lessons yet still passes on what it knows.
- **Heard without asking:** `listen()` shows advice matching the open questions; with none open, it
  shows what this member was handed (heirlooms from its predecessor, then its ancestors' sayings).
  `recall()` also returns family advice matching the cue.
- **Sayings:** lessons told as family advice, shown in `listen()` when relevant as "advice only", with who learned them and how far back. They carry no authority. `adopt_saying` brings one into the agent's memory as an inherited idea that must be confirmed by use. Reunions raise the weight of sayings that were confirmed and lower those that were voted down.
- **Heirlooms:** a few specific memories handed down intact, with their context.
- **Reunions:** members tell their lessons, adopted sayings are scored, and lessons that recur across members become family wisdom.
- **Capped:** 60 sayings, 12 heirlooms, 20 pieces of wisdom and 10 marks per member. Over 12 generations and 120 lessons, `family.json` grew from 9 KB to 11 KB.

**What a family is:** related projects, declared by you, plus kinship that reunions propose when unrelated projects keep learning the same lessons. Approve with `approve_kin()` and the pair counts as siblings; `decline_kin()` stops the proposal.

**Generations within a project:** a long-lived project comes of age when the world its memories describe has changed, not when it gets big (memory is already flat).
- **The conductor suggests** in `listen()`, for your approval, on any of:
  - **drift:** at least 3 pieces of knowledge overturned, 15% or more of its waking memories;
  - **age:** 60 nights in one generation;
  - **possible milestones:** memories that mention a release, launch, rewrite, pivot, migration or handover.
- **You decide:** `approve()` accepts; `decline()` snoozes the suggestion for 14 nights and stops flagging those notes.
- **You can also declare one:** `milestone(name, root, note)` takes effect at once.
- **What coming of age does:** the current generation retires as the parent. Its lessons become sayings, its 3 most relied-on memories become heirlooms, and traits and marks pass on. `project@2` starts with clean everyday memory and hears its predecessor as "your parent, advice only".

**Seeing the tree** (`family_view.py`):
- `render_html(family, path)` writes one self-contained page. Generations are rows; a thick line marks a project coming of age, a dashed line approved kinship, and retired members are faded. Each member shows trait bars and mark dots, plus a yellow dot for a pending suggestion. Clicking a member shows its traits, marks, sayings and heirlooms.
- `to_mermaid(family)` gives the same tree as a Mermaid flowchart for GitLab, Confluence or GitHub.

`test_family.py` has 9 tests on a three-generation family: a founder with a credential leak, one branch that lived through another leak, one calm branch, grandchildren on both sides, and a child that turned out less curious than it was born.

## Honest assessment

- **The token savings come from the protocol, not from audio.** Markdown files plus a script that tallies votes and writes the same summary would cost about the same tokens, and would be 70 times smaller on disk.
- **What audio adds:**
  - one portable artifact holding both messages and consensus;
  - tallying with no tally process;
  - a score that survives MP3 and other lossy transport;
  - a three-way merge with no conflicts;
  - a redundant encoding that makes the audit possible;
  - a file a human can play.
- **Limits:**
  - 9 agents, 953 compressed bytes per part, 32 open yes/no questions.
  - Parts need lossless storage.
  - The mix is anonymous; `audit()` shows that something is wrong, not who did it, though the declared parts let you narrow it down.
  - Every write rewrites the whole 197 KB file under one lock, so the design is for agents taking turns, not for thousands of writes per second.
  - The benchmark agents are scripted, so the test measures the protocol, not model behavior.
