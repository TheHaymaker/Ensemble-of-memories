"""MdEnsemble: the Ensemble protocol on plain markdown files.

    <root>/parts/<agent>.md   one file per agent, overwritten, size-capped.
                              A JSON header (valid YAML front matter) holds the
                              version and declared votes; the body is the note.
    <root>/score.md           generated summary, rebuilt on every write. This is
                              the file agents read each turn (via listen()).

The conductor's file also holds the beat counter and the open questions.
Fade is computed when the tally is built: a vote's weight is
confidence * gamma ** (beats since it was cast). Nothing is rewritten each beat.

Same public API as ensemble.Ensemble, so tools.Player works on either.
"""
import fcntl
import json
import os
import shutil
from contextlib import contextmanager

GAMMA = 0.97
SPLIT = 0.25
CONFLICT_WEIGHT = 1.5
CAP = 4096          # bytes per part file, header included


class MdEnsemble:
    def __init__(self, root, roster, gamma=GAMMA, cap=CAP):
        if not roster or len(set(roster)) != len(roster):
            raise ValueError("roster must hold unique names")
        self.root, self.roster, self.gamma, self.cap = root, list(roster), gamma, cap
        self.conductor = self.roster[0]
        os.makedirs(os.path.join(root, "parts"), exist_ok=True)
        with self._lock():
            if not os.path.exists(self._path(self.conductor)):
                self._write(self.conductor, {"version": 0, "votes": {}, "beat": 0, "serial": 0,
                                             "questions": {}}, "")
                self._regen()

    # ------------------------------------------------------------------ files
    def _path(self, agent):
        return os.path.join(self.root, "parts", f"{agent}.md")

    @contextmanager
    def _lock(self):
        with open(os.path.join(self.root, ".lock"), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _parse(text):
        _, header, body = text.split("---\n", 2)
        return json.loads(header), body.rstrip("\n")

    def _read(self, agent, root=None):
        path = os.path.join(root, "parts", f"{agent}.md") if root else self._path(agent)
        if not os.path.exists(path):
            return {"version": 0, "votes": {}}, None
        with open(path) as f:
            return self._parse(f.read())

    def _atomic(self, path, text):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, path)

    def _write(self, agent, meta, note):
        meta = dict(meta, version=meta.get("version", 0) + 1)
        text = f"---\n{json.dumps(meta, separators=(',', ':'))}\n---\n{note}\n"
        size = len(text.encode())
        if size > self.cap:
            raise ValueError(f"part would be {size} bytes; the limit is {self.cap}")
        self._atomic(self._path(agent), text)
        return meta["version"], size

    # ------------------------------------------------------------------ tally
    def _live(self, reg, qid, vote):
        q = reg["questions"].get(qid)
        return q is not None and q["n"] == vote[3]

    def _tally(self):
        reg, _ = self._read(self.conductor)
        now = reg["beat"]
        acc = {qid: {"net": 0.0, "w": 0.0, "opts": {o: 0.0 for o in (q["options"] or [])}}
               for qid, q in reg["questions"].items()}
        for a in self.roster:
            meta, _ = self._read(a)
            for qid, v in meta["votes"].items():
                if not self._live(reg, qid, v):
                    continue
                eff = v[1] * self.gamma ** (now - v[2])
                if reg["questions"][qid]["options"]:
                    acc[qid]["opts"][v[0]] += eff
                else:
                    acc[qid]["net"] += eff if v[0] == "yes" else -eff
                    acc[qid]["w"] += eff
        res = {}
        for qid, q in reg["questions"].items():
            a = acc[qid]
            extra = {"text": q["text"]} if q.get("text") else {}
            if q["options"]:
                tot = sum(a["opts"].values())
                res[qid] = {"weight": tot, **extra,
                            "shares": {o: (x / tot if tot > 0.05 else 0.0) for o, x in a["opts"].items()}}
            else:
                w = a["w"]
                lean = a["net"] / w if w > 0.05 else 0.0
                verdict = ("none" if w <= 0.05 else "split" if abs(lean) < SPLIT
                           else "yes" if lean > 0 else "no")
                res[qid] = {"lean": lean, "weight": w, "verdict": verdict, **extra,
                            "conflict": verdict == "split" and w >= CONFLICT_WEIGHT}
        return now, res

    def _regen(self):
        beat, score = self._tally()
        lines = [f"# Score at beat {beat}", ""]
        for qid, r in score.items():
            if "lean" in r:
                lines.append(f"- **{qid}**: {r['verdict']} ({r['lean']:+.2f}, weight {r['weight']:.1f})"
                             + (" CONFLICT" if r["conflict"] else ""))
            else:
                lines.append(f"- **{qid}**: " + ", ".join(f"{o} {s:.0%}" for o, s in r["shares"].items()))
        meta = {"beat": beat, "score": score}
        self._atomic(os.path.join(self.root, "score.md"),
                     f"---\n{json.dumps(meta, separators=(',', ':'))}\n---\n" + "\n".join(lines) + "\n")

    # -------------------------------------------------------------- agent API
    def _prune(self, reg, meta):
        meta["votes"] = {k: v for k, v in meta["votes"].items() if self._live(reg, k, v)}

    def note(self, agent, text):
        with self._lock():
            reg, _ = self._read(self.conductor)
            meta, _ = self._read(agent)
            self._prune(reg, meta)
            out = self._write(agent, meta, text)
            self._regen()
            return out

    def cast(self, agent, qid, choice, confidence):
        conf = round(min(max(float(confidence), 0.0), 1.0), 3)
        with self._lock():
            reg, _ = self._read(self.conductor)
            q = reg["questions"].get(qid)
            if q is None:
                raise KeyError(f"no open question '{qid}'")
            if q["options"] and choice not in q["options"]:
                raise ValueError(f"options are {q['options']}")
            if not q["options"] and choice not in ("yes", "no"):
                raise ValueError("answer 'yes' or 'no'")
            meta, note = self._read(agent) if agent != self.conductor else (reg, self._read(agent)[1])
            self._prune(reg, meta)
            meta["votes"][qid] = [choice, conf, reg["beat"], q["n"]]
            out = self._write(agent, meta, note or "")
            self._regen()
            return out

    def withdraw(self, agent, qid):
        with self._lock():
            meta, note = self._read(agent)
            meta["votes"].pop(qid, None)
            out = self._write(agent, meta, note or "")
            self._regen()
            return out

    # ---------------------------------------------------------- conductor API
    def _conduct(self, change):
        with self._lock():
            reg, note = self._read(self.conductor)
            result = change(reg)
            self._prune(reg, reg)
            out = self._write(self.conductor, reg, note)
            self._regen()
            return result if result is not None else out

    def open_question(self, qid, options=None, text=None):
        def change(reg):
            if qid in reg["questions"]:
                raise ValueError(f"'{qid}' is already open")
            if options is not None and len(options) < 2:
                raise ValueError("a choice needs at least 2 options")
            reg["serial"] += 1
            reg["questions"][qid] = {"options": list(options) if options else None, "n": reg["serial"]}
            if text:
                reg["questions"][qid]["text"] = text[:300]
        return self._conduct(change)

    def close_question(self, qid):
        return self._conduct(lambda reg: reg["questions"].pop(qid) and None)

    def beat(self):
        def change(reg):
            reg["beat"] += 1
            return reg["beat"]
        return self._conduct(change)

    # ---------------------------------------------------------------- reading
    def state(self):
        beat, score = self._tally()
        parts = []
        for a in self.roster:
            p = self._path(a)
            meta, _ = self._read(a)
            parts.append({"agent": a, "version": meta["version"],
                          "fill": os.path.getsize(p) / self.cap if os.path.exists(p) else 0.0})
        return {"beat": beat, "parts": parts, "score": score}

    def read(self, agent):
        meta, note = self._read(agent)
        if note is None:
            return 0, None
        return meta["version"], {"note": note, "v": meta["votes"]}

    def audit(self, tol=1e-9):
        """Check that score.md (what agents read) still matches the parts it was built from."""
        try:
            with open(os.path.join(self.root, "score.md")) as f:
                stored, _ = self._parse(f.read())
        except (OSError, ValueError):
            return [{"question": "(score.md)", "off_by": "unreadable"}]
        beat, score = self._tally()
        flags = []
        for qid, r in score.items():
            s = stored["score"].get(qid)
            keys = ("lean", "weight") if "lean" in r else ("weight",)
            off = max(abs(r[k] - s[k]) for k in keys) if s else float("inf")
            if s and "verdict" in r and s.get("verdict") != r["verdict"]:
                off = max(off, 1.0)
            if stored["beat"] != beat or off > tol:
                flags.append({"question": qid, "off_by": round(off, 3)})
        return flags

    # ------------------------------------------------------------------ merge
    def merge(self, base, a, b):
        """Three-way merge of directories that diverged. Each part comes from whichever copy changed it."""
        clashes = []
        with self._lock():
            for agent in self.roster:
                v0, va, vb = (self._read(agent, r)[0]["version"] for r in (base, a, b))
                if va != v0 and vb != v0:
                    clashes.append(agent)
                src = b if (vb != v0 and va == v0) else a
                shutil.copy(os.path.join(src, "parts", f"{agent}.md"), self._path(agent))
            self._regen()
        return clashes

    def size(self):
        return sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(self.root)
                   for f in fs if f.endswith(".md"))

    # ----------------------------------------------------------------- export
    def export_wav(self, path):
        """Render the current state as an Ensemble WAV: playable, sendable over audio,
        readable by ensemble.Ensemble.read_copy(). Notes that exceed the audio part
        limit are shortened; returns the names of agents whose notes were cut."""
        from ensemble import Ensemble, SLOTS
        if len(self.roster) > SLOTS:
            raise ValueError(f"audio export holds at most {SLOTS} agents")
        for f in (path, path + ".lock"):
            if os.path.exists(f):
                os.remove(f)
        reg, _ = self._read(self.conductor)
        e = Ensemble(path, self.roster, self.gamma)
        for qid, q in sorted(reg["questions"].items(), key=lambda kv: kv[1]["n"]):
            e.open_question(qid, q["options"])
        cut = []
        with e._txn() as spec:
            areg = e._reg(spec)
            areg["t"] = reg["beat"]
            for agent in self.roster[1:] + [self.conductor]:
                meta, note = self._read(agent)
                part = areg if agent == self.conductor else {"note": "", "v": {}}
                for qid, v in meta["votes"].items():
                    if not self._live(reg, qid, v):
                        continue
                    q = areg["q"][qid]
                    choice = (1 if v[0] == "yes" else -1) if q["k"] == "b" else v[0]
                    e._play(spec, e._contrib(q, choice, v[1], v[2], reg["beat"]))
                    part["v"][qid] = [choice, v[1], v[2], q["n"]]
                note = note or ""
                while True:
                    part["note"] = note
                    try:
                        e._put(spec, agent, part)
                        break
                    except ValueError:
                        note = note[: int(len(note) * 0.8)] + "..."
                        if agent not in cut:
                            cut.append(agent)
        return cut
