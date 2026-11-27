"""Ensemble: one fixed-size WAV file as the shared state of a multi-agent system.

Layout of the buffer (48 kHz mono 16-bit, 96 blocks x 1024 samples = 2.05 s, 196,652 bytes):

  bins 5, 7, 9   PILOTS  fixed tones. Let a reader find the time offset and gain
                         of any copy (e.g. after an MP3 round trip).
  bins 10-73     SCORE   consensus tones. A vote is a tone added with + phase for
                         yes / - for no, scaled by confidence; a second tone carries
                         the confidence alone. The mix *is* the tally: one FFT reads
                         every question. Disagreement cancels; agreement adds.
  bins 80-457    PARTS   one 40-carrier OFDM band per agent (QPSK, zlib, CRC32).
                         Each agent overwrites only its own band. Exact, lossless only.

The conductor (roster[0]) owns the question registry and the beat counter, stored
in its own part. On every beat the score decays by `gamma`, so votes that are not
re-affirmed fade out (crashed agents stop counting without cleanup).

Every agent declares its votes in its own part as well as playing them into the
score. audit() re-plays the declared parts and compares with the score: the
"check the combined performance against the parts" test.
"""
import fcntl
import json
import os
import struct
import wave
import zlib
from contextlib import contextmanager

import numpy as np

FS, N, SYMS = 48_000, 1024, 96
NB = N // 2 + 1
PILOTS = (5, 7, 9)
CB0, CBN = 10, 64                    # score bins 10..73 (469-3422 Hz)
CH0, WIDTH, GUARD, SLOTS = 80, 40, 2, 9
MAXW = 9.0                  # most confidence any one score bin can hold (1 per agent)
A_CH = 0.5 / (SLOTS * WIDTH)         # per-carrier amplitude, parts
A_V = 0.4 / (CBN * MAXW)             # amplitude of one unit of confidence, score
P_UNITS = 8.0                        # pilot strength in confidence units
G_CH, G_V = A_CH * N / 2, A_V * N / 2
HDR = struct.Struct(">BHI")          # version, payload length, crc32
CAP = SYMS * WIDTH * 2 // 8 - HDR.size   # 953 compressed bytes per part
GAMMA = 0.97
SPLIT = 0.25                          # |lean| below this = split
CONFLICT_WEIGHT = 1.5                 # a split only matters with this much confidence cast


class Ensemble:
    def __init__(self, path, roster, gamma=GAMMA):
        if not 1 <= len(roster) <= SLOTS or len(set(roster)) != len(roster):
            raise ValueError(f"roster must hold 1-{SLOTS} unique names")
        self.path, self.roster, self.gamma = path, list(roster), gamma
        self.conductor = self.roster[0]
        with self._lock():
            if not os.path.exists(path):
                spec = self._blank()
                self._put(spec, self.conductor, {"note": "", "v": {}, "t": 0, "c": 0, "q": {}})
                self._save(spec)

    # ------------------------------------------------------------------ file
    @contextmanager
    def _lock(self):
        with open(self.path + ".lock", "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    @contextmanager
    def _txn(self):
        """Read-modify-write under an exclusive lock; nothing is saved if the body raises."""
        with self._lock():
            spec = self._load()
            yield spec
            self._save(spec)

    @staticmethod
    def _samples(path):
        with wave.open(path, "rb") as w:
            if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, FS, 2):
                raise ValueError("expected 48 kHz mono 16-bit WAV")
            return np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32767.0

    def _blank(self):
        spec = np.zeros((SYMS, NB), complex)
        spec[:, list(PILOTS)] = P_UNITS * G_V
        return spec

    def _load(self, path=None):
        x = self._samples(path or self.path)
        return self._clean(np.fft.rfft(x.reshape(SYMS, N), axis=1))

    def _clean(self, spec):
        """Regenerate the signal like a repeater: snap every part to ideal QPSK and
        every score bin to its mean, zero everything else. Noise cannot accumulate."""
        out = self._blank()
        for a in self.roster:
            b = self._band(a)
            s = spec[:, b] / G_CH
            active = np.abs(s).mean(axis=1) > 0.5
            snapped = (np.where(s.real < 0, -1, 1) + 1j * np.where(s.imag < 0, -1, 1)) / np.sqrt(2)
            out[active, b] = snapped[active] * G_CH
        units = spec[:, CB0:CB0 + CBN].mean(axis=0).real / G_V
        out[:, CB0:CB0 + CBN] = np.round(units, 3) * G_V      # snap to the 0.001 grid: no drift
        return out

    def _save(self, spec):
        x = np.fft.irfft(spec, n=N, axis=1).ravel()
        if np.abs(x).max() > 1:
            raise RuntimeError("mix would clip")
        tmp = self.path + ".tmp"
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(FS)
            # TPDF dither: turns rounding error from tone-correlated distortion into noise
            d = np.random.default_rng().random((2, x.size)).sum(axis=0) - 1.0
            w.writeframes(np.clip(np.round(x * 32767 + d), -32767, 32767).astype("<i2").tobytes())
        os.replace(tmp, self.path)       # readers never see a half-written file

    # ----------------------------------------------------------------- parts
    def _band(self, agent):
        start = CH0 + self.roster.index(agent) * (WIDTH + GUARD)
        return slice(start, start + WIDTH)

    def _raw(self, spec, agent, rows=None, gain=1.0):
        s = spec[:rows, self._band(agent)] / (G_CH * gain)
        active = np.abs(s).mean(axis=1) > 0.5
        n = len(active) if active.all() else int(np.argmin(active))
        s = s[:n].ravel()
        bits = np.empty(s.size * 2, np.uint8)
        bits[0::2], bits[1::2] = s.real < 0, s.imag < 0
        return np.packbits(bits).tobytes()

    def _header(self, spec, agent):
        raw = self._raw(spec, agent, rows=1)
        return HDR.unpack(raw[:HDR.size]) if len(raw) >= HDR.size else (0, 0, 0)

    def _get(self, spec, agent, gain=1.0):
        raw = self._raw(spec, agent, gain=gain)
        if len(raw) < HDR.size:
            return 0, None
        ver, ln, crc = HDR.unpack(raw[:HDR.size])
        data = raw[HDR.size:HDR.size + ln]
        if len(data) != ln or zlib.crc32(data) != crc:
            raise IOError(f"part of {agent} failed its checksum")
        return ver, json.loads(zlib.decompress(data))

    def _put(self, spec, agent, obj):
        data = zlib.compress(json.dumps(obj, separators=(",", ":")).encode(), 9)
        if len(data) > CAP:
            raise ValueError(f"part would be {len(data)} bytes compressed; the limit is {CAP}")
        ver = self._header(spec, agent)[0] % 255 + 1
        frame = HDR.pack(ver, len(data), zlib.crc32(data)) + data
        bits = np.unpackbits(np.frombuffer(frame, np.uint8))
        bits = np.pad(bits, (0, -len(bits) % (2 * WIDTH)))
        sym = ((1 - 2.0 * bits[0::2]) + 1j * (1 - 2.0 * bits[1::2])) / np.sqrt(2)
        b = self._band(agent)
        spec[:, b] = 0
        spec[: len(sym) // WIDTH, b] = sym.reshape(-1, WIDTH) * G_CH
        return ver, len(data)

    def _part(self, spec, agent, reg):
        if agent == self.conductor:
            return reg
        return self._get(spec, agent)[1] or {"note": "", "v": {}}

    # ----------------------------------------------------------------- score
    def _reg(self, spec):
        return self._get(spec, self.conductor)[1]

    @staticmethod
    def _width(q):
        return 2 if q["k"] == "b" else len(q["o"])

    def _contrib(self, q, choice, conf, cast_t, now):
        eff = conf * self.gamma ** (now - cast_t)
        if q["k"] == "b":
            return {CB0 + q["s"]: choice * eff, CB0 + q["s"] + 1: eff}
        return {CB0 + q["s"] + q["o"].index(choice): eff}

    @staticmethod
    def _live(reg, qid, vote):
        q = reg["q"].get(qid)
        return q is not None and q["n"] == vote[3]

    def _prune(self, reg, part):
        part["v"] = {k: v for k, v in part["v"].items() if self._live(reg, k, v)}

    @staticmethod
    def _play(spec, contrib, sign=1):
        for b, amt in contrib.items():
            spec[:, b] += sign * amt * G_V

    def _score(self, vals, reg):
        res = {}
        for qid, q in reg["q"].items():
            s = q["s"]
            if q["k"] == "b":
                net, w = float(vals[s]), float(vals[s + 1])
                lean = net / w if w > 0.05 else 0.0
                verdict = ("none" if w <= 0.05 else "split" if abs(lean) < SPLIT
                           else "yes" if lean > 0 else "no")
                res[qid] = {"lean": lean, "weight": w, "verdict": verdict,
                            "conflict": verdict == "split" and w >= CONFLICT_WEIGHT}
            else:
                sup = np.clip(vals[s:s + len(q["o"])], 0, None)
                tot = float(sup.sum())
                res[qid] = {"weight": tot,
                            "shares": {o: (float(x) / tot if tot > 0.05 else 0.0) for o, x in zip(q["o"], sup)}}
        return res

    # ------------------------------------------------------------ agent API
    def note(self, agent, text):
        """Overwrite the agent's note (its current state, not a log)."""
        with self._txn() as spec:
            reg = self._reg(spec)
            part = self._part(spec, agent, reg)
            self._prune(reg, part)
            part["note"] = text
            return self._put(spec, agent, part)

    def cast(self, agent, qid, choice, confidence):
        """Vote (binary: 'yes'/'no') or choose an option. Replaces any earlier vote on qid."""
        conf = round(min(max(float(confidence), 0.0), 1.0), 3)
        with self._txn() as spec:
            reg = self._reg(spec)
            q = reg["q"].get(qid)
            if q is None:
                raise KeyError(f"no open question '{qid}'")
            if q["k"] == "b":
                if choice not in ("yes", "no"):
                    raise ValueError("answer 'yes' or 'no'")
                choice = 1 if choice == "yes" else -1
            elif choice not in q["o"]:
                raise ValueError(f"options are {q['o']}")
            part = self._part(spec, agent, reg)
            self._prune(reg, part)
            old = part["v"].get(qid)
            if old:
                self._play(spec, self._contrib(q, old[0], old[1], old[2], reg["t"]), -1)
            self._play(spec, self._contrib(q, choice, conf, reg["t"], reg["t"]))
            part["v"][qid] = [choice, conf, reg["t"], q["n"]]
            return self._put(spec, agent, part)

    def withdraw(self, agent, qid):
        with self._txn() as spec:
            reg = self._reg(spec)
            part = self._part(spec, agent, reg)
            self._prune(reg, part)
            old = part["v"].pop(qid, None)
            if old:
                self._play(spec, self._contrib(reg["q"][qid], old[0], old[1], old[2], reg["t"]), -1)
            return self._put(spec, agent, part)

    # ------------------------------------------------------- conductor API
    def open_question(self, qid, options=None, text=None):
        """text is accepted for interface compatibility; the audio registry has no room for it."""
        with self._txn() as spec:
            reg = self._reg(spec)
            if qid in reg["q"]:
                raise ValueError(f"'{qid}' is already open")
            if options is not None and len(options) < 2:
                raise ValueError("a choice needs at least 2 options")
            need = len(options) if options else 2
            used = set()
            for q in reg["q"].values():
                used.update(range(q["s"], q["s"] + self._width(q)))
            slot = next((s for s in range(CBN - need + 1)
                         if used.isdisjoint(range(s, s + need))), None)
            if slot is None:
                raise RuntimeError("the score is full; close a question first")
            reg["c"] += 1
            reg["q"][qid] = {"k": "c" if options else "b", "s": slot, "o": list(options or []), "n": reg["c"]}
            spec[:, CB0 + slot:CB0 + slot + need] = 0
            return self._put(spec, self.conductor, reg)

    def close_question(self, qid):
        with self._txn() as spec:
            reg = self._reg(spec)
            q = reg["q"].pop(qid)
            spec[:, CB0 + q["s"]:CB0 + q["s"] + self._width(q)] = 0
            self._prune(reg, reg)
            return self._put(spec, self.conductor, reg)

    def beat(self):
        """Advance time one beat: the whole score fades by gamma."""
        with self._txn() as spec:
            reg = self._reg(spec)
            reg["t"] += 1
            spec[:, CB0:CB0 + CBN] = np.round(spec[:, CB0:CB0 + CBN].real / G_V * self.gamma, 3) * G_V
            self._put(spec, self.conductor, reg)
            return reg["t"]

    # --------------------------------------------------------------- reading
    def state(self):
        """Cheap: decodes the registry and the 1-block header of each part, plus one score read."""
        spec = self._load()
        reg = self._reg(spec)
        parts = []
        for a in self.roster:
            ver, ln, _ = self._header(spec, a)
            parts.append({"agent": a, "version": ver,
                          "fill": (ln + HDR.size) / (CAP + HDR.size) if ver else 0.0})
        return {"beat": reg["t"], "parts": parts,
                "score": self._score(spec[0, CB0:CB0 + CBN].real / G_V, reg)}

    def read(self, agent):
        spec = self._load()
        return self._get(spec, agent)

    def audit(self, tol=0.05):
        """Replay every agent's declared votes and compare with what the score actually holds."""
        spec = self._load()
        reg = self._reg(spec)
        expected = np.zeros(CBN)
        for a in self.roster:
            part = self._part(spec, a, reg)
            for qid, v in part["v"].items():
                if self._live(reg, qid, v):
                    for b, amt in self._contrib(reg["q"][qid], v[0], v[1], v[2], reg["t"]).items():
                        expected[b - CB0] += amt
        measured = spec[0, CB0:CB0 + CBN].real / G_V
        flags = []
        for qid, q in reg["q"].items():
            sl = slice(q["s"], q["s"] + self._width(q))
            diff = float(np.abs(measured[sl] - expected[sl]).max())
            if diff > tol:
                flags.append({"question": qid, "off_by": round(diff, 3)})
        return flags

    def read_copy(self, path, reg=None):
        """Read the score from any copy of the mix: shifted, rescaled or MP3-compressed.
        Pilots give the time offset and gain. Parts are tried too and reported if intact."""
        x = self._samples(path)
        whole = len(x) // N
        Y = np.fft.rfft(x[: whole * N].reshape(whole, N), axis=1).mean(axis=0)
        d = np.arange(N)
        p = np.array(PILOTS)
        score = (Y[p][None, :] * np.exp(2j * np.pi * np.outer(d, p) / N)).real.sum(axis=1)
        off = int(d[np.argmax(score)])
        rows = min(SYMS, (len(x) - off) // N)
        spec = np.zeros((SYMS, NB), complex)
        spec[:rows] = np.fft.rfft(x[off: off + rows * N].reshape(rows, N), axis=1)
        gain = float(np.abs(spec[:rows, list(PILOTS)].mean(axis=0)).mean() / (P_UNITS * G_V))
        intact = []
        for a in self.roster:
            try:
                ver, obj = self._get(spec, a, gain=gain)
                if obj is not None:
                    intact.append(a)
                    if a == self.conductor and reg is None:
                        reg = obj
            except (IOError, ValueError, zlib.error, UnicodeDecodeError, json.JSONDecodeError):
                pass
        if reg is None:
            raise IOError("registry unreadable in this copy; pass reg= from a lossless copy")
        vals = spec[:rows, CB0:CB0 + CBN].mean(axis=0).real / G_V / gain
        return {"offset": off, "gain": gain, "intact_parts": intact, "score": self._score(vals, reg)}

    # ----------------------------------------------------------------- merge
    def merge(self, base, a, b):
        """Three-way merge of copies that diverged (e.g. two hosts). Parts are disjoint,
        so each comes from whichever copy changed it; the score is additive, so
        merged = a + b - base. Writes the result to this ensemble's file."""
        S0, SA, SB = (self._load(p) for p in (base, a, b))
        out = self._blank()
        clashes = []
        for agent in self.roster:
            band = self._band(agent)
            v0, va, vb = (self._header(s, agent)[0] for s in (S0, SA, SB))
            if va != v0 and vb != v0 and va != vb:
                clashes.append(agent)
            src = SB if (vb != v0 and va == v0) else SA
            out[:, band] = src[:, band]
        out[:, CB0:CB0 + CBN] = SA[:, CB0:CB0 + CBN] + SB[:, CB0:CB0 + CBN] - S0[:, CB0:CB0 + CBN]
        with self._lock():
            self._save(out)
        return clashes
