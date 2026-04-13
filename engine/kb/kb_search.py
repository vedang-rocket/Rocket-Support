"""
kb_search.py — Fast BM25-lite search over ~/rocket-support/kb/*.md files.

Pure Python stdlib only (re, math, json) — NO sklearn, NO numpy, NO torch.
Load time: ~20ms (reads pre-built JSON index from kb_builder.py).
Query time: ~1ms.
Target: < 50ms total including first load.

Index format (kb_index.json produced by kb_builder.py):
  {
    "chunks": [{"source": str, "chunk": str}, ...],
    "idf":    {term: float, ...},        # log IDF for each term
    "tf":     [[term_freq_dict], ...]    # per-chunk TF (sparse, top terms only)
  }
"""

import os
import re
import json
import math
import glob
import time
from typing import List, Dict, Optional

KB_DIR = os.path.expanduser("~/rocket-support/kb")

# Module-level cache
_chunks: List[Dict] = []
_idf: Dict[str, float] = {}
_tf: List[Dict[str, float]] = []
_loaded = False


# ── Tokeniser ─────────────────────────────────────────────────────────────────

def _tokenise(text: str) -> List[str]:
    """Lowercase alphanumeric tokens + common tech bigrams."""
    tokens = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    # Add bigrams for key tech pairs (e.g. "row_level" → "row level")
    bigrams = [tokens[i] + "_" + tokens[i + 1] for i in range(len(tokens) - 1)]
    return tokens + bigrams


_STOPWORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
    "is", "are", "was", "be", "with", "this", "that", "it", "as", "by",
    "from", "you", "can", "will", "your", "not", "if", "do", "use",
    "more", "all", "have", "has", "we", "i", "s", "t",
}


def _terms(text: str) -> List[str]:
    return [t for t in _tokenise(text) if t not in _STOPWORDS and len(t) > 1]


# ── Chunk splitter (same as kb_builder) ──────────────────────────────────────

def _split_chunks(text: str, size: int = 400, overlap: int = 80) -> List[str]:
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    chunks = []
    pos = 0
    while pos < len(text):
        end = min(pos + size, len(text))
        snap = text.rfind('\n\n', pos + size - overlap, end)
        if snap != -1:
            end = snap
        elif end < len(text):
            snap = text.rfind('\n', pos + size - overlap, end)
            if snap != -1:
                end = snap
        chunk = text[pos:end].strip()
        if chunk:
            chunks.append(chunk)
        next_pos = end - overlap
        if next_pos <= pos:
            next_pos = pos + max(size - overlap, 1)
        pos = next_pos
    return chunks


# ── Load ──────────────────────────────────────────────────────────────────────

def _load():
    """Load pre-built JSON index. Falls back to building from .md files."""
    global _chunks, _idf, _tf, _loaded

    if _loaded:
        return

    idx_path = os.path.join(KB_DIR, "kb_index.json")
    if os.path.exists(idx_path):
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            _chunks = index["chunks"]
            _idf    = index["idf"]
            _tf     = index["tf"]
            _loaded = True
            return
        except Exception:
            pass  # fall through to rebuild

    # Slow path: build from .md files on the fly
    _build_from_mds()
    _loaded = True


def _build_from_mds():
    """Build in-memory BM25 index from .md files (no sklearn needed)."""
    global _chunks, _idf, _tf

    md_files = sorted(glob.glob(os.path.join(KB_DIR, "*.md")))
    all_chunks = []
    for path in md_files:
        source = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            continue
        for chunk in _split_chunks(content):
            all_chunks.append({"source": source, "chunk": chunk})

    _chunks = all_chunks
    if not all_chunks:
        return

    N = len(all_chunks)
    # Count document frequency per term
    df: Dict[str, int] = {}
    chunk_terms = []
    for c in all_chunks:
        tks = _terms(c["chunk"])
        term_set = set(tks)
        chunk_terms.append(tks)
        for t in term_set:
            df[t] = df.get(t, 0) + 1

    # IDF = log((N - df + 0.5) / (df + 0.5) + 1)  [BM25 IDF]
    idf = {}
    for t, d in df.items():
        idf[t] = math.log((N - d + 0.5) / (d + 0.5) + 1)

    # TF per chunk (raw frequency normalised by chunk length)
    tf_list = []
    for tks in chunk_terms:
        freq: Dict[str, float] = {}
        total = max(len(tks), 1)
        for t in tks:
            freq[t] = freq.get(t, 0) + 1
        tf_list.append({t: v / total for t, v in freq.items()})

    _idf = idf
    _tf  = tf_list


# ── Search ────────────────────────────────────────────────────────────────────

def search(query: str, top_k: int = 2) -> List[Dict]:
    """
    Search KB for chunks relevant to query using TF-IDF cosine similarity.
    Returns list of {source, chunk, score} dicts, best first.
    """
    _load()

    if not _chunks:
        return []

    q_terms = _terms(query)
    if not q_terms:
        return []

    # Query TF-IDF vector (unit norm)
    q_freq: Dict[str, float] = {}
    for t in q_terms:
        q_freq[t] = q_freq.get(t, 0) + 1
    q_total = max(len(q_terms), 1)

    q_vec: Dict[str, float] = {}
    for t, f in q_freq.items():
        if t in _idf:
            q_vec[t] = (f / q_total) * _idf[t]

    if not q_vec:
        return []

    # Normalise query vector
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

    # Score each chunk via cosine similarity
    scores = []
    for i, chunk_tf in enumerate(_tf):
        dot = 0.0
        for t, qv in q_vec.items():
            if t in chunk_tf:
                dot += qv * chunk_tf[t] * _idf.get(t, 0)
        if dot > 0:
            chunk_norm = math.sqrt(
                sum((v * _idf.get(t, 0)) ** 2 for t, v in chunk_tf.items())
            ) or 1.0
            scores.append((dot / (q_norm * chunk_norm), i))

    scores.sort(reverse=True)

    return [
        {
            "source": _chunks[i]["source"],
            "chunk":  _chunks[i]["chunk"],
            "score":  round(s, 4),
        }
        for s, i in scores[:top_k]
        if s > 0.001
    ]


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "supabase auth middleware cookies"

    t0 = time.perf_counter()
    hits = search(query, top_k=2)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"kb_search  query={query!r}  {elapsed:.1f}ms  {len(_chunks)} chunks indexed")

    if hits:
        for i, hit in enumerate(hits, 1):
            print(f"\n[{i}] source={hit['source']}  score={hit['score']:.4f}")
            print(f"    {hit['chunk'][:300]}")
    else:
        print("No results — run kb_builder.py first to populate the KB.")
