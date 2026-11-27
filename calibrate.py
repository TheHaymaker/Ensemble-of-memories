"""Measure how well an embedder separates related from unrelated memories, and pick thresholds.

    python3 calibrate.py gemini        (needs GOOGLE_API_KEY)
    python3 calibrate.py model2vec     (pip install model2vec)
    python3 calibrate.py st            (pip install sentence-transformers)
    python3 calibrate.py spacy | keywords | concept

Prints AUC (1.0 = perfect separation, 0.5 = chance) and suggested recall_min / revive.
Add pairs from your own domain to PAIRS for a better fit.
"""
import sys

import numpy as np

from memory import keywords, overlap

# (stored memory, cue, related?)  Related cues mostly share no key words with the memory.
PAIRS = [
    ("The staging database password rotates on the first Monday of each month", "when do the preprod DB creds change?", 1),
    ("Deploys go out on Tuesday and Thursday only", "which days are we allowed to ship to prod?", 1),
    ("Refresh tokens must rotate on every use after the auth incident", "do session renewal tokens get reissued each time?", 1),
    ("The cafeteria closes early on Fridays", "is the canteen open late at the end of the week?", 1),
    ("Billing runs nightly at 2am UTC and retries failed charges three times", "how often do we re-attempt declined payments?", 1),
    ("We chose Postgres over DynamoDB for the orders service", "what datastore backs order processing?", 1),
    ("The on-call engineer must acknowledge pages within 15 minutes", "how fast do we need to respond to an alert?", 1),
    ("Feature flags older than 90 days are deleted in the quarterly cleanup", "when do stale toggles get removed?", 1),
    ("Customer PII must never be written to application logs", "can we print user emails in debug output?", 1),
    ("The vendor contract renews in March with a 5 percent price cap", "when is the supplier agreement up and is pricing limited?", 1),
    ("Load tests showed p95 latency doubles above 800 requests per second", "at what traffic level does response time degrade?", 1),
    ("New hires get production access only after security training", "when can a new engineer touch prod?", 1),
    # unrelated, often same domain (hard negatives)
    ("The staging database password rotates on the first Monday of each month", "which days are we allowed to ship to prod?", 0),
    ("Deploys go out on Tuesday and Thursday only", "is the canteen open late at the end of the week?", 0),
    ("Refresh tokens must rotate on every use after the auth incident", "what datastore backs order processing?", 0),
    ("The cafeteria closes early on Fridays", "how often do we re-attempt declined payments?", 0),
    ("Billing runs nightly at 2am UTC and retries failed charges three times", "when do the preprod DB creds change?", 0),
    ("We chose Postgres over DynamoDB for the orders service", "how fast do we need to respond to an alert?", 0),
    ("The on-call engineer must acknowledge pages within 15 minutes", "when do stale toggles get removed?", 0),
    ("Feature flags older than 90 days are deleted in the quarterly cleanup", "can we print user emails in debug output?", 0),
    ("Customer PII must never be written to application logs", "when is the supplier agreement up and is pricing limited?", 0),
    ("The vendor contract renews in March with a 5 percent price cap", "at what traffic level does response time degrade?", 0),
    ("Load tests showed p95 latency doubles above 800 requests per second", "when can a new engineer touch prod?", 0),
    ("New hires get production access only after security training", "do session renewal tokens get reissued each time?", 0),
]


def get_embedder(name):
    import embeddings as E
    return {"gemini": E.GeminiEmbedder, "model2vec": E.Model2VecEmbedder, "st": E.SentenceTransformerEmbedder,
            "spacy": E.SpacyEmbedder, "concept": E.ConceptEmbedder}[name]()


def similarities(name):
    mems, cues, labels = zip(*PAIRS)
    if name == "keywords":
        return np.array([overlap(keywords(m), keywords(c)) for m, c in zip(mems, cues)]), np.array(labels)
    emb = get_embedder(name)
    M, C = emb.encode(list(mems), "memory"), emb.encode(list(cues), "cue")
    return (M * C).sum(axis=1), np.array(labels)


def auc(s, y):
    pos, neg = s[y == 1], s[y == 0]
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum())
                 / (len(pos) * len(neg)))


def calibrate(name):
    s, y = similarities(name)
    cands = np.unique(s)
    best = max(cands, key=lambda t: ((s >= t) & (y == 1)).mean() + ((s < t) & (y == 0)).mean())
    acc = ((s >= best) == (y == 1)).mean()
    return {"embedder": name, "auc": round(auc(s, y), 3), "accuracy": round(float(acc), 3),
            "related": [round(float(x), 2) for x in np.percentile(s[y == 1], [10, 50, 90])],
            "unrelated": [round(float(x), 2) for x in np.percentile(s[y == 0], [10, 50, 90])],
            "recall_min": round(float(best), 3), "revive": round(float(best) * 0.9, 3)}


if __name__ == "__main__":
    for name in sys.argv[1:] or ["keywords"]:
        r = calibrate(name)
        print(f"{r['embedder']:10s} AUC {r['auc']:.3f}  accuracy {r['accuracy']:.0%}  "
              f"related p10/50/90 {r['related']}  unrelated {r['unrelated']}  "
              f"-> recall_min={r['recall_min']}, revive={r['revive']}")
