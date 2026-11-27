"""Tiered memory for agents: short, intermediate, long and dormant.

    <root>/index.json         metadata for every memory (strength, floor, tier, keywords)
    <root>/memories/<id>.md   the memory text
    <root>/summary.md         the strongest active memories: what agents read each turn

Every memory has a strength. It fades each beat at its tier's rate, down to a
permanent floor. Using a memory (or recalling it) adds strength and raises the
floor a little: a permanent buff, smaller each time and capped.

  short-term      fades fast       (x0.80 per beat)
  intermediate    fades slowly     (x0.95)  after 2 uses spaced >= 3 beats apart
  long-term       barely fades     (x0.99)  after 5 spaced uses
  dormant         strength fell below 0.05: out of the summary, no longer fades,
                  costs nothing to read. Comes back only when a cue matches it
                  closely AND is strong (similarity x cue strength >= 0.5).

Fade is computed when strength is read; nothing is rewritten each beat.
Massed repetition (many uses in one beat) does not promote: spacing does.
A floor above the dormant line (about 7 uses) means a memory can never go dormant.

Above long-term sit LESSONS: hardened, unfading, changed only by a vote. Below everything
is the ARCHIVE. Sleep (consolidation + association cycles), daydreams and poem-making are
further down in this file; see README for the full design.
"""
import fcntl
import gzip
import itertools
import json
import math
import os
import random
import re
from contextlib import contextmanager

import numpy as np

GAMMA = {0: 0.80, 1: 0.95, 2: 0.99}
TIER = {0: "short", 1: "intermediate", 2: "long"}
PROMOTE_AT = {1: 2, 2: 5}         # spaced uses needed to reach consolidation level
SPACING = 3                        # beats between uses for a use to count as spaced
DORMANT = 0.05
BUFF0, FLOOR_CAP = 0.02, 0.15      # n-th buff adds BUFF0 / n, floor never exceeds the cap
S_MAX = 1.0
REVIVE = 0.5                       # similarity x cue strength needed to wake a dormant memory
REVIVED_AT = 0.6
RECALL_MIN = 0.3                   # similarity needed for an active memory to count as recalled
SUMMARY_K = 12
SLOW_CAP = 3.0                     # dream buffs: decay exponent divided by (1 + slow), slow <= cap
FRUITLESS_K = 5                    # dream exposures with no connection before a dormant memory may go
MIN_AGE = 50                       # ...and beats untouched, times (1 + uses + 2 x revivals)
SLEEP_PRESSURE = 30                # new waking memories that make sleep due
DREAM_SOURCES = ("dream", "qualify", "tension", "poem", "probe", "excursion", "prediction")
IMAGINED = ("poem", "probe", "excursion", "prediction")   # language and play: never referents, never facts
PRECISION_MARGIN = 0.02            # an alias must be this much closer to its memory than to any other
LESSON_USES, LESSON_NIGHTS, LESSON_CAP = 4, 2, 40   # what it takes to harden into a lesson; most lessons kept
# (8 uses over 3 nights in long-term was reachable in 600-beat simulations, never in a project with a
# few sessions a week: in a 30-session run with real Claude sessions no memory got past 2 uses.)
CONFIRM_USES = 2                   # waking uses that confirm a dream-made idea as a real memory
BACKSTOP = 4                       # dormant and untouched for BACKSTOP x grace: archived even without exposures
SCREEN = 0.8                       # dormant memory with no partner above SCREEN x recall_min: fruitless, no judge call
SCREEN_BATCH = 200                 # dormant memories screened per association pass

STOP = set("the a an and or but of to in on for with at by from is are was were be been this that "
           "these those it its as we our you your they their he she i not no yes when what where which "
           "who why how does did do has have had will would can could should there here then than "
           "about into over under after before again also just only very each every".split())


def keywords(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    out = set()
    for w in words:
        if len(w) < 3 or w in STOP:
            continue
        for suf in ("ing", "ed", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        if w.endswith("e") and len(w) > 3:      # rotate / rotates / rotated -> rotat
            w = w[:-1]
        out.add(w)
    return out


def overlap(a, b):
    """Default similarity: keyword overlap, 0..1. Pass an embedder to MemoryStore to use embeddings instead."""
    a, b = set(a), set(b)
    return len(a & b) / math.sqrt(len(a) * len(b)) if a and b else 0.0


def word_commonness(text):
    """Offline stand-in for a language model's likelihood: mean Zipf frequency (wordfreq) of the
    content words. Higher = more ordinary. Use real log-probs when the poet can supply them."""
    from wordfreq import zipf_frequency
    words = [w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2]
    return sum(zipf_frequency(w, "en") for w in words) / len(words) if words else 8.0


class _Ranked(list):
    excluded = 0


def _ranked_off_mode(cands, scorer):
    """Candidates as str or {"text", "logprob" | "p"}. Likelihood comes from the model's
    log-prob if given, else its verbalized probability, else `scorer`. The likelier half is
    excluded (never the mode, never the mean); the rest are returned least likely first."""
    items = []
    for c in cands or []:
        if isinstance(c, str):
            items.append((c, None, None))
        elif c and c.get("text"):
            items.append((c["text"], c.get("logprob"), c.get("p")))
    if not items:
        return _Ranked()
    if all(lp is not None for _, lp, _ in items):
        like = [lp for _, lp, _ in items]
    elif all(p is not None for _, _, p in items):
        like = [p for _, _, p in items]
    else:
        like = [scorer(t) for t, _, _ in items]
    order = sorted(range(len(items)), key=lambda i: like[i])        # least likely first
    keep = order[: len(order) // 2]                                  # a lone candidate is the mode itself
    out = _Ranked(items[i][0] for i in keep)
    out.excluded = len(items) - len(keep)
    return out


class MemoryStore:
    """embedder: None for keyword overlap, or any object from embeddings.py.
    recall_min / revive override the embedder's thresholds (see calibrate.py)."""

    def __init__(self, root, embedder=None, summary_k=SUMMARY_K, recall_min=None, revive=None):
        self.root, self.k, self.emb = root, summary_k, embedder
        self.confirm_uses, self.lesson_uses = CONFIRM_USES, LESSON_USES   # a family may tune these
        self.sensitivities = []      # inherited marks: [(theme keywords, theme vector or None, weight)]
        th = getattr(embedder, "thresholds", {}) or {}
        self.recall_min = recall_min if recall_min is not None else th.get("recall_min", RECALL_MIN)
        self.revive = revive if revive is not None else th.get("revive", REVIVE)
        kind = embedder.name if embedder else "keywords"
        os.makedirs(os.path.join(root, "memories"), exist_ok=True)
        with self._lock():
            if not os.path.exists(self._index_path()):
                self._save({"beat": 0, "next": 1, "m": {}, "embedder": kind})
            elif self._load().get("embedder", "keywords") != kind:
                raise ValueError(f"this store was built with {self._load().get('embedder')}, not {kind}")

    # ----------------------------------------------------------------- files
    def _index_path(self):
        return os.path.join(self.root, "index.json")

    @contextmanager
    def _lock(self):
        with open(os.path.join(self.root, ".lock"), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _atomic(self, path, text):
        with open(path + ".tmp", "w") as f:
            f.write(text)
        os.replace(path + ".tmp", path)

    def _load(self):
        with open(self._index_path()) as f:
            return json.load(f)

    def _save(self, idx):
        self._atomic(self._index_path(), json.dumps(idx, separators=(",", ":")))

    def _vec_path(self):
        return os.path.join(self.root, "vectors.npy")

    def _vectors(self):
        p = self._vec_path()
        return np.load(p) if os.path.exists(p) else np.zeros((0, 0), np.float16)

    def _append_vector(self, v):
        V = self._vectors()
        V = v[None, :].astype(np.float16) if V.size == 0 else np.vstack([V, v.astype(np.float16)])
        with open(self._vec_path() + ".tmp", "wb") as f:
            np.save(f, V)
        os.replace(self._vec_path() + ".tmp", self._vec_path())
        return len(V) - 1

    @contextmanager
    def _txn(self):
        with self._lock():
            idx = self._load()
            yield idx
            self._settle(idx)
            self._save(idx)
            self._write_summary(idx)

    # ---------------------------------------------------------------- strength
    @staticmethod
    def strength(m, now):
        if m.get("lesson"):
            return 1.0                                  # lessons are hardened: they do not fade
        if m["dormant"]:
            return m["s"]
        g = GAMMA[m["c"]] ** (1.0 / (1.0 + m.get("slow", 0.0)))   # dream buffs slow the fade
        return m["floor"] + (m["s"] - m["floor"]) * g ** (now - m["t"])

    @staticmethod
    def tier(m):
        if m.get("lesson"):
            return "lesson"
        return "dormant" if m["dormant"] else TIER[m["c"]]

    def _settle(self, idx):
        """Anything that has faded below the line goes dormant (and stops fading)."""
        now = idx["beat"]
        for m in idx["m"].values():
            if not m["dormant"]:
                s = self.strength(m, now)
                if s < DORMANT:
                    m.update(s=s, t=now, dormant=True)

    def _invoke(self, m, now, weight, revived=False):
        s = REVIVED_AT if revived else self.strength(m, now)
        if now - m.get("last_spaced", -SPACING) >= SPACING:
            m["spaced"] += 1
            m["last_spaced"] = now
            for level, need in PROMOTE_AT.items():
                if m["spaced"] >= need:
                    m["c"] = max(m["c"], level)
        m["buffs"] += 1
        m["floor"] = min(FLOOR_CAP, m["floor"] + BUFF0 / m["buffs"])
        m.update(s=min(S_MAX, s + weight), t=now, dormant=False, uses=m["uses"] + 1, touch=now)
        if m.get("origin") in ("dream", "inherited") and m["uses"] >= self.confirm_uses:
            m["origin"], m["confirmed_at"] = "confirmed", now   # relied on while awake: now a real memory
        if revived:
            m["revivals"] += 1

    # -------------------------------------------------------------------- API
    def remember(self, text, importance=0.5, source="", parents=None):
        """Store a new short-term memory. Returns its id."""
        vec = self.emb.encode([text], "memory")[0] if self.emb else None     # outside the lock
        for kw, tvec, w in self.sensitivities:            # an inherited mark makes this feel more important
            sim = float(tvec @ vec) if (tvec is not None and vec is not None) else overlap(keywords(text), kw)
            if sim >= 0.8 * self.recall_min:
                importance = min(S_MAX, importance + 0.4 * w)
        with self._txn() as idx:
            mid = self._add(idx, text, importance, source, parents, vec)
            if source not in DREAM_SOURCES:
                self._check_predictions(idx, mid, vec)
            return mid

    def _add(self, idx, text, importance, source, parents, vec):
        mid = f"m{idx['next']:05d}"
        idx["next"] += 1
        idx["m"][mid] = {"s": min(S_MAX, max(0.0, importance)), "t": idx["beat"], "c": 0, "floor": 0.0,
                         "dormant": False, "uses": 0, "spaced": 0, "buffs": 0, "revivals": 0,
                         "born": idx["beat"], "kw": sorted(keywords(text)), "src": source,
                         "head": text[:120], "slow": 0.0, "touch": idx["beat"],
                         "parents": list(parents or []),
                         "origin": ("dream" if source in DREAM_SOURCES else
                                    "inherited" if source.startswith("family:") else "waking"),
                         "fruitless": 0, "last_sampled": None,
                         "lesson": False, "nights_long": 0, "dream_links": 0}
        if source not in DREAM_SOURCES and not source.startswith("family:"):
            idx["pressure"] = idx.get("pressure", 0) + 1
        if vec is not None:
            idx["m"][mid]["vi"] = self._append_vector(vec)
        self._atomic(os.path.join(self.root, "memories", f"{mid}.md"), text + "\n")
        return mid

    def use(self, mid, weight=0.3):
        """An agent relied on this memory: strengthen it and give it a permanent buff."""
        with self._txn() as idx:
            m = idx["m"][mid]
            self._invoke(m, idx["beat"], weight, revived=m["dormant"])
            return self._row(mid, m, idx["beat"])

    def recall(self, cue, cue_strength=0.5, k=5):
        """Search memory with a cue. Matching active memories are invoked (and buffed).
        Dormant memories wake only if similarity x cue_strength >= REVIVE."""
        ckw = keywords(cue)
        q = self.emb.encode([cue], "cue")[0] if self.emb else None          # outside the lock
        with self._txn() as idx:
            now = idx["beat"]
            V = self._vectors()
            sims = (V.astype(np.float32) @ q) if (q is not None and V.size) else None    # aliases count too
            if q is not None and sims is None:          # embedder store with no memories yet
                return []
            hits = []
            for mid, m in idx["m"].items():
                sim = (max([float(sims[m["vi"]])] + [float(sims[r]) for r in m.get("avi", [])])
                       if sims is not None else overlap(ckw, m["kw"]))
                if m["dormant"]:
                    if sim * cue_strength >= self.revive:
                        self._invoke(m, now, 0.0, revived=True)
                        hits.append((sim, mid, "revived"))
                elif sim >= self.recall_min:
                    hits.append((sim, mid, "recalled"))
            hits.sort(reverse=True)
            out = []
            for sim, mid, how in hits[:k]:
                m = idx["m"][mid]
                if how == "recalled":
                    self._invoke(m, now, 0.2 * cue_strength)
                out.append(dict(self._row(mid, m, now), how=how, similarity=round(sim, 2)))
            return out

    def advance_to(self, beat):
        """Keep this store's clock in step with an Ensemble's beat."""
        with self._txn() as idx:
            idx["beat"] = max(idx["beat"], beat)
            return idx["beat"]

    def beat(self, n=1):
        with self._txn() as idx:
            idx["beat"] += n
            return idx["beat"]

    def read(self, mid):
        with open(os.path.join(self.root, "memories", f"{mid}.md")) as f:
            return f.read().rstrip("\n")

    def _row(self, mid, m, now):
        r = {"id": mid, "tier": self.tier(m), "strength": round(self.strength(m, now), 3),
             "floor": round(m["floor"], 3), "uses": m["uses"], "revivals": m["revivals"], "head": m["head"]}
        if m.get("superseded_by"):
            r["superseded_by"] = m["superseded_by"]
        return r

    def rows(self):
        idx = self._load()
        return [self._row(mid, m, idx["beat"]) for mid, m in idx["m"].items()]

    def stats(self):
        idx = self._load()
        counts = {"short": 0, "intermediate": 0, "long": 0, "dormant": 0}
        for m in idx["m"].values():
            counts[self.tier(m)] += 1
        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(self.root) for f in fs
                   if not f.startswith("."))
        return {"beat": idx["beat"], **counts, "bytes": size}

    # ---------------------------------------------------------------- summary
    def _summary_text(self, idx):
        now = idx["beat"]
        active = [(self.strength(m, now), mid, m) for mid, m in idx["m"].items()
                  if not m["dormant"] and not m.get("lesson")]
        n_lessons = sum(1 for m in idx["m"].values() if m.get("lesson"))
        active.sort(reverse=True, key=lambda x: x[0])
        n_dormant = sum(m["dormant"] for m in idx["m"].values())
        lines = [f"beat {now} | {len(active)} active, {n_dormant} dormant, {n_lessons} lessons | strongest {min(self.k, len(active))}:"]
        for s, mid, m in active[: self.k]:
            tag = " (imagined)" if m.get("src") in IMAGINED and m.get("origin") != "confirmed" else ""
            lines.append(f"{mid} {TIER[m['c']][:5]} {s:.2f}{tag}: {m['head'][:80]}")
        return "\n".join(lines)

    def _write_summary(self, idx):
        self._atomic(os.path.join(self.root, "summary.md"), self._summary_text(idx) + "\n")
        ls = [(k, m) for k, m in idx["m"].items() if m.get("lesson")]
        self._atomic(os.path.join(self.root, "lessons.md"),
                     "# Lessons\n\n" + "".join(f"- {k}: {m['head']} (used {m['uses']} times)\n" for k, m in ls))

    def summary(self):
        with open(os.path.join(self.root, "summary.md")) as f:
            return f.read().rstrip("\n")

    # ==================================================================== sleep
    #
    # A night = several cycles. Each cycle has a consolidation phase (recent memories
    # against their nearest older ones: updates, contradictions, qualifications) and an
    # association phase (distant random pairs, dormant memories guaranteed a turn: new
    # links). Early cycles lean on consolidation, late ones on association, as in human
    # sleep. Daydreams happen while idle, around the current focus, and change nothing
    # destructively. Everything runs in three steps (sample under the lock, judge without
    # it, apply under it) so a slow LLM judge never blocks other agents.
    OPS = ("reinforce", "add", "qualify", "substitute", "subtract", "tension")

    def sleep_pressure(self):
        """New waking memories since the last sleep."""
        return self._load().get("pressure", 0)

    def sleep_due(self, threshold=SLEEP_PRESSURE):
        return self.sleep_pressure() >= threshold

    def sleep(self, judge, cycles=4, pairs_per_cycle=20, rng=None, min_score=0.5, plan=None):
        """A night. `plan` (the "plan" a previous sleep returned) replays exactly those pairs, pass
        by pass, instead of sampling: a judge that answered pairs in advance is asked about the
        same pairs even though applying its verdicts changes what fresh sampling would pick."""
        rng = rng or random.Random()
        since = self._load().get("last_sleep", -1)
        done, totals, log, insights, used_plan = set(), {}, [], [], []
        passes = iter(plan) if plan is not None else None
        for i in range(cycles):
            share = 0.8 - 0.6 * (i / max(1, cycles - 1))          # 80% consolidation -> 20%
            nc = round(pairs_per_cycle * share)
            ec = self._pass(judge, "consolidate", nc, rng, min_score, done, since=since,
                            pairs=next(passes, []) if passes else None)
            ea = self._pass(judge, "associate", pairs_per_cycle - nc, rng, min_score, done,
                            pairs=next(passes, []) if passes else None)
            used_plan += [ec["sampled"], ea["sampled"]]
            log.append({"consolidate": nc, "associate": pairs_per_cycle - nc,
                        "found": (ec["connections"], ea["connections"])})
            for ev in (ec, ea):
                insights += ev["insights"]
                for k, v in ev["counts"].items():
                    totals[k] = totals.get(k, 0) + v
                for k in ("downgraded", "pairs"):
                    totals[k] = totals.get(k, 0) + ev[k]
        with self._txn() as idx:
            archived = self._vacate(idx)
            hardened, softened = self._harden(idx)
            idx["pressure"], idx["last_sleep"] = 0, idx["beat"]
            idx["nights"] = idx.get("nights", 0) + 1
            idx["proposals"] = []
            now = idx["beat"]
        found = ", ".join(f"{totals[k]} {k}" for k in self.OPS if totals.get(k))
        report = (f"slept at beat {now}: {cycles} cycles, {totals.get('pairs', 0)} pairs; {found or 'nothing found'}; "
                  f"{len(insights)} new insights; {len(archived)} archived"
                  + (f"; {len(hardened)} became lessons" if hardened else "")
                  + (f"; {len(softened)} lessons demoted (cap)" if softened else ""))
        self._atomic(os.path.join(self.root, "dreams.md"), report + "\n")
        return {"report": report, "counts": totals, "cycles": log, "insights": insights, "archived": archived,
                "lessons": hardened, "demoted": softened, "plan": used_plan}

    # ------------------------------------------------------------- lessons
    def _harden(self, idx):
        """End of each night: consolidated memories (intermediate or long) that earned it become lessons."""
        now, protected = idx["beat"], self._protected(idx)
        new = []
        for mid, m in idx["m"].items():
            if m.get("lesson") or m["dormant"] or m["c"] < 1:     # intermediate (2 spaced uses) or long
                continue
            m["nights_long"] = m.get("nights_long", 0) + 1
            if (m.get("origin", "waking") in ("waking", "confirmed") and m["uses"] >= self.lesson_uses
                    and m["nights_long"] >= LESSON_NIGHTS and m.get("dream_links", 0) >= 1
                    and not m.get("superseded_by") and not m.get("merged_into") and mid not in protected):
                m.update(lesson=True, lesson_at=now, s=1.0, t=now)
                new.append(mid)
        lessons = sorted((k for k, m in idx["m"].items() if m.get("lesson")),
                         key=lambda k: (idx["m"][k]["uses"], idx["m"][k].get("lesson_at", 0)))
        demoted = lessons[: max(0, len(lessons) - LESSON_CAP)]
        for mid in demoted:
            self._demote(idx["m"][mid], now)
        return new, demoted

    def _demote(self, m, now):
        m.update(lesson=False, c=2, s=0.9, t=now, nights_long=0)

    def lessons(self):
        idx = self._load()
        return [{"id": k, "text": self.read(k), "uses": m["uses"]} for k, m in idx["m"].items() if m.get("lesson")]

    def lessons_for(self, context, k=2):
        """Lessons relevant to a situation, offered before anyone asks."""
        ls = self.lessons()
        if not ls or not context.strip():
            return []
        if self.emb:
            q = self.emb.encode([context], "cue")[0]
            V = self._vectors().astype(np.float32)
            idx = self._load()
            scored = [(float(V[idx["m"][l["id"]]["vi"]] @ q), l) for l in ls]
        else:
            ckw = keywords(context)
            scored = [(overlap(ckw, keywords(l["text"])), l) for l in ls]
        scored.sort(key=lambda x: -x[0])
        return [dict(l, relevance=round(s, 2)) for s, l in scored[:k] if s >= self.recall_min]

    def daydream(self, judge, focus, samples=6, rng=None, min_score=0.5):
        """Idle mind-wandering: memories closest to `focus` paired with older or dormant ones.
        Links, reinforcements, qualifications and tensions apply at once; replacements and
        contradictions are only proposed, for the next sleep to re-judge."""
        return self._pass(judge, "daydream", samples, rng or random.Random(), min_score, set(), focus=focus)

    # ------------------------------------------------------------ one pass
    def _pass(self, judge, mode, n, rng, min_score, done, since=-1, focus=None, pairs=None):
        """One sample-judge-apply pass. Given `pairs`, judge those (minus any whose memories are
        gone or already judged tonight) instead of sampling."""
        ev = {"counts": {}, "connections": 0, "insights": [], "proposed": 0, "downgraded": 0, "pairs": 0,
              "sampled": []}
        if n <= 0 and not pairs:
            return ev
        fvec = self.emb.encode([focus], "cue")[0] if (focus and self.emb) else None
        # 1. sample
        with self._lock():
            idx = self._load()
            if len(idx["m"]) < 2:
                return ev
            V = self._vectors().astype(np.float32) if self.emb else None
            sim = self._sim_fn(idx, V)
            pick = {"consolidate": self._pairs_consolidate, "associate": self._pairs_associate,
                    "daydream": self._pairs_daydream}[mode]
            if pairs is None:
                pairs = pick(idx, sim, n, rng, done, since=since, fvec=fvec, fkw=keywords(focus or ""), V=V)
            else:
                fixed = []
                for a, b in pairs:
                    if a not in idx["m"] or b not in idx["m"]:
                        continue
                    ok, p = self._ok(idx, done, a, b)
                    if ok and p not in fixed:
                        fixed.append(p)
                pairs = fixed
            done.update(pairs)
            ev["sampled"] = [list(p) for p in pairs]
            snap = {}
            for mid in {x for p in pairs for x in p}:
                m = idx["m"][mid]
                snap[mid] = {"id": mid, "text": self.read(mid), "born": m["born"], "src": m["src"],
                             "tier": self.tier(m), "origin": m.get("origin", "waking"), "uses": m["uses"]}
            sims = {p: sim(*p) for p in pairs}
        ev["pairs"] = len(pairs)
        # 2. judge (no lock)
        verdicts = []
        for p in pairs:
            v = judge(snap[p[0]], snap[p[1]], sims[p])
            ok = bool(v) and v.get("op") in self.OPS and float(v.get("score", 0)) >= min_score
            verdicts.append((p, dict(v) if ok else None))
        texts = [v["insight"] for _, v in verdicts if v and v.get("insight")]
        vecs = iter(self.emb.encode(texts, "memory")) if (self.emb and texts) else iter(())
        for _, v in verdicts:
            if v and v.get("insight"):
                v["vec"] = next(vecs, None)
        # 3. apply
        with self._txn() as idx:
            now = idx["beat"]
            for (ai, bi), v in verdicts:
                a, b = idx["m"].get(ai), idx["m"].get(bi)
                if a is None or b is None or a.get("merged_into") or b.get("merged_into"):
                    continue
                a["last_sampled"] = b["last_sampled"] = now
                if v is None:
                    a["fruitless"] = a.get("fruitless", 0) + 1
                    b["fruitless"] = b.get("fruitless", 0) + 1
                    continue
                op = self._gate(idx, mode, v, ai, bi, ev)
                if op is None:
                    continue
                a["fruitless"] = b["fruitless"] = 0
                self._apply(idx, now, op, v, ai, bi, ev)
                ev["counts"][op] = ev["counts"].get(op, 0) + 1
                ev["connections"] += 1
        return ev

    def _sim_fn(self, idx, V):
        if V is not None and V.size:
            return lambda a, b: float(V[idx["m"][a]["vi"]] @ V[idx["m"][b]["vi"]])
        return lambda a, b: overlap(idx["m"][a]["kw"], idx["m"][b]["kw"])

    @staticmethod
    def _kin(idx, a, b):
        """An insight paired with its own source teaches nothing."""
        return a in idx["m"][b].get("parents", []) or b in idx["m"][a].get("parents", [])

    def _ok(self, idx, done, a, b):
        p = tuple(sorted((a, b)))
        return a != b and p not in done and not self._kin(idx, a, b), p

    def _pairs_consolidate(self, idx, sim, n, rng, done, since=-1, **_):
        pairs = []
        open_t = [[t["a"], t["b"]] for t in idx.get("tensions", {}).values() if t["status"] == "open"]
        for a, b in idx.get("proposals", []) + open_t:        # daydream proposals and open tensions first
            if a in idx["m"] and b in idx["m"]:
                ok, p = self._ok(idx, done, a, b)
                if ok and p not in pairs:
                    pairs.append(p)
        recent = sorted((mid for mid, m in idx["m"].items()
                         if m.get("origin", "waking") == "waking" and m["born"] > since),
                        key=lambda k: -idx["m"][k]["born"])
        for r in recent:
            if len(pairs) >= n:
                break
            near = sorted(((sim(r, o), o) for o in idx["m"] if o != r), reverse=True)
            added = 0
            for s, o in near:
                ok, p = self._ok(idx, done, r, o)
                if s > 0 and ok and p not in pairs:
                    pairs.append(p); added += 1
                if added == 2:
                    break
        return pairs[:n]

    def _pairs_associate(self, idx, sim, n, rng, done, **_):
        """Dormant memories, longest-unreplayed first, each get a turn. A cheap similarity screen
        runs first: a dormant memory with no partner above SCREEN x recall_min is counted as a
        fruitless exposure without spending a judge call (an LLM call, in production)."""
        mids = list(idx["m"])
        pairs = []
        dormant = sorted((k for k in mids if idx["m"][k]["dormant"]),
                         key=lambda k: (idx["m"][k].get("last_sampled") is not None,
                                        idx["m"][k].get("last_sampled") or 0))
        quota = max(1, n // 3) if dormant else 0                # dormant memories get guaranteed turns
        floor = SCREEN * self.recall_min
        screened = 0
        for d in dormant[:SCREEN_BATCH]:
            best = max(((sim(d, o), o) for o in mids if o != d and self._ok(idx, done, d, o)[0]), default=(0.0, None))
            if best[0] < floor:
                m = idx["m"][d]
                m["fruitless"] = m.get("fruitless", 0) + 1
                m["last_sampled"] = idx["beat"]
                screened += 1
            elif len(pairs) < quota:
                pairs.append(self._ok(idx, done, d, best[1])[1])
        if screened:
            self._save(idx)                                     # we hold the lock during sampling
        tiers = {}
        for k in mids:
            tiers.setdefault(self.tier(idx["m"][k]), []).append(k)
        groups = list(tiers.values())
        for _ in range(n * 5):
            if len(pairs) >= n:
                break
            ok, p = self._ok(idx, done, rng.choice(rng.choice(groups)), rng.choice(rng.choice(groups)))
            if ok and p not in pairs:
                pairs.append(p)
        return pairs

    def _pairs_daydream(self, idx, sim, n, rng, done, fvec=None, fkw=None, V=None, **_):
        active = [k for k, m in idx["m"].items() if not m["dormant"]]
        if not active:
            return []
        if fvec is not None and V is not None and V.size:
            score = lambda k: float(V[idx["m"][k]["vi"]] @ fvec)
        else:
            score = lambda k: overlap(fkw, idx["m"][k]["kw"])
        focus = sorted(active, key=score, reverse=True)[:3]
        older = [k for k, m in idx["m"].items() if m["dormant"] or m["c"] == 2] or list(idx["m"])
        pairs = []
        for _ in range(n * 5):
            if len(pairs) >= n:
                break
            ok, p = self._ok(idx, done, rng.choice(focus), rng.choice(older))
            if ok and p not in pairs:
                pairs.append(p)
        return pairs

    # -------------------------------------------------------- rules and effects
    def _gate(self, idx, mode, v, ai, bi, ev):
        """Destructive outcomes need waking evidence. Daydreams only propose them; a dream-made
        memory may only overrule another once agents have relied on it (2+ uses)."""
        op = v["op"]
        if {idx["m"][ai].get("src"), idx["m"][bi].get("src")} & set(IMAGINED) and op not in ("reinforce", "add"):
            return None                                       # poems and excursions never settle facts
        if op not in ("substitute", "subtract"):
            return op
        if mode == "daydream":
            idx.setdefault("proposals", []).append([ai, bi])
            ev["proposed"] += 1
            return None
        keep = idx["m"].get(v.get("keep"))
        if keep is None or v.get("drop") not in (ai, bi):
            return None
        if idx["m"][v["drop"]].get("lesson") or (keep.get("origin") in ("dream", "inherited")
                                                and keep["uses"] < self.confirm_uses):
            ev["downgraded"] += 1
            drop = idx["m"][v["drop"]]
            v["insight"] = v.get("insight") or f'Unresolved: "{keep["head"]}" vs "{drop["head"]}"'
            v["vec"] = None
            v["a"], v["b"] = v["keep"], v["drop"]
            return "tension"
        return op

    def _apply(self, idx, now, op, v, ai, bi, ev):
        a, b = idx["m"][ai], idx["m"][bi]
        sc = float(v["score"])
        if op == "reinforce":
            if a["dormant"] or b["dormant"]:          # a dormant duplicate adds nothing: merge it into its partner
                gone, keep = (ai, bi) if (a["dormant"] and (not b["dormant"] or a["uses"] <= b["uses"])) else (bi, ai)
                g, k = idx["m"][gone], idx["m"][keep]
                if not g.get("lesson") and gone not in self._protected(idx):
                    k["uses"] += g["uses"]; k["revivals"] += g["revivals"]
                    g["merged_into"] = keep
                    self._dream_buff(k, now, sc, 0.1 * sc)
                    idx.setdefault("pending_merge", []).append(gone)
                    ev["counts"]["merged"] = ev["counts"].get("merged", 0) + 1
                    return
            self._dream_buff(a, now, sc, 0.1 * sc); self._dream_buff(b, now, sc, 0.1 * sc)
        elif op in ("add", "qualify"):
            self._dream_buff(a, now, sc); self._dream_buff(b, now, sc)
        elif op in ("substitute", "subtract"):
            self._weaken(idx["m"][v["drop"]], now, by=v["keep"])
            self._dream_buff(idx["m"][v["keep"]], now, sc)
            idx["overturned"] = idx.get("overturned", 0) + 1
            for t in idx.get("tensions", {}).values():           # waking evidence settled a tension
                if t["status"] == "open" and {t["a"], t["b"]} == {ai, bi}:
                    t["status"] = f"resolved:evidence:{v['keep']}"
        elif op == "tension":
            for m in (a, b):
                self._reanchor(m, now); m["touch"] = now
        if v.get("insight"):
            source = {"qualify": "qualify", "tension": "tension"}.get(op, "dream")
            key = f"{min(ai, bi)}|{max(ai, bi)}|{op}"
            seen = idx.setdefault("dream_pairs", {})
            if seen.get(key) in idx["m"]:
                self._dream_buff(idx["m"][seen[key]], now, sc, 0.1 * sc)
                return
            imp = 0.6 if op == "tension" else 0.3 + 0.4 * sc
            new = self._add(idx, v["insight"], imp, source, [ai, bi], v.get("vec") if v.get("vec") is not None
                            else (self.emb.encode([v["insight"]], "memory")[0] if self.emb else None))
            seen[key] = new
            ev["insights"].append(new)
            if op == "qualify":
                a["qualified_by"] = b["qualified_by"] = new
            if op == "tension":
                first, second = (v.get("a", ai), v.get("b", bi))
                idx.setdefault("tensions", {})[new] = {"a": first, "b": second, "status": "open", "raised": False}

    def _reanchor(self, m, now):
        if not m["dormant"]:
            m["s"], m["t"] = self.strength(m, now), now

    def _dream_buff(self, m, now, score, boost=0.0):
        self._reanchor(m, now)
        m["slow"] = min(SLOW_CAP, m.get("slow", 0.0) + 0.5 * score)
        m["touch"] = now
        m["dream_links"] = m.get("dream_links", 0) + 1
        if not m["dormant"] and boost:
            m["s"] = min(S_MAX, m["s"] + boost)

    def _weaken(self, m, now, by=None):
        self._reanchor(m, now)
        m["s"] = max(m["floor"] if not m["dormant"] else 0.0, m["s"] * 0.3)
        m["superseded_by"] = by
        m["touch"] = now

    # ------------------------------------------------------------- tensions
    def open_tensions(self):
        idx = self._load()
        out = []
        for tid, t in idx.get("tensions", {}).items():
            if t["status"] == "open" and tid in idx["m"]:
                out.append({"id": tid, "text": self.read(tid), "raised": t["raised"],
                            "a": t["a"], "b": t["b"],
                            "a_text": self.read(t["a"]) if t["a"] in idx["m"] else None,
                            "b_text": self.read(t["b"]) if t["b"] in idx["m"] else None})
        return out

    def mark_raised(self, tid):
        with self._txn() as idx:
            idx["tensions"][tid]["raised"] = True

    def resolve_tension(self, tid, winner):
        """winner: 'a' or 'b' (the other is superseded) or 'both' (both stand, linked to the tension)."""
        with self._txn() as idx:
            t = idx["tensions"][tid]
            now = idx["beat"]
            a, b = idx["m"].get(t["a"]), idx["m"].get(t["b"])
            if winner in ("a", "b") and a and b:
                win, lose, wid = (a, b, t["a"]) if winner == "a" else (b, a, t["b"])
                if lose.get("lesson"):
                    self._demote(lose, now)
                self._weaken(lose, now, by=wid); self._dream_buff(win, now, 1.0)
            else:
                for m in (a, b):
                    if m:
                        self._dream_buff(m, now, 1.0); m["qualified_by"] = tid
            t["status"] = f"resolved:{winner}"
            return t["status"]

    # ---------------------------------------------------- vacating and archive
    def _protected(self, idx):
        keep = set()
        for tid, t in idx.get("tensions", {}).items():
            if t["status"] == "open":
                keep |= {tid, t["a"], t["b"]}
        return keep

    def vacate(self):
        with self._txn() as idx:
            return self._vacate(idx)

    def _vacate(self, idx):
        """Archive dormant memories that had FRUITLESS_K dream exposures with nothing coming of
        it, and sat untouched for MIN_AGE x (1 + uses + 2 x revivals) beats."""
        now, protected = idx["beat"], self._protected(idx)
        gone = list(dict.fromkeys(g for g in idx.pop("pending_merge", []) if g in idx["m"]))
        for mid, m in idx["m"].items():
            if not m["dormant"] or mid in protected or mid in gone or m.get("lesson"):
                continue
            grace = MIN_AGE * (1 + m["uses"] + 2 * m["revivals"])
            if m.get("origin") == "dream":                      # an unconfirmed dream idea is a hypothesis
                grace //= 2
            idle = now - max(m.get("touch", m["t"]), m["t"])
            if (m.get("fruitless", 0) >= FRUITLESS_K and idle >= grace) or idle >= BACKSTOP * grace:
                gone.append(mid)
        if not gone:
            return []
        with gzip.open(os.path.join(self.root, "archive.jsonl.gz"), "at") as f:
            for mid in gone:
                m = idx["m"][mid]
                f.write(json.dumps({"id": mid, "text": self.read(mid), "archived": now,
                                    **{k: m.get(k) for k in ("born", "src", "origin", "uses", "revivals", "fruitless",
                                                             "parents", "superseded_by", "merged_into", "kw")}}) + "\n")
        for mid in gone:
            del idx["m"][mid]
            p = os.path.join(self.root, "memories", f"{mid}.md")
            if os.path.exists(p):
                os.remove(p)
        if self.emb:
            V = self._vectors()
            rows, new = [], {}
            for k in sorted(idx["m"], key=lambda k: idx["m"][k]["vi"]):
                m = idx["m"][k]
                new[k] = (len(rows), list(range(len(rows) + 1, len(rows) + 1 + len(m.get("avi", [])))))
                rows += [m["vi"]] + m.get("avi", [])
            V = V[rows] if rows else V[:0]
            for k, (vi, avi) in new.items():
                idx["m"][k]["vi"] = vi
                if avi:
                    idx["m"][k]["avi"] = avi
            with open(self._vec_path() + ".tmp", "wb") as f:
                np.save(f, V)
            os.replace(self._vec_path() + ".tmp", self._vec_path())
        g = set(gone)
        idx["dream_pairs"] = {k: v for k, v in idx.get("dream_pairs", {}).items()
                              if v not in g and not (set(k.split("|")[:2]) & g)}
        return gone

    def search_archive(self, cue, k=5):
        """Keyword search of archived memories (cold storage: no vectors, no fading)."""
        p = os.path.join(self.root, "archive.jsonl.gz")
        if not os.path.exists(p):
            return []
        ckw = keywords(cue)
        with gzip.open(p, "rt") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        scored = sorted(((overlap(ckw, r["kw"]), r) for r in rows), key=lambda x: -x[0])
        return [{"id": r["id"], "score": round(s, 2), "text": r["text"]} for s, r in scored[:k] if s > 0]

    def restore(self, archived_id):
        """Bring an archived memory back as a new short-term memory. Returns the new id."""
        with gzip.open(os.path.join(self.root, "archive.jsonl.gz"), "rt") as f:
            row = next((json.loads(l) for l in f if f'"id": "{archived_id}"' in l), None)
        if row is None:
            raise KeyError(archived_id)
        return self.remember(row["text"], 0.6, source=f"restored:{archived_id}")

    # ============================================================ poem-making
    #
    # Not sense-making. Distant memories (different topics, different sources, lessons
    # included, optional domain text) are handed to a poet that proposes MANY candidates
    # for each figure and alias, each with a likelihood: the model's own token log-probs,
    # its verbalized probability, or (offline) word frequency. The engine refuses the
    # likely: the more probable half of every candidate set is excluded outright, and the
    # least probable survivor that still passes the precision gate is kept. Language
    # moves away from the model's mode, never toward it, without losing its referent.
    #   figure   a structural analogy, stored as a memory (a hypothesis until agents use it)
    #   alias    an expressive handle, kept only if it points unambiguously back to its memory
    #   gloss    a precise restatement (precision, not surprise: gated the same way)
    #   probe    a question testing where a memory or lesson stops holding
    #   verse    a few lines, kept in poems.md (the last 12)
    def compose(self, poet, pairs=4, rng=None, domain=None, scorer=None, plan=None):
        """Poem-making. `plan` (the "plan" a previous compose returned) uses exactly those pairs."""
        rng = rng or random.Random()
        scorer = scorer or word_commonness
        domain = list(domain or [])
        report = {"pairs": 0, "figures": [], "aliases": [], "rejected_aliases": [], "glosses": 0,
                  "probes": [], "verses": 0, "excluded_as_likely": 0, "plan": []}
        # 1. choose distant pairs (under the lock)
        with self._lock():
            idx = self._load()
            ms = idx["m"]
            pool = [k for k, m in ms.items() if m.get("src") not in IMAGINED]   # memories, lessons, dormant
            if len(pool) + len(domain) < 2:
                return dict(report, report="nothing to compose from")
            V = self._vectors().astype(np.float32) if self.emb else None
            sim = self._sim_fn(idx, V)
            cands = []
            for _ in range(pairs * 15 if plan is None else 0):
                a = rng.choice(pool)
                if domain and rng.random() < 0.3:
                    cands.append((0.0, a, f"domain:{rng.randrange(len(domain))}"))
                    continue
                b = rng.choice(pool)
                if a != b and not self._kin(idx, a, b):
                    cands.append((sim(a, b), a, b))
            cands.sort(key=lambda x: x[0])                     # most disparate first
            chosen, used = [], set()
            for s, a, b in cands:
                if len(chosen) < pairs and a not in used and b not in used:
                    chosen.append((s, a, b)); used |= {a, b}
            if plan is not None:
                live = lambda k: (k in ms) if not k.startswith("domain:") else int(k.split(":")[1]) < len(domain)
                chosen = [(s, a, b) for s, a, b in plan if live(a) and live(b)]
            report["plan"] = [[s, a, b] for s, a, b in chosen]
            snap = {}
            for _, a, b in chosen:
                for k in (a, b):
                    if k.startswith("domain:"):
                        snap[k] = {"id": k, "text": domain[int(k.split(":")[1])], "tier": "domain",
                                   "src": "domain", "aliases": [], "lesson": False}
                    else:
                        snap[k] = {"id": k, "text": self.read(k), "tier": self.tier(ms[k]), "src": ms[k]["src"],
                                   "aliases": ms[k].get("aliases", []), "lesson": bool(ms[k].get("lesson"))}
        report["pairs"] = len(chosen)
        # 2. compose (no lock: the poet may be an LLM); embed every candidate up front
        works = []
        for s, a, b in chosen:
            w = poet(snap[a], snap[b], s)
            if not w:
                continue
            w["figures"] = _ranked_off_mode(w.get("figures"), scorer)
            w["aliases"] = {side: _ranked_off_mode(c, scorer) for side, c in (w.get("aliases") or {}).items()}
            report["excluded_as_likely"] += w["figures"].excluded + sum(c.excluded for c in w["aliases"].values())
            texts = list(w["figures"]) + [t for c in w["aliases"].values() for t in c] + \
                [t for t in (w.get("glosses") or {}).values() if t] + [t for t in (w.get("probes") or {}).values() if t]
            vecs = self.emb.encode(texts, "memory") if (self.emb and texts) else [None] * len(texts)
            w["_vec"] = dict(zip(texts, vecs))
            works.append((a, b, w))
        # 3. apply (under the lock)
        with self._txn() as idx:
            now = idx["beat"]
            for a, b, w in works:
                ids = {"A": a, "B": b}
                real = [k for k in (a, b) if k in idx["m"]]
                kept_any = False
                if w["figures"]:
                    fig = w["figures"][0]                      # least likely of the unlikely half
                    report["figures"].append(self._add(idx, fig, 0.4, "poem", real, w["_vec"].get(fig)))
                    kept_any = True
                for side, ranked in w["aliases"].items():
                    target = ids.get(side)
                    if target not in idx["m"]:
                        continue
                    pick = next((t for t in ranked if self._precise(idx, target, t, w["_vec"].get(t))), None)
                    if pick:
                        self._attach_alias(idx, target, pick, w["_vec"].get(pick))
                        report["aliases"].append((target, pick)); kept_any = True
                    elif ranked:
                        report["rejected_aliases"].append((target, list(ranked)[:3]))
                for side, gloss in (w.get("glosses") or {}).items():
                    target = ids.get(side)
                    if target in idx["m"] and gloss and self._precise(idx, target, gloss, w["_vec"].get(gloss)):
                        idx["m"][target]["gloss"] = gloss
                        report["glosses"] += 1
                for side, probe in (w.get("probes") or {}).items():
                    target = ids.get(side)
                    if target in idx["m"] and probe:
                        report["probes"].append(self._add(idx, probe, 0.5, "probe", [target], w["_vec"].get(probe)))
                if w.get("verse"):
                    idx.setdefault("poems", []).append({"beat": now, "verse": w["verse"],
                                                        "from": [snap[a]["text"][:60], snap[b]["text"][:60]]})
                    idx["poems"] = idx["poems"][-12:]
                    report["verses"] += 1
                if kept_any:
                    for k in real:
                        self._dream_buff(idx["m"][k], now, float(w.get("score", 0.6)))
            poems = idx.get("poems", [])
        self._atomic(os.path.join(self.root, "poems.md"), "# Poems\n\n" + "\n".join(
            f"*beat {p['beat']}, from \"{p['from'][0]}\" and \"{p['from'][1]}\"*\n\n{p['verse']}\n" for p in poems))
        report["report"] = (f"composed from {report['pairs']} disparate pairs: {len(report['figures'])} figures, "
                            f"{len(report['aliases'])} aliases kept ({len(report['rejected_aliases'])} memories had no "
                            f"candidate precise enough), {report['excluded_as_likely']} candidates refused as too likely, "
                            f"{report['glosses']} glosses, {len(report['probes'])} probes, {report['verses']} verses")
        return report

    def _precise(self, idx, target, phrase, vec):
        """A new name must point back to its own memory: nearest of all, by a margin.
        With keywords, a phrase that overlaps nothing at all is new vocabulary and unambiguous."""
        if vec is not None:
            V = self._vectors().astype(np.float32)
            sims = {k: max([float(V[m["vi"]] @ vec)] + [float(V[r] @ vec) for r in m.get("avi", [])])
                    for k, m in idx["m"].items() if "vi" in m and (k == target or m.get("src") not in IMAGINED)}
            best = sorted(sims.items(), key=lambda kv: -kv[1])
            if not best or best[0][0] != target:
                return False
            return len(best) == 1 or best[0][1] - best[1][1] >= PRECISION_MARGIN
        kw = keywords(phrase)
        scores = {k: overlap(kw, m["kw"]) for k, m in idx["m"].items()
                  if k == target or m.get("src") not in IMAGINED}             # poems are not referents
        top = max(scores.values(), default=0)
        if top == 0:
            return True
        return scores.get(target, 0) == top and sum(v == top for v in scores.values()) == 1

    def _attach_alias(self, idx, target, alias, vec):
        m = idx["m"][target]
        m.setdefault("aliases", []).append(alias)
        m["kw"] = sorted(set(m["kw"]) | keywords(alias))
        if vec is not None:
            m.setdefault("avi", []).append(self._append_vector(vec))

    def describe(self, mid):
        """The memory with its renewed language: aliases (expressive) and gloss (precise)."""
        m = self._load()["m"][mid]
        out = self.read(mid)
        if m.get("src") in IMAGINED and m.get("origin") != "confirmed":
            out = "(imagined, unconfirmed) " + out
        if m.get("aliases"):
            out += f"  [aka: {'; '.join(m['aliases'])}]"
        if m.get("gloss"):
            out += f"  [precisely: {m['gloss']}]"
        return out

    def poems(self):
        return self._load().get("poems", [])

    # ============================================================== excursions
    #
    # Curiosity that acts. A seed (an unexplored poem figure, probe, dream link, or two
    # memories with nothing in common) is handed to an explorer that carries it out anyway:
    # a build-out, an experiment, a thought exercise or a hypothesis. Silly, trivial and
    # nonsensical results are kept too: the field note is the point. Everything is marked
    # imagined and can never settle a fact. A hypothesis carries a prediction; if a later
    # waking memory matches it, the hypothesis is confirmed and can grow into a lesson.
    # Experiments only execute code through a runner you supply (your own sandbox).
    def wander(self, explorer, n=1, rng=None, runner=None, max_spawn=2, plan=None):
        """Excursions. `plan` (the "plan" a previous wander returned) explores exactly those seeds."""
        rng = rng or random.Random()
        report = {"excursions": [], "spawned": [], "predictions": [], "verdicts": {}, "plan": []}
        # 1. choose seeds (under the lock)
        with self._lock():
            idx = self._load()
            ms = idx["m"]
            explored = set(idx.get("explored", []))
            seeds = [k for k, m in ms.items() if m.get("src") in ("poem", "probe", "dream") and k not in explored]
            rng.shuffle(seeds)
            plain = [k for k, m in ms.items() if m.get("src") not in IMAGINED]
            picks = []
            for _ in range(n):
                if seeds and rng.random() < 0.75:
                    k = seeds.pop()
                    picks.append({"seed": self.read(k), "from": [k]})
                elif len(plain) >= 2:                          # two unrelated things: what if?
                    a, b = rng.sample(plain, 2)
                    picks.append({"seed": f"What if \"{self.read(a)}\" met \"{self.read(b)}\"?", "from": [a, b]})
            if plan is not None:
                picks = [{"seed": p["seed"], "from": list(p["from"])} for p in plan
                         if all(k in ms for k in p["from"])]
            for p in picks:
                p["context"] = [self.read(k) for k in p["from"]]
            report["plan"] = [{"seed": p["seed"], "from": p["from"]} for p in picks]
        # 2. explore (no lock: the explorer may be an LLM; the runner may take a while)
        notes = []
        for p in picks:
            r = explorer(p["seed"], p["context"])
            if not r:
                continue
            if r.get("form") == "experiment" and r.get("code") and runner is not None:
                try:
                    r["ran"] = str(runner(r["code"]))[:500]
                except Exception as err:                       # a failed experiment is still a result
                    r["ran"] = f"error: {err}"[:500]
            texts = [self._field_note(r)] + [s for s in (r.get("spawn") or [])[:max_spawn]] + \
                    ([r["prediction"]] if r.get("prediction") else [])
            vecs = self.emb.encode(texts, "memory") if self.emb else [None] * len(texts)
            notes.append((p, r, dict(zip(texts, vecs))))
        # 3. keep everything (under the lock)
        with self._txn() as idx:
            for p, r, vec in notes:
                parents = [k for k in p["from"] if k in idx["m"]]
                note = self._field_note(r)
                mid = self._add(idx, note, 0.35, "excursion", parents, vec[note])
                idx["m"][mid]["verdict"] = r.get("verdict", "unknown")
                report["excursions"].append(mid)
                idx["excursions_total"] = idx.get("excursions_total", 0) + 1
                v = r.get("verdict", "unknown")
                report["verdicts"][v] = report["verdicts"].get(v, 0) + 1
                for s in (r.get("spawn") or [])[:max_spawn]:
                    report["spawned"].append(self._add(idx, s, 0.3, "dream", [mid], vec[s]))
                if r.get("prediction"):
                    pid = self._add(idx, r["prediction"], 0.4, "prediction", [mid], vec[r["prediction"]])
                    report["predictions"].append(pid)
                idx.setdefault("explored", []).extend(p["from"])
                idx.setdefault("journal", []).append({"beat": idx["beat"], "note": note})
                idx["journal"] = idx["journal"][-20:]
                for k in parents:
                    self._dream_buff(idx["m"][k], idx["beat"], 0.4)
            journal = idx.get("journal", [])
        self._atomic(os.path.join(self.root, "excursions.md"), "# Excursions\n\n" + "\n".join(
            f"- beat {j['beat']}: {j['note']}" for j in journal) + "\n")
        verdicts = ", ".join(f"{c} {v}" for v, c in report["verdicts"].items()) or "none"
        report["report"] = (f"wandered: {len(report['excursions'])} excursions ({verdicts}), "
                            f"{len(report['spawned'])} new ideas, {len(report['predictions'])} predictions")
        return report

    @staticmethod
    def _field_note(r):
        note = f"[imagined {r.get('form', 'excursion')}] {r.get('title', '')}: {r.get('outcome', '')}"
        if r.get("ran"):
            note += f" (ran it: {r['ran'][:120]})"
        if r.get("surprise"):
            note += f" Surprise: {r['surprise']}"
        return note + f" Verdict: {r.get('verdict', 'unknown')}."

    def _check_predictions(self, idx, new_id, vec):
        """A waking memory that matches an open prediction makes the imagined hypothesis real."""
        hits = []
        new = idx["m"][new_id]
        V = self._vectors().astype(np.float32) if (self.emb and vec is not None) else None
        for pid, m in idx["m"].items():
            if m.get("src") != "prediction" or m.get("came_true"):
                continue
            s = float(V[m["vi"]] @ vec) if V is not None else overlap(new["kw"], m["kw"])
            if s >= min(0.95, self.recall_min + 0.15):
                m["came_true"] = new_id
                for k in [pid] + m.get("parents", []):
                    if k in idx["m"]:
                        h = idx["m"][k]
                        h["origin"], h["confirmed_by"] = "confirmed", new_id
                        self._invoke(h, idx["beat"], 0.3)
                hits.append(pid)
        if hits:
            idx.setdefault("came_true", []).extend(hits)
        return hits

    def journal(self):
        return self._load().get("journal", [])

    # ------------------------------------------------------------ agent tools
    def tools(self):
        """Functions an LLM agent can call (ADK-compatible: type hints + docstrings)."""
        store = self

        def memory_summary() -> str:
            """Read your strongest active memories. Call at the start of each turn."""
            return store.summary()

        def remember(text: str, importance: float) -> str:
            """Store something worth remembering. importance is 0 to 1."""
            return f"stored {store.remember(text, importance)}"

        def recall(cue: str, strength: float) -> str:
            """Search memory. strength 0 to 1 is how strongly the situation calls for it;
            only a strong, closely matching cue wakes dormant memories."""
            hits = store.recall(cue, strength)
            if not hits:
                return "nothing matched"
            return "\n".join(f"{h['id']} [{h['how']}, {h['tier']}] {store.read(h['id'])}" for h in hits)

        def use_memory(memory_id: str) -> str:
            """Mark that you relied on a memory. Strengthens it permanently."""
            r = store.use(memory_id)
            return f"{r['id']} now {r['tier']} {r['strength']:.2f}"

        return [memory_summary, remember, recall, use_memory]
