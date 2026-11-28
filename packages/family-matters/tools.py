"""The tool surface each agent sees. Every tool returns a short string, written to be
cheap for an LLM to read. Plain functions with type hints and docstrings, so they
can be passed straight to Google ADK (`Agent(tools=player.tools())`) or any other
function-calling framework.
"""
import functools

from ensemble import CAP, Ensemble

# What the family calls things. Storage keeps the engine's words (tier "lesson", "dormant", sayings,
# heirlooms), so stores from before the Family Matters rename load unchanged; only what is shown changes.
SHOW_TIER = {"dormant": "repressed", "lesson": "blessing-and-a-curse"}
SHOW_KIND = {"saying": "advice", "heirloom": "baggage", "wisdom": "lore"}


def show_tier(tier):
    return SHOW_TIER.get(tier, tier)


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as err:          # tools report errors instead of crashing the agent
            return f"error: {err}"
    return wrapper


class Player:
    """memory: an optional memory.MemoryStore private to this agent. When given, listen()
    also shows the agent's strongest memories, the memory tools are added, the memory
    clock follows the ensemble's beat, and a conductor remembers every decision it closes."""

    MEMORY_LINES = 5

    def __init__(self, ensemble: Ensemble, name: str, memory=None, sleep_at=None, judge=None,
                 cycles=4, pairs_per_cycle=20, poet=None, poem_pairs=3, domain=None,
                 explorer=None, excursions=1, runner=None, family=None, family_member=None):
        """sleep_at: sleep (inside listen) once this many new memories have built up.
        judge: a dreams.py judge; defaults to HeuristicJudge tuned to the memory's thresholds.
        A conductor with memory raises its open tensions as Ensemble questions, and closing
        one resolves the tension: yes keeps the first memory, no the second, split keeps both."""
        self.e, self.name, self.memory = ensemble, name, memory
        self.seen = {name: None}
        self.sleep_at, self.cycles, self.pairs_per_cycle = sleep_at, cycles, pairs_per_cycle
        if judge is None and memory is not None:
            from dreams import HeuristicJudge
            judge = HeuristicJudge(low=memory.recall_min)
        self.judge = judge
        self.poet, self.poem_pairs, self.domain = poet, poem_pairs, domain   # compose after each sleep
        self.explorer, self.excursions, self.runner = explorer, excursions, runner   # then wander
        self.min_score, self.family = 0.5, None
        self.member = family_member or name        # who this player is in the family (usually the project)
        if family is not None and memory is not None:
            family.attach(self)                    # takes after its family: settings and sensitivities

    # ------------------------------------------------------------ everyone
    def listen(self) -> str:
        """Hear the whole ensemble at once: the beat, which agents' parts changed since you
        last read them, and where the group stands on every open question. Call this first,
        each turn, before reading any individual part."""
        st = self.e.state()
        changed = [f"{p['agent']} v{p['version']}" for p in st["parts"]
                   if p["agent"] != self.name and p["version"] and self.seen.get(p["agent"]) != p["version"]]
        full = [p["agent"] for p in st["parts"] if p["fill"] > 0.9]
        lines = [f"beat {st['beat']} | changed: {', '.join(changed) or 'none'}"
                 + (f" | nearly full: {', '.join(full)}" if full else "")]
        for qid, r in st["score"].items():
            if "lean" in r:
                flag = "  <- CONFLICT" if r["conflict"] else ""
                lines.append(f"{qid}: {r['verdict'].upper()} {r['lean']:+.2f} w{r['weight']:.1f}{flag}")
                if r.get("text"):
                    lines.append(f"  ({r['text']})")
            else:
                shares = sorted(r["shares"].items(), key=lambda kv: -kv[1])
                lines.append(f"{qid}: " + " ".join(f"{o} {s:.0%}" for o, s in shares) + f" w{r['weight']:.1f}")
        if self.memory is not None:
            self.memory.advance_to(st["beat"])
            if self.sleep_at and self.memory.sleep_due(self.sleep_at):
                lines.append(self.memory.sleep(self.judge, self.cycles, self.pairs_per_cycle,
                                               min_score=self.min_score)["report"])
                if self.poet is not None:
                    lines.append(self.memory.compose(self.poet, self.poem_pairs, domain=self.domain)["report"])
                if self.explorer is not None:
                    lines.append(self.memory.wander(self.explorer, self.excursions, runner=self.runner)["report"])
            if self.name == self.e.conductor:
                for t in self.memory.open_tensions():
                    if not t["raised"] and t["a_text"] and t["b_text"]:
                        q = f"tension-{t['id']}"
                        self.e.open_question(q, text=f'Does "{t["a_text"][:120]}" take precedence over '
                                                     f'"{t["b_text"][:120]}"? (split = both hold)')
                        self.memory.mark_raised(t["id"])
                        lines.append(f"raised {q} for a vote")
                        lines.append(f'  (Does "{t["a_text"][:80]}" take precedence over "{t["b_text"][:80]}"?)')
            context = " ".join(f"{q} {r.get('text', '')}" for q, r in st["score"].items())
            for l in self.memory.lessons_for(context):
                lines.append(f"blessing-and-a-curse {l['id']}: {self.memory.read(l['id'])}")
            if self.family is not None and self.name == self.e.conductor:
                sug = self.family.suggest(self.member)
                if sug:
                    lines.append(f"suggest: {self.member} may be ready to move out as a new generation ("
                                 f"{'; '.join(sug['reasons'])}). Awaiting your approval.")
            if self.family is not None:
                fam = self.family._load()
                # Advice matches the open questions; with none open (the usual case), show what this
                # project was handed instead, or a child never hears its parents at all.
                handed = self.family.advice(self.member, context) or self.family.inheritance(self.member)
                lines += self._family_lines(fam, handed)
            mem = self.memory.summary().splitlines()
            lines.append("memory: " + mem[0].split(" | ", 1)[1].split(" | ")[0])
            lines += [f"  {l}" for l in mem[1:1 + self.MEMORY_LINES]]
        return "\n".join(lines)

    def _family_lines(self, fam, items):
        return [f"family {SHOW_KIND.get(a['kind'], a['kind'])} {a['id']} ("
                f"{self.family.describe_origin(fam, self.member, a['item'])}, unsolicited, advice only): "
                f"{a['item']['text']}" for a in items]

    @_safe
    def read_part(self, agent: str) -> str:
        """Read one agent's current note and declared votes. Only do this for parts that
        listen() reports as changed and that matter to your task."""
        ver, obj = self.e.read(agent)
        self.seen[agent] = ver
        if obj is None:
            return f"{agent}: (empty)"
        votes = ", ".join(f"{q}={'yes' if v[0] == 1 else 'no' if v[0] == -1 else v[0]}@{v[1]:g}"
                          for q, v in obj["v"].items())
        return f"{agent} v{ver}: {obj['note']}" + (f"\nvotes: {votes}" if votes else "")

    @_safe
    def write_note(self, text: str) -> str:
        """Replace your note with your CURRENT state: what you are doing, what you need,
        what you decided. It overwrites the previous note; it is not a log. Keep it short."""
        ver, size = self.e.note(self.name, text)
        return f"saved v{ver} ({size}/{getattr(self.e, 'cap', CAP)} bytes)"

    @_safe
    def vote(self, question: str, answer: str, confidence: float) -> str:
        """Vote on an open question. answer is 'yes'/'no' for yes-no questions, or one of the
        listed options. confidence is 0 to 1 and scales your weight. Voting again replaces
        your earlier vote. Votes fade each beat, so re-vote to keep a position alive."""
        ver, _ = self.e.cast(self.name, question, answer, confidence)
        return f"vote recorded (part v{ver})"

    @_safe
    def withdraw(self, question: str) -> str:
        """Remove your vote on a question."""
        self.e.withdraw(self.name, question)
        return "withdrawn"

    # ---------------------------------------------------------- conductor
    @_safe
    def open_question(self, question: str, options: list[str] | None = None, text: str | None = None) -> str:
        """Conductor only. Open a question for the ensemble: yes/no by default, or a choice
        between options. text optionally explains what is being decided."""
        self._conductor()
        self.e.open_question(question, options, text)
        return f"opened '{question}'"

    @_safe
    def close_question(self, question: str) -> str:
        """Conductor only. Close a question and clear it from the score."""
        self._conductor()
        result = self.e.state()["score"].get(question)
        self.e.close_question(question)
        if self.memory is not None and result:
            if "lean" in result:
                text = (f"Decided '{question}': {result['verdict']} (lean {result['lean']:+.2f}, "
                        f"weight {result['weight']:.1f})")
                importance = 0.3 + 0.5 * abs(result["lean"])
            else:
                top = max(result["shares"], key=result["shares"].get)
                text = f"Decided '{question}': {top} ({result['shares'][top]:.0%} of support)"
                importance = 0.3 + 0.5 * result["shares"][top]
            mid = self.memory.remember(text, importance, source="decision")
            if question.startswith("tension-") and "lean" in result:
                winner = {"yes": "a", "no": "b"}.get(result["verdict"], "both")
                self.memory.resolve_tension(question[len("tension-"):], winner)
                return f"closed '{question}', tension resolved ({winner}), remembered as {mid}"
            return f"closed '{question}' and remembered it as {mid}"
        return f"closed '{question}'"

    @_safe
    def next_beat(self) -> str:
        """Conductor only. Advance time one beat; every vote fades a little."""
        self._conductor()
        return f"beat {self.e.beat()}"

    @_safe
    def audit(self) -> str:
        """Check the score against what every agent declared in its part. Flags any question
        where someone played a vote they did not declare, or the score is damaged."""
        flags = self.e.audit()
        return "audit clean" if not flags else "audit: " + "; ".join(
            f"{f['question']} off by {f['off_by']}" for f in flags)

    def _conductor(self):
        if self.name != self.e.conductor:
            raise PermissionError("only the conductor can do that")

    def idle(self, focus: str) -> str:
        """Call when this agent is idle: a short daydream around what it is working on."""
        if self.memory is None:
            return "no memory"
        ev = self.memory.daydream(self.judge, focus)
        return (f"daydreamed {ev['pairs']} pairs: {ev['connections']} connections, "
                f"{ev['proposed']} proposals for the next sleep")

    # ------------------------------------------------------------- memory
    @_safe
    def remember(self, text: str, importance: float, replaces: str = "") -> str:
        """Store something in your own long-lived memory. importance is 0 to 1. If it overturns
        an earlier memory (a decision changed, a fact went stale), give that memory's id in
        replaces (comma-separated for several): the old one stops being shown or handed down."""
        old = [x.strip() for x in (replaces or "").split(",") if x.strip()]
        mid = self.memory.remember(text, importance, source=self.name, replaces=old)
        if old:
            return f"stored {mid}, replacing {', '.join(old)}"
        near = self.memory.near(mid, k=2)
        if not near:
            return f"stored {mid}"
        return (f"stored {mid}. Close to: " + "; ".join(f'{n["id"]} "{n["head"][:70]}"' for n in near)
                + f". If {mid} overturns one of these, run: fam revise-history OLD_ID {mid}")

    @_safe
    def replace_memory(self, old_id: str, new_id: str) -> str:
        """Mark memory old_id as overturned by new_id (both already stored). The old one leaves the
        summary and recall (recall shows new_id instead), and is never handed down to the family."""
        self.memory.replace(old_id, new_id)
        return f"{old_id} is now replaced by {new_id}"

    @_safe
    def recall(self, cue: str, strength: float) -> str:
        """Search your memory by meaning. strength (0 to 1) is how strongly the situation
        calls for it: only a strong, closely matching cue wakes a dormant memory."""
        hits = self.memory.recall(cue, strength)
        lines = [f"{h['id']} [{h['how']}, {show_tier(h['tier'])}, sim {h['similarity']}"
                 + (f", OUTDATED: see {h['superseded_by']}" if h.get("superseded_by") else "")
                 + (f", current answer, replaces {', '.join(h['replaces'])}" if h["how"] == "replacement" else "")
                 + f"] {self.memory.describe(h['id'])}" for h in hits]
        if self.family is not None:                 # relatives may have met this before
            lines += self._family_lines(self.family._load(), self.family.advice(self.member, cue, k=3))
        return "\n".join(lines) or "nothing matched"

    @_safe
    def use_memory(self, memory_id: str) -> str:
        """Mark that you relied on a memory. It gets stronger and permanently harder to forget."""
        row = next((r for r in self.memory.rows() if r["id"] == memory_id), None)
        if row and row.get("superseded_by"):        # relying on what was overturned should not revive it
            return f"{memory_id} was replaced by {row['superseded_by']}: use that one instead (nothing changed)"
        r = self.memory.use(memory_id)
        return f"{r['id']} now {show_tier(r['tier'])} {r['strength']:.2f}"

    @_safe
    def lessons(self) -> str:
        """List your blessings-and-curses (lessons): hardened knowledge that never fades and that only a vote can overturn."""
        ls = self.memory.lessons()
        return "\n".join(f"{l['id']}: {l['text']}" for l in ls) or "no blessings or curses yet (give it time)"

    @_safe
    def adopt_saying(self, saying_id: str) -> str:
        """Take a family saying or heirloom (s0004, h0005) into your own memory. It starts unproven:
        use it to confirm it."""
        fam = self.family._load()
        s = fam["sayings"].get(saying_id) or fam["heirlooms"].get(saying_id)
        if s is None:
            return f"no family advice or baggage {saying_id}"
        mid = self.memory.remember(s["text"], 0.5, source=f"family:{saying_id}")
        return f"adopted as {mid} (inherited, unconfirmed)"

    def tools(self) -> list:
        base = [self.listen, self.read_part, self.write_note, self.vote, self.withdraw, self.audit]
        if self.name == self.e.conductor:
            base += [self.open_question, self.close_question, self.next_beat]
        if self.memory is not None:
            base += [self.remember, self.replace_memory, self.recall, self.use_memory, self.lessons]
        if self.family is not None:
            base.append(self.adopt_saying)
        return base
