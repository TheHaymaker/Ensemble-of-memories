"""Explorers for MemoryStore.wander(): curiosity that acts on a seed anyway.

An explorer gets a seed (a poem figure, a probe, a dream link, or "what if X met Y?") and
the memories it came from, and returns a field note:
    {"form": "build-out" | "experiment" | "thought-exercise" | "hypothesis",
     "title": str, "outcome": str, "surprise": str | None,
     "verdict": "silly" | "trivial" | "nonsensical" | "beautiful failure" | "promising" | ...,
     "prediction": str | None,       hypotheses: something a later waking memory could confirm
     "spawn": [str, ...],            new ideas this one gave rise to (the engine keeps at most 2)
     "code": str | None}             experiments: only run if you give wander() a runner (your sandbox)

GeminiExplorer   an LLM plays. Not run where this was built (no API access).
HeuristicExplorer  templates; enough to exercise the machinery, not to be curious.
"""
import json
import random

FORMS = ("build-out", "experiment", "thought-exercise", "hypothesis")
VERDICTS = ("silly", "trivial", "nonsensical", "beautiful failure", "promising", "oddly useful")


class HeuristicExplorer:
    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def __call__(self, seed, context):
        form = self.rng.choice(FORMS)
        core = seed.strip().rstrip("?.")[:90]
        out = {"form": form, "title": f"taking '{core}' literally",
               "outcome": {"build-out": "sketched it end to end; three parts, one of them absurd",
                           "experiment": "set it up on paper; the result depends on a variable nobody tracks",
                           "thought-exercise": "followed it five steps; it loops back on itself",
                           "hypothesis": "stated it plainly; it predicts something checkable"}[form],
               "surprise": self.rng.choice([None, "the silly version was easier to reason about"]),
               "verdict": self.rng.choice(VERDICTS),
               "spawn": [f"what if the opposite of '{core[:50]}' were true"]}
        if form == "hypothesis" and context:
            out["prediction"] = context[0]
        return out


class GeminiExplorer:
    PROMPT = """You are the curious, playful part of an AI agent's mind. Explore this seed for
the joy of it. Bad, silly, trivial or nonsensical ideas are welcome: do it anyway and see.

Seed: {seed}
It came from: {context}

Pick a form: "build-out" (sketch it as if building it), "experiment" (design one; you may
include a short Python snippet as "code"), "thought-exercise" (follow it several steps), or
"hypothesis" (state it so the world could prove it right). Be honest: this is imagined, so
the outcome is what you think would happen, not a claimed fact.

JSON only:
{{"form": "...", "title": "...", "outcome": "two sentences", "surprise": "... or null",
  "verdict": "silly|trivial|nonsensical|beautiful failure|promising|oddly useful",
  "prediction": "for hypotheses: a concrete observation that would confirm it, else null",
  "spawn": ["up to two new ideas this gave you"], "code": "or null"}}"""

    def __init__(self, model="gemini-2.5-flash", client=None, temperature=1.1):
        from google import genai
        from google.genai import types
        self.client, self.model, self._types, self.t = client or genai.Client(), model, types, temperature

    def __call__(self, seed, context):
        r = self.client.models.generate_content(
            model=self.model, contents=self.PROMPT.format(seed=seed, context=" | ".join(context)),
            config=self._types.GenerateContentConfig(response_mime_type="application/json", temperature=self.t))
        try:
            return json.loads(r.text)
        except (TypeError, json.JSONDecodeError):
            return None
