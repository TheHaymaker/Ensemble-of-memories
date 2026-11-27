"""Judges for MemoryStore.sleep() and .daydream(). A judge sees two memories and their
similarity and returns None (nothing there) or:
    {"op": "reinforce" | "add" | "qualify" | "substitute" | "subtract" | "tension",
     "score": 0..1,                      how surprising or compelling the connection is
     "keep": id, "drop": id,             for substitute / subtract: which one is outdated
     "insight": "one sentence"}          the learning, stored as a new memory

    reinforce   they support each other
    add         together they suggest something new
    qualify     both are right under different conditions; the insight names them
    substitute  one is an updated version of the other
    subtract    one contradicts the other and is wrong
    tension     they conflict and it is unclear which holds, or when: raised for a vote

Memory dicts carry: id, text, born, src, tier, origin ("waking" or "dream"), uses.

GeminiJudge     an LLM decides and writes real insights. Not run where this was built
                (no API access): test it on your machine.
HeuristicJudge  rules on similarity, age and wording. Offline and deterministic; finds
                structure, but its insights are templates.
"""
import json
import re

NEGATION = {"not", "no", "never", "longer", "stopped", "cancelled", "canceled", "removed", "dropped", "without"}
CHANGE = {"now", "instead", "replaced", "moved", "switched", "changed", "anymore", "updated"}
CONDITION = {"except", "unless", "only", "during", "until", "before"}
TEMPLATES = ("Link: ", "No longer true: ", "Updated: ", "Conflict: ", "Both hold: ", "Unresolved: ")


def _words(text):
    return set(re.findall(r"[a-z]+", text.lower()))


class HeuristicJudge:
    def __init__(self, low=0.35, high=0.8, min_gap=10):
        self.low, self.high, self.min_gap = low, high, min_gap

    def __call__(self, a, b, sim):
        if sim < self.low:
            return None
        meta = any(m["text"].startswith(TEMPLATES) for m in (a, b))        # this judge's own templates are not claims
        new, old = (a, b) if a["born"] >= b["born"] else (b, a)
        wn, wo = _words(new["text"]), _words(old["text"])
        gap = new["born"] - old["born"]
        if sim >= self.high and meta:
            return {"op": "reinforce", "score": sim}
        if sim >= self.high:
            if bool(wn & NEGATION) != bool(wo & NEGATION):
                if gap < self.min_gap and a["src"] != b["src"]:          # same time, different voices
                    return {"op": "tension", "score": sim,
                            "insight": f'Conflict: "{old["text"]}" vs "{new["text"]}"'}
                return {"op": "subtract", "score": sim, "keep": new["id"], "drop": old["id"],
                        "insight": f'No longer true: "{old["text"]}" (contradicted by "{new["text"]}")'}
            if (wn & CHANGE) and not (wo & CHANGE) and gap > 0:
                return {"op": "substitute", "score": sim, "keep": new["id"], "drop": old["id"],
                        "insight": f'Updated: "{new["text"]}" replaces "{old["text"]}"'}
            ca, cb = _words(a["text"]) & CONDITION, _words(b["text"]) & CONDITION
            if bool(ca) != bool(cb):
                general, specific = (b, a) if ca else (a, b)
                return {"op": "qualify", "score": sim,
                        "insight": f'Both hold: "{general["text"]}" in general; "{specific["text"]}" in its stated case'}
            return {"op": "reinforce", "score": sim}
        if gap >= self.min_gap or a["src"] != b["src"]:
            score = 0.5 + 0.5 * (sim - self.low) / (self.high - self.low)
            return {"op": "add", "score": score, "insight": f'Link: "{old["text"]}" relates to "{new["text"]}"'}
        return None


class GeminiJudge:
    PROMPT = """You are the sleeping mind of an AI agent, replaying two memories together.

Memory A (formed at beat {a_born}, {a_origin}, used {a_uses} times, now {a_tier}): {a_text}
Memory B (formed at beat {b_born}, {b_origin}, used {b_uses} times, now {b_tier}): {b_text}
Semantic similarity: {sim:.2f}. "waking" memories came from real work; "dream" ones from earlier dreams.

Most pairs mean nothing. Answer "none" unless the combination is genuinely surprising or useful.
Otherwise choose one:
- "reinforce": they support each other.
- "add": together they suggest something neither says alone. Write that idea.
- "qualify": both are right under different conditions. Write when each applies.
- "substitute": one is an updated version of the other. Say which to keep.
- "subtract": one contradicts the other and is wrong. Say which to keep.
- "tension": they conflict and you cannot tell which holds, or when. Describe the conflict.
Prefer "qualify" or "tension" over discarding a lesson that may still be valuable.

Reply with JSON only:
{{"op": "none|reinforce|add|qualify|substitute|subtract|tension", "score": 0-1,
  "keep": "A|B|null", "insight": "one sentence a future you should remember, or null"}}"""

    def __init__(self, model="gemini-2.5-flash", client=None):
        from google import genai
        from google.genai import types
        self.client, self.model, self._types = client or genai.Client(), model, types

    def __call__(self, a, b, sim):
        text = self.PROMPT.format(sim=sim, **{f"a_{k}": a[k] for k in ("born", "origin", "uses", "tier", "text")},
                                  **{f"b_{k}": b[k] for k in ("born", "origin", "uses", "tier", "text")})
        r = self.client.models.generate_content(
            model=self.model, contents=text,
            config=self._types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7))
        try:
            v = json.loads(r.text)
        except (TypeError, json.JSONDecodeError):
            return None
        if v.get("op") in (None, "none"):
            return None
        out = {"op": v["op"], "score": float(v.get("score", 0)), "insight": v.get("insight")}
        keep = {"A": a["id"], "B": b["id"]}.get(v.get("keep"))
        if v["op"] in ("substitute", "subtract"):
            if not keep:
                return None
            out["keep"], out["drop"] = keep, (b["id"] if keep == a["id"] else a["id"])
        return out
