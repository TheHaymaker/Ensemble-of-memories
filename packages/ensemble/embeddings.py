"""Embedders for the memory store.

Every embedder has:
    name                 stored in the memory index; a store refuses a different embedder later
    encode(texts, kind)  -> float32 array (n, dim), rows unit-length.
                         kind is "memory" (stored text) or "cue" (a search), for models
                         that embed queries and documents differently.
    thresholds           {"recall_min": ..., "revive": ...} on cosine similarity.
                         Defaults are starting points: run calibrate.py to set them.

Adapters:
    GeminiEmbedder            Google's gemini-embedding-001 (needs GOOGLE_API_KEY or Vertex AI).
                              Uses RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY task types.
    Model2VecEmbedder         minishlab/potion-base-8M: local, ~30 MB, no GPU, very fast.
    SentenceTransformerEmbedder   e.g. all-MiniLM-L6-v2: local, needs torch.
    SpacyEmbedder             spaCy word vectors, averaged. Weak; a last resort.
"""
import re
import zlib

import numpy as np


def _unit(v):
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(n == 0, 1, n)


class GeminiEmbedder:
    def __init__(self, model="gemini-embedding-001", dim=768, client=None, thresholds=None):
        from google import genai
        from google.genai import types
        self._types = types
        self.client = client or genai.Client()       # reads GOOGLE_API_KEY, or Vertex AI env settings
        self.model, self.dim = model, dim
        self.name = f"gemini:{model}:{dim}"
        self.thresholds = thresholds or {"recall_min": 0.65, "revive": 0.55}

    def encode(self, texts, kind="memory"):
        task = "RETRIEVAL_DOCUMENT" if kind == "memory" else "RETRIEVAL_QUERY"
        out = []
        for i in range(0, len(texts), 100):
            r = self.client.models.embed_content(
                model=self.model, contents=texts[i:i + 100],
                config=self._types.EmbedContentConfig(task_type=task, output_dimensionality=self.dim))
            out += [e.values for e in r.embeddings]
        return _unit(out)


class Model2VecEmbedder:
    def __init__(self, model="minishlab/potion-base-8M", thresholds=None):
        from model2vec import StaticModel
        self.m = StaticModel.from_pretrained(model)
        self.name = f"model2vec:{model}"
        self.thresholds = thresholds or {"recall_min": 0.55, "revive": 0.45}

    def encode(self, texts, kind="memory"):
        return _unit(self.m.encode(list(texts)))


class SentenceTransformerEmbedder:
    def __init__(self, model="sentence-transformers/all-MiniLM-L6-v2", thresholds=None):
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer(model)
        self.name = f"st:{model}"
        self.thresholds = thresholds or {"recall_min": 0.5, "revive": 0.45}

    def encode(self, texts, kind="memory"):
        return _unit(self.m.encode(list(texts), normalize_embeddings=True))


class SpacyEmbedder:
    """Average of content-word vectors with the shared direction removed. Runs anywhere
    spaCy's en_core_web_md installs, but separates paraphrases poorly: see calibrate.py."""
    BACKGROUND = ["the team met to discuss the project", "we will fix the bug tomorrow",
                  "please review the document", "the meeting is at noon",
                  "update the config and restart the service", "customers reported an issue",
                  "the report is ready", "add tests for the new feature"]

    def __init__(self, model="en_core_web_md", thresholds=None):
        import spacy
        self.nlp = spacy.load(model, disable=["parser", "ner", "tagger", "attribute_ruler", "lemmatizer"])
        self.name = f"spacy:{model}"
        self.thresholds = thresholds or {"recall_min": 0.45, "revive": 0.4}
        b = self._avg(self.BACKGROUND)
        self.mu = b.mean(0)
        self.u = np.linalg.svd(b - self.mu)[2][0]

    def _avg(self, texts):
        out = []
        for d in self.nlp.pipe(texts):
            v = [t.vector for t in d if not t.is_stop and not t.is_punct and t.has_vector]
            out.append(np.mean(v, axis=0) if v else np.zeros(self.nlp.vocab.vectors_length))
        return np.array(out)

    def encode(self, texts, kind="memory"):
        v = self._avg(list(texts)) - self.mu
        v = v - np.outer(v @ self.u, self.u)
        return _unit(v)


class ConceptEmbedder:
    """Deterministic test embedder: words in the same concept group map to the same axis,
    so paraphrases with no shared words still match. For tests only."""
    GROUPS = [
        "password credential creds secret passphrase",
        "database db postgres sql datastore",
        "rotate rotates rotation change changed renew cycle",
        "staging preprod",
        "monday weekly month monthly schedule when",
        "deploy deploys ship release production prod",
        "tuesday thursday days weekday",
        "token tokens refresh session",
        "cafeteria canteen lunch food",
        "decided decision decide agreed",
        "audit audits compliance auditor",
        "small batch batched batches large",
        "daily nightly hourly",
        "printer printers jam jams",
    ]
    name = "test:concepts"
    thresholds = {"recall_min": 0.5, "revive": 0.45}

    def __init__(self):
        self.axis = {w: i for i, g in enumerate(self.GROUPS) for w in g.split()}
        self.dim = len(self.GROUPS) + 64

    def encode(self, texts, kind="memory"):
        out = np.zeros((len(texts), self.dim), np.float32)
        for r, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                if w in self.axis:
                    out[r, self.axis[w]] += 1
                elif len(w) > 3:
                    out[r, len(self.GROUPS) + zlib.crc32(w.encode()) % 64] += 0.3     # unknown words: small noise
        return _unit(out)
