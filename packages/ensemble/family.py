"""A family of projects: resemblance, not rules.

    <root>/family.json   the tree, traits, epigenetic marks, sayings, heirlooms, wisdom
    <root>/family.md     the same, for people to read

Each project keeps its own MemoryStore. The family holds only what passes between them:

  traits      tendencies read from how a project actually behaved (curiosity, skepticism,
              steadiness, expressiveness). A child starts from its relatives' traits, blended
              by closeness, and its own experience moves them from there.
  marks       epigenetic: a big experience (mark()) leaves heightened sensitivity to a theme.
              Marks travel parent to child at half strength, so a grandparent's arrives as a
              quarter, unless a calm parent let it fade first. A similar experience renews it
              at full strength; a calm life lets it fade (x0.85 per night).
  sayings     lessons told as family advice, with who learned them. They surface when
              relevant and carry no authority: a child adopts one, and it must be confirmed
              by use like any idea. Confirmations across the family raise a saying's weight;
              being voted down lowers it.
  heirlooms   a few specific memories handed down intact, with their context.
  wisdom      what only the family can see: lessons that recur across members, found at reunions.

Everything is capped, so the family store stays small across any number of generations.
"""
import fcntl
import json
import os
from contextlib import contextmanager

from memory import IMAGINED, MemoryStore, keywords, overlap

TRAITS = ("curiosity", "skepticism", "steadiness", "expressiveness")
NEUTRAL = {t: 0.5 for t in TRAITS}
CAP_SAYINGS, CAP_HEIRLOOMS, CAP_WISDOM, CAP_MARKS = 60, 12, 20, 10
BIRTH_SAYINGS = 3               # a parent's most relied-on memories, told to a newborn child as sayings
DRIFT, DRIFT_MIN = 0.15, 3      # share of waking knowledge overturned (and at least this many) = drift
AGE_NIGHTS = 60                  # nights in one generation before age alone suggests coming of age
SNOOZE = 14                      # nights a declined suggestion stays quiet
MILESTONE_WORDS = {"release", "released", "launch", "launched", "rewrite", "rewrote", "pivot", "pivoted",
                   "migrated", "migration", "v2", "v3", "handover", "reorg", "sunset", "replatform"}
MILESTONE_STEMS = keywords(" ".join(MILESTONE_WORDS))
CALM = 0.85                      # an inherited mark keeps this share per night without a matching event
SIMILAR = 0.5                    # keyword overlap that counts as "the same saying" or "the same theme"


class Family:
    def __init__(self, root, embedder=None):
        self.root, self.emb = root, embedder
        os.makedirs(root, exist_ok=True)
        with self._lock():
            if not os.path.exists(self._path()):
                self._save({"members": {}, "sayings": {}, "heirlooms": {}, "wisdom": [], "next": 1})

    # ----------------------------------------------------------------- files
    def _path(self):
        return os.path.join(self.root, "family.json")

    @contextmanager
    def _lock(self):
        with open(os.path.join(self.root, ".lock"), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _load(self):
        with open(self._path()) as f:
            return json.load(f)

    def _save(self, fam):
        tmp = self._path() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(fam, f, separators=(",", ":"))
        os.replace(tmp, self._path())
        self._write_md(fam)

    @contextmanager
    def _txn(self):
        with self._lock():
            fam = self._load()
            yield fam
            self._save(fam)

    def store(self, name):
        """The member's own MemoryStore (opened with the family's embedder)."""
        return MemoryStore(self._load()["members"][name]["memory"], self.emb)

    # ------------------------------------------------------------ relations
    @staticmethod
    def _ancestors(fam, name):
        out, frontier, d = {}, list(fam["members"][name]["parents"]), 1
        while frontier:
            nxt = []
            for p in frontier:
                if p not in out:
                    out[p] = d
                    nxt += fam["members"][p]["parents"]
            frontier, d = nxt, d + 1
        return out

    def closeness(self, fam, child, other, parents=None):
        """parent 1, grandparent 0.5, great-grandparent 0.25 ...; sibling 0.3; aunt/uncle 0.15."""
        if child == other:
            return 0.0
        if sorted((child, other)) in fam.get("kin", []):
            return 0.3                                 # approved kinship: treated like siblings
        anc = self._ancestors(fam, child) if parents is None else {}
        if parents is not None:
            for p in parents:
                anc.setdefault(p, 1)
                for a, dist in self._ancestors(fam, p).items():
                    anc[a] = min(anc.get(a, 99), dist + 1)
        if other in anc:
            return 0.5 ** (anc[other] - 1)
        mine = set(parents if parents is not None else fam["members"][child]["parents"])
        theirs = set(fam["members"][other]["parents"])
        if mine & theirs:
            return 0.3
        grand = {g for p in mine for g in fam["members"][p]["parents"]}
        if grand & theirs:
            return 0.15
        return 0.0

    # --------------------------------------------------------------- traits
    @staticmethod
    def observe(store):
        """Read temperament from a project's actual history. Returns (traits, nights of evidence)."""
        idx = store._load()
        ms = idx["m"].values()
        nights = idx.get("nights", 0)
        ideas = [m for m in ms if m.get("src") in ("dream", "poem", "excursion")]
        confirmed = sum(m.get("origin") == "confirmed" for m in ideas)
        waking = sum(m.get("origin") == "waking" for m in ms) or 1
        names = sum(len(m.get("aliases", [])) for m in ms)
        t = {"curiosity": min(1.0, idx.get("excursions_total", 0) / max(1, nights) / 2),
             "skepticism": 1 - confirmed / len(ideas) if ideas else 0.5,
             "steadiness": max(0.0, 1 - 5 * idx.get("overturned", 0) / waking),
             "expressiveness": min(1.0, 4 * names / max(1, len(idx["m"])))}
        return t, nights

    def traits(self, name, fam=None):
        fam = fam or self._load()
        mem = fam["members"][name]
        t, nights = self.observe(MemoryStore(mem["memory"], self.emb))
        w = nights / (nights + 3)                      # the more it has lived, the more it is itself
        return {k: round((1 - w) * mem["born_traits"][k] + w * t[k], 3) for k in TRAITS}

    @staticmethod
    def expression(traits):
        """How traits show up as settings."""
        return {"excursions": round(3 * traits["curiosity"]),
                "poem_pairs": 1 + round(3 * traits["expressiveness"]),
                "min_score": round(0.4 + 0.3 * traits["skepticism"], 2),
                "confirm_uses": 2 + round(2 * traits["skepticism"]),
                "lesson_uses": round(5 - 2 * traits["steadiness"])}

    # ---------------------------------------------------------------- marks
    def mark(self, name, theme, strength=1.0, note=""):
        """A big experience. Renews any inherited mark on the same theme at full strength."""
        nights = self.store(name)._load().get("nights", 0)
        with self._txn() as fam:
            marks = fam["members"][name]["marks"]
            same = [m for m in marks if overlap(keywords(theme), keywords(m["theme"])) >= SIMILAR]
            for m in same:
                marks.remove(m)
            marks.append({"theme": theme, "strength": strength, "own": True, "since": nights, "note": note})
            fam["members"][name]["marks"] = sorted(marks, key=lambda m: -m["strength"])[:CAP_MARKS]

    def effective_marks(self, name, fam=None):
        fam = fam or self._load()
        mem = fam["members"][name]
        nights = MemoryStore(mem["memory"], self.emb)._load().get("nights", 0)
        out = []
        for m in mem["marks"]:
            s = m["strength"] if m["own"] else m["strength"] * CALM ** max(0, nights - m["since"])
            out.append({"theme": m["theme"], "strength": round(s, 3), "own": m["own"]})
        return out

    # ---------------------------------------------------------------- birth
    def birth(self, name, memory_root, parents=(), hand_down=True):
        """A new project, taking after its relatives. Each parent also tells the child its most
        relied-on memories as sayings (advice only), so a child born before its parent has any
        lessons still hears what the parent knows. Coming of age passes heirlooms instead."""
        parents = list(parents)
        with self._txn() as fam:
            if name in fam["members"]:
                raise ValueError(f"{name} already exists")
            weights = {o: self.closeness(fam, name, o, parents) for o in fam["members"]}
            weights = {o: w for o, w in weights.items() if w > 0}
            total = sum(weights.values())
            if total:
                rel = {o: self.traits(o, fam) for o in weights}
                born = {k: round(sum(w * rel[o][k] for o, w in weights.items()) / total, 3) for k in TRAITS}
            else:
                born = dict(NEUTRAL)
            inherited = []
            for o in parents:                              # marks travel down the line, parent to child
                for m in self.effective_marks(o, fam):
                    s = m["strength"] * 0.5                # half a parent's; a grandparent's arrives as a quarter
                    same = next((x for x in inherited if overlap(keywords(x["theme"]), keywords(m["theme"])) >= SIMILAR), None)
                    if same:
                        same["strength"] = max(same["strength"], s)
                    elif s >= 0.05:
                        inherited.append({"theme": m["theme"], "strength": round(s, 3), "own": False, "since": 0})
            fam["members"][name] = {"parents": parents, "memory": memory_root, "status": "living",
                                    "gen": 1 + max((fam["members"][p]["gen"] for p in parents), default=0),
                                    "born_traits": born, "marks": sorted(inherited, key=lambda m: -m["strength"])[:CAP_MARKS]}
        MemoryStore(memory_root, self.emb)
        told = sum(self.tell_at_birth(p) for p in parents) if hand_down else 0
        return {"traits": born, "marks": inherited, "settings": self.expression(born), "told": told}

    def tell_at_birth(self, parent, k=BIRTH_SAYINGS):
        """A parent's strongest everyday knowledge (lessons first, then by use and strength), as sayings."""
        s = self.store(parent)
        idx = s._load()
        now = idx["beat"]
        pool = [(bool(m.get("lesson")), m["uses"], s.strength(m, now), mid) for mid, m in idx["m"].items()
                if m.get("origin", "waking") in ("waking", "confirmed") and m.get("src") not in IMAGINED
                and not m.get("superseded_by") and not m.get("merged_into") and not m["dormant"]]
        told = 0
        with self._txn() as fam:
            gen = fam["members"][parent]["gen"]
            for _, _, _, mid in sorted(pool, reverse=True)[:k]:
                text = s.read(mid)
                if any(overlap(keywords(text), keywords(x["text"])) >= SIMILAR for x in fam["sayings"].values()):
                    continue
                sid = f"s{fam['next']:04d}"; fam["next"] += 1
                fam["sayings"][sid] = {"text": text, "from": parent, "gen": gen, "weight": 0.5,
                                       "confirmed_by": [], "contradicted_by": [], "told": "birth"}
                told += 1
            self._cap(fam)
        return told

    def attach(self, player):
        """Make a Player take after its family: settings from traits, sensitivities from marks."""
        fam = self._load()
        who = getattr(player, "member", player.name)
        t = self.traits(who, fam)
        ex = self.expression(t)
        player.family = self
        player.excursions, player.poem_pairs = ex["excursions"], ex["poem_pairs"]
        player.min_score = ex["min_score"]
        m = player.memory
        m.confirm_uses, m.lesson_uses = ex["confirm_uses"], ex["lesson_uses"]
        m.sensitivities = [(keywords(x["theme"]), m.emb.encode([x["theme"]], "cue")[0] if m.emb else None, x["strength"])
                           for x in self.effective_marks(who, fam) if x["strength"] >= 0.05]
        return ex

    # ------------------------------------------------- sayings and heirlooms
    def tell(self, name):
        """A member tells its lessons as family sayings (confirming ones the family already has)."""
        lessons = self.store(name).lessons()
        told = 0
        with self._txn() as fam:
            gen = fam["members"][name]["gen"]
            for l in lessons:
                same = next((sid for sid, s in fam["sayings"].items()
                             if overlap(keywords(l["text"]), keywords(s["text"])) >= SIMILAR), None)
                if same:
                    if name not in fam["sayings"][same]["confirmed_by"] and name != fam["sayings"][same]["from"]:
                        fam["sayings"][same]["confirmed_by"].append(name)
                        fam["sayings"][same]["weight"] += 1
                    continue
                sid = f"s{fam['next']:04d}"; fam["next"] += 1
                fam["sayings"][sid] = {"text": l["text"], "from": name, "gen": gen, "weight": 1.0,
                                       "confirmed_by": [], "contradicted_by": []}
                told += 1
            self._cap(fam)
        return told

    def heirloom(self, name, memory_id, why=""):
        """Hand down one specific memory intact, with its context."""
        s = self.store(name)
        m = s._load()["m"][memory_id]
        context = [s.read(p) for p in m.get("parents", []) if p in s._load()["m"]]
        with self._txn() as fam:
            hid = f"h{fam['next']:04d}"; fam["next"] += 1
            fam["heirlooms"][hid] = {"text": s.read(memory_id), "context": context, "why": why,
                                     "from": name, "gen": fam["members"][name]["gen"]}
            self._cap(fam)
        return hid

    def advice(self, name, context, k=2):
        """Family sayings, wisdom and heirlooms relevant to a situation, closest relatives first."""
        if not context.strip():
            return []
        fam = self._load()
        ckw = keywords(context)
        found = []
        for sid, s in fam["sayings"].items():
            if s["from"] == name:
                continue
            rel = overlap(ckw, keywords(s["text"]))
            near = max(self.closeness(fam, name, s["from"]), 0.1)
            if rel >= 0.25:
                found.append((rel * near * (1 + 0.5 * s["weight"]), "saying", sid, s))
        for i, w in enumerate(fam["wisdom"]):
            rel = overlap(ckw, keywords(w["text"]))
            if rel >= 0.25:
                found.append((rel * 2, "wisdom", f"w{i}", w))
        for hid, h in fam["heirlooms"].items():
            rel = overlap(ckw, keywords(h["text"]))
            if rel >= 0.25:
                found.append((rel * 1.5, "heirloom", hid, h))
        found.sort(key=lambda x: -x[0])
        return [{"kind": kind, "id": i, "item": it} for _, kind, i, it in found[:k]]

    def inheritance(self, name, k=3):
        """What this member was handed, for when nothing is open to match advice against: heirlooms
        from its own predecessor first, then sayings from its ancestors, closest and weightiest first."""
        fam = self._load()
        anc = self._ancestors(fam, name)
        found = []
        for hid, h in fam["heirlooms"].items():
            if h["from"] in anc:
                found.append((3.0 / anc[h["from"]], "heirloom", hid, h))
        for sid, sv in fam["sayings"].items():
            if sv["from"] in anc and sv["weight"] > 0:
                found.append((self.closeness(fam, name, sv["from"]) * (1 + 0.5 * sv["weight"]), "saying", sid, sv))
        found.sort(key=lambda x: -x[0])
        return [{"kind": kind, "id": i, "item": it} for _, kind, i, it in found[:k]]

    def describe_origin(self, fam, name, item):
        if "members" in item:
            return f"family wisdom, seen in {', '.join(item['members'])}"
        gens = fam["members"][name]["gen"] - item["gen"]
        who = item["from"]
        rel = {1: "your parent", 2: "your grandparent"}.get(gens, f"{gens} generations back")
        if who not in self._ancestors(fam, name):
            rel = "a relative"
        return f"from {who}, {rel}"

    def adopt(self, name, saying_id):
        """Take a family saying into this member's own memory, as an unproven inherited idea."""
        fam = self._load()
        s = fam["sayings"].get(saying_id) or fam["heirlooms"][saying_id]
        return self.store(name).remember(s["text"], 0.5, source=f"family:{saying_id}")

    # -------------------------------------------------------------- reunion
    def reunion(self):
        """Living members tell their lessons; adopted sayings are scored by how they fared; lessons
        recurring across members become family wisdom; traits are refreshed."""
        fam = self._load()
        living = [n for n, m in fam["members"].items() if m["status"] == "living"]
        told = sum(self.tell(n) for n in living)
        lessons = {n: self.store(n).lessons() for n in living}
        outcome = {"told": told, "confirmed": 0, "contradicted": 0, "wisdom": []}
        with self._txn() as fam:
            for n in living:
                for m in self.store(n)._load()["m"].values():
                    src = m.get("src", "")
                    if not src.startswith("family:"):
                        continue
                    s = fam["sayings"].get(src.split(":", 1)[1])
                    if s is None:
                        continue
                    if m.get("superseded_by") and n not in s["contradicted_by"]:
                        s["contradicted_by"].append(n); s["weight"] -= 1; outcome["contradicted"] += 1
                    elif m.get("origin") == "confirmed" and n not in s["confirmed_by"]:
                        s["confirmed_by"].append(n); s["weight"] += 1; outcome["confirmed"] += 1
            pool = [(n, l["text"]) for n, ls in lessons.items() for l in ls]
            for i, (n1, t1) in enumerate(pool):
                group = {n1} | {n2 for n2, t2 in pool[i + 1:] if n2 != n1 and overlap(keywords(t1), keywords(t2)) >= SIMILAR}
                if len(group) >= 2 and not any(overlap(keywords(t1), keywords(w["text"])) >= SIMILAR for w in fam["wisdom"]):
                    w = {"text": t1, "members": sorted(group), "gen": max(fam["members"][g]["gen"] for g in group)}
                    fam["wisdom"].append(w)
                    outcome["wisdom"].append(w["text"])
            self._cap(fam)
        outcome["kin_suggestions"] = self.suggest_kin()
        return outcome

    def retire(self, name):
        """A project ends: it tells its lessons one last time. Its memory store stays where it is."""
        told = self.tell(name)
        with self._txn() as fam:
            fam["members"][name]["status"] = "retired"
            fam["members"][name]["final_traits"] = self.traits(name, fam)
        return told

    # ------------------------------------------- generations within a project
    def maturity(self, name):
        """Why this project might be ready for a new generation (empty list: it isn't)."""
        s = self.store(name)
        idx = s._load()
        nights = idx.get("nights", 0)
        waking = [m for m in idx["m"].values() if m.get("origin") == "waking"]
        reasons = []
        over = idx.get("overturned", 0)
        if over >= DRIFT_MIN and over / max(1, len(waking)) >= DRIFT:
            reasons.append(f"drift: {over} things it knew were overturned, against {len(waking)} current waking memories")
        if nights >= AGE_NIGHTS:
            reasons.append(f"age: {nights} nights in this generation")
        for k, m in idx["m"].items():
            if m.get("origin") == "waking" and keywords(m["head"]) & MILESTONE_STEMS and not m.get("milestone_seen"):
                reasons.append(f"possible milestone: \"{m['head'][:80]}\"")
        return reasons

    def suggest(self, name):
        """Conductor's check. Records a pending suggestion (unless one is pending or snoozed)."""
        reasons = self.maturity(name)
        nights = self.store(name)._load().get("nights", 0)
        with self._txn() as fam:
            cur = fam.setdefault("suggestions", {}).get(name)
            if cur and (cur["status"] == "pending" or (cur["status"] == "declined" and nights < cur["until"])):
                return cur if cur["status"] == "pending" else None
            if not reasons:
                return None
            fam["suggestions"][name] = {"reasons": reasons, "status": "pending", "night": nights}
            return fam["suggestions"][name]

    def decline(self, name):
        nights = self.store(name)._load().get("nights", 0)
        s = self.store(name)
        with s._txn() as idx:                         # these milestone hints have been seen
            for m in idx["m"].values():
                if keywords(m["head"]) & MILESTONE_STEMS:
                    m["milestone_seen"] = True
        with self._txn() as fam:
            fam["suggestions"][name].update(status="declined", until=nights + SNOOZE)

    def approve(self, name, memory_root):
        """Approve the conductor's suggestion: the project comes of age."""
        return self.come_of_age(name, memory_root, why="; ".join(self._load()["suggestions"][name]["reasons"]))

    def milestone(self, name, memory_root, note):
        """You declare a milestone: the project comes of age now, no suggestion needed."""
        return self.come_of_age(name, memory_root, why=note)

    def come_of_age(self, name, memory_root, why="", heirlooms=3, extra_parents=()):
        """The current generation retires as the parent of the next: lessons become sayings, its
        most relied-on memories become heirlooms, traits and marks pass on. The new generation
        starts with clean everyday memory under a new name (project@2, project@3, ...)."""
        s = self.store(name)
        idx = s._load()
        best = sorted((k for k, m in idx["m"].items() if m.get("origin") in ("waking", "confirmed")
                       and not m.get("lesson") and not m.get("superseded_by")),
                      key=lambda k: -idx["m"][k]["uses"])[:heirlooms]
        for k in best:
            self.heirloom(name, k, f"carried over when {name} came of age")
        self.retire(name)
        base = name.split("@")[0]
        n = int(name.split("@")[1]) + 1 if "@" in name else 2
        child = f"{base}@{n}"
        born = self.birth(child, memory_root, [name, *extra_parents], hand_down=False)
        with self._txn() as fam:
            fam["members"][child]["came_of_age"] = {"from": name, "why": why}
            if name in fam.get("suggestions", {}):
                fam["suggestions"][name]["status"] = "approved"
        return dict(born, name=child, heirlooms=len(best))

    # --------------------------------------------------------------- kinship
    def suggest_kin(self, min_shared=2):
        """Unrelated projects whose lessons keep overlapping: proposed as kin, for approval."""
        fam = self._load()
        living = [n for n, m in fam["members"].items() if m["status"] == "living"]
        lessons = {n: [keywords(l["text"]) for l in self.store(n).lessons()] for n in living}
        out = []
        for i, a in enumerate(living):
            for b in living[i + 1:]:
                if self.closeness(fam, a, b) > 0 or sorted((a, b)) in fam.get("declined_kin", []):
                    continue
                shared = sum(any(overlap(x, y) >= SIMILAR for y in lessons[b]) for x in lessons[a])
                if shared >= min_shared:
                    out.append({"a": a, "b": b, "shared_lessons": shared})
        with self._txn() as fam:
            fam["kin_suggestions"] = out
        return out

    def approve_kin(self, a, b):
        with self._txn() as fam:
            pair = sorted((a, b))
            if pair not in fam.setdefault("kin", []):
                fam["kin"].append(pair)

    def decline_kin(self, a, b):
        with self._txn() as fam:
            fam.setdefault("declined_kin", []).append(sorted((a, b)))

    # ------------------------------------------------------------------ caps
    @staticmethod
    def _cap(fam):
        top = sorted(fam["sayings"].items(), key=lambda kv: (-kv[1]["weight"], -kv[1]["gen"]))[:CAP_SAYINGS]
        fam["sayings"] = dict(top)
        fam["heirlooms"] = dict(list(fam["heirlooms"].items())[-CAP_HEIRLOOMS:])
        fam["wisdom"] = fam["wisdom"][-CAP_WISDOM:]

    def _write_md(self, fam):
        lines = ["# Family", ""]
        for n, m in sorted(fam["members"].items(), key=lambda kv: kv[1]["gen"]):
            parents = " + ".join(m["parents"]) or "founder"
            marks = ", ".join(f"{x['theme']} {x['strength']:.2f}" for x in m["marks"]) or "none"
            lines.append(f"- **{n}** (generation {m['gen']}, {m['status']}, from {parents}); marks: {marks}")
        lines += ["", "## Wisdom", ""] + [f"- {w['text']} (seen in {', '.join(w['members'])})" for w in fam["wisdom"]]
        lines += ["", "## Sayings", ""] + [f"- {s['text']} ({s['from']}, weight {s['weight']:g})"
                                         for s in fam["sayings"].values()]
        lines += ["", "## Heirlooms", ""] + [f"- {h['text']} ({h['from']}: {h['why']})" for h in fam["heirlooms"].values()]
        with open(os.path.join(self.root, "family.md"), "w") as f:
            f.write("\n".join(lines) + "\n")
