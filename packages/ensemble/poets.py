"""Poets for MemoryStore.compose(). Poem-making is not sense-making, and it refuses the likely.
A poet sees two disparate memories (or a memory and some domain text) and offers MANY
candidates per figure and per alias. Each candidate may carry the model's own likelihood:
    {"text": ..., "logprob": mean token log-prob}   from the model's log-probs (best), or
    {"text": ..., "p": verbalized probability}       the model's own estimate, or
    "text"                                           scored offline by word frequency
The engine always excludes the likelier half and keeps the least likely candidate that
still points unambiguously at its memory.

    {"figures": [...], "aliases": {"A": [...], "B": [...]},
     "glosses": {"A": str, "B": str},   precise restatements: precision, not surprise
     "probes":  {"A": str, "B": str},   where does each stop being true?
     "verse": str, "score": 0..1}

GeminiPoet     verbalized sampling (asks for candidates WITH probabilities, from the tails),
               high temperature, and on Vertex AI the real token log-probs per candidate.
LlamaCppPoet   a local model through llama-server with the XTC sampler (exclude top choices)
               and per-token probabilities.
HeuristicPoet  offline lexicon of plain-to-strange words; exercises the machinery only.
GeminiPoet and LlamaCppPoet were not run where this was built (no model access).
"""
import json
import math
import re
import urllib.request

LEXICON = {
    "password": ["key", "secret", "gate-word", "cipher-seed"],
    "database": ["store", "ledger", "the deep shelf", "reliquary"],
    "rotate": ["change", "renewal", "molting", "phoenix-cycle"],
    "staging": ["test", "rehearsal", "understudy stage", "the green room"],
    "monthly": ["schedule", "moon-count", "lunar ledger", "the slow clock"],
    "deploy": ["release", "launch", "the unmooring", "first flight"],
    "tuesday": ["weekday", "the hinge days", "calendar teeth"],
    "token": ["pass", "ticket", "the brief coin", "wax seal"],
    "cafeteria": ["food", "canteen", "the feeding hall", "bread-house"],
    "audit": ["check", "witness", "auditor's lamp", "the ledger-reader"],
    "printer": ["printer", "ink machine", "paper-mouth", "the stutterer"],
}
CONCEPT_OF = {"passwords": "password", "creds": "password", "credentials": "password", "db": "database",
              "rotates": "rotate", "rotation": "rotate", "rotated": "rotate", "deploys": "deploy",
              "release": "deploy", "releases": "deploy", "tokens": "token", "session": "token",
              "audits": "audit", "thursday": "tuesday", "weekly": "monthly", "month": "monthly",
              "canteen": "cafeteria", "lunch": "cafeteria", "printers": "printer", "jams": "printer"}

PROMPT = """You are making poems from an AI agent's memories. This is NOT sense-making: do not
summarize, explain, moralize or conclude. Refuse the phrase you would most expect to write.

A ({a_tier}): {a_text}
B ({b_tier}): {b_text}

For each list, give 8 candidates sampled from the TAILS of your distribution (each with
probability below 0.10), each with your estimated probability "p". Aliases must still be
unmistakably about their memory: strange, but exact.

JSON only:
{{"figures": [{{"text": "analogy between A and B", "p": 0.0}}, ...],
  "aliases": {{"A": [{{"text": "name for A", "p": 0.0}}, ...], "B": [...]}},
  "glosses": {{"A": "A restated with maximum precision", "B": "..."}},
  "probes": {{"A": "where does A stop being true?", "B": "..."}},
  "verse": "two to four lines", "score": 0.0}}"""


def _concepts(text):
    out = []
    for w in re.findall(r"[a-z]+", text.lower()):
        c = CONCEPT_OF.get(w, w)
        if c in LEXICON and c not in out:
            out.append(c)
    return out


class HeuristicPoet:
    def __call__(self, a, b, sim):
        ca, cb = _concepts(a["text"]), _concepts(b["text"])
        if not ca or not cb:
            return None

        def handles(cs):
            x, y = cs[0], cs[1] if len(cs) > 1 else cs[0]
            return [f"the {p} of {q}" for p in LEXICON[x] for q in LEXICON[y] if p != q]

        x, y = LEXICON[ca[0]], LEXICON[cb[0]]
        return {"figures": [f"{p} is the {q} of its own world" for p in x for q in y],
                "aliases": {"A": handles(ca), "B": handles(cb)},
                "glosses": {"A": a["text"], "B": b["text"]},
                "probes": {k: f'Where does "{m["text"]}" stop being true?' for k, m in (("A", a), ("B", b))
                           if m.get("lesson")},
                "verse": f"{x[-1].capitalize()} and {y[-1]}:\none keeps time by {x[-2]}, the other by {y[-2]}.",
                "score": 0.6}


def _attach_logprobs(data, tokens):
    """Give every candidate the mean log-prob of the tokens that spelled it out."""
    text, spans, pos = "", [], 0
    for tok, lp in tokens:
        spans.append((pos, pos + len(tok), lp)); text += tok; pos += len(tok)
    def mean_lp(s):
        i = text.find(json.dumps(s)[1:-1])
        if i < 0:
            return None
        lps = [lp for a, b, lp in spans if a < i + len(s) and b > i]
        return sum(lps) / len(lps) if lps else None
    for key in ("figures",):
        for c in data.get(key, []):
            if isinstance(c, dict):
                c["logprob"] = mean_lp(c["text"])
    for side in (data.get("aliases") or {}).values():
        for c in side:
            if isinstance(c, dict):
                c["logprob"] = mean_lp(c["text"])
    for group in [data.get("figures", [])] + list((data.get("aliases") or {}).values()):
        if any(isinstance(c, dict) and c.get("logprob") is None for c in group):
            for c in group:
                if isinstance(c, dict):
                    c.pop("logprob", None)        # incomplete: fall back to verbalized p for the whole set
    return data


class GeminiPoet:
    def __init__(self, model="gemini-2.5-flash", client=None, temperature=1.3, use_logprobs=False):
        """use_logprobs=True needs Vertex AI (genai.Client(vertexai=True, ...)) and is quota-limited."""
        from google import genai
        from google.genai import types
        self.client, self.model, self._types = client or genai.Client(), model, types
        self.t, self.use_logprobs = temperature, use_logprobs

    def __call__(self, a, b, sim):
        cfg = dict(response_mime_type="application/json", temperature=self.t)
        if self.use_logprobs:
            cfg.update(response_logprobs=True, logprobs=1)
        r = self.client.models.generate_content(
            model=self.model, contents=PROMPT.format(a_tier=a["tier"], a_text=a["text"],
                                                     b_tier=b["tier"], b_text=b["text"]),
            config=self._types.GenerateContentConfig(**cfg))
        try:
            data = json.loads(r.text)
        except (TypeError, json.JSONDecodeError):
            return None
        lr = getattr(r.candidates[0], "logprobs_result", None) if self.use_logprobs else None
        if lr and lr.chosen_candidates:
            data = _attach_logprobs(data, [(c.token, c.log_probability) for c in lr.chosen_candidates])
        return data


class LlamaCppPoet:
    """A local model via llama-server, sampling with XTC (exclude top choices)."""

    def __init__(self, url="http://127.0.0.1:8080", temperature=1.0, xtc_probability=0.5, xtc_threshold=0.1):
        self.url, self.t, self.xp, self.xt = url.rstrip("/"), temperature, xtc_probability, xtc_threshold

    def __call__(self, a, b, sim):
        body = {"prompt": PROMPT.format(a_tier=a["tier"], a_text=a["text"], b_tier=b["tier"], b_text=b["text"]),
                "temperature": self.t, "xtc_probability": self.xp, "xtc_threshold": self.xt,
                "n_predict": 1200, "n_probs": 1, "json_schema": {"type": "object"}}
        req = urllib.request.Request(self.url + "/completion", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read())
        try:
            data = json.loads(out["content"])
        except (KeyError, json.JSONDecodeError):
            return None
        probs = out.get("completion_probabilities") or []
        toks = [(p.get("token", ""), p.get("logprob", math.log(max(p.get("prob", 1e-9), 1e-9)))) for p in probs]
        return _attach_logprobs(data, toks) if toks else data
