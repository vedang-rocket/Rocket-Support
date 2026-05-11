"""
Fix database — SQLite at ~/.rocket-support/brain.db
Vector embeddings via sentence-transformers (degrades gracefully without it).
Schema: fixes(id, pattern, error_signature, category, fix_diff, verified, uses, created_at, project_type, embedding)
"""

import sqlite3
import json
import os
import sys
import hashlib
import datetime
import subprocess
from typing import Optional, List, Dict, Any

import tracer as _tracer

DB_PATH = os.path.expanduser("~/.rocket-support/brain.db")


def _semantic_store_dir() -> str:
    preferred = os.path.expanduser("~/.rocket-support")
    try:
        os.makedirs(preferred, exist_ok=True)
        probe = os.path.join(preferred, ".idx_write_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return preferred
    except Exception:
        fallback = "/tmp/rocket-support"
        os.makedirs(fallback, exist_ok=True)
        return fallback

# Embedding strategy (in priority order):
#   1. sentence-transformers (best, requires torch — optional)
#   2. scikit-learn TF-IDF   (good, lightweight — installed)
#   3. keyword overlap        (fallback, always available)

_st_model = None
_st_available = None
_tfidf_vectorizer = None
_tfidf_corpus: List[str] = []
_tfidf_matrix = None


def _try_sentence_transformers(text: str) -> Optional[List[float]]:
    global _st_model, _st_available
    if _st_available is False:
        return None
    if _st_available is None:
        # Never import sentence_transformers on demand — loading PyTorch cold costs 8-15GB RSS.
        # Only reuse the model if it is already loaded elsewhere in this process.
        if "sentence_transformers" not in sys.modules:
            _st_available = False
            return None
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer("all-MiniLM-L6-v2")
            _st_available = True
        except Exception:
            _st_available = False
            return None
    vec = _st_model.encode(text, convert_to_numpy=True)
    return vec.tolist()


def _numpy_word_embed(text: str, n_features: int = 512) -> Optional[List[float]]:
    """
    Word unigram + bigram hashing into n_features buckets.
    Replaces char n-gram — captures 'getSession' as a token, not character fragments.
    Uses hashlib.md5 for deterministic hashing (Python's hash() is PYTHONHASHSEED-dependent).
    """
    try:
        import re as _re
        import numpy as np
        vec = np.zeros(n_features, dtype=float)
        tokens = _re.sub(r"[^\w]", " ", text.lower()).split()
        for tok in tokens:
            bucket = int(hashlib.md5(tok.encode()).hexdigest(), 16) % n_features
            vec[bucket] += 1.0
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            bucket = int(hashlib.md5(bigram.encode()).hexdigest(), 16) % n_features
            vec[bucket] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()
    except Exception:
        return None


def _embed(text: str) -> Optional[List[float]]:
    """Embed text. Tries sentence-transformers first, then word n-gram hashing."""
    st_vec = _try_sentence_transformers(text)
    if st_vec:
        return st_vec
    return _numpy_word_embed(text)


def _cosine(a: List[float], b: List[float]) -> float:
    try:
        import numpy as np
        va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        return float(np.dot(va, vb) / denom) if denom > 0 else 0.0
    except Exception:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


# ── Semantic index (usearch + TF-IDF LSA) ────────────────────────────────────

class SemanticIndex:
    """
    Semantic index using usearch ANN + _numpy_word_embed (no sklearn).
    Stored at ~/.rocket-support/brain.usearch + brain.idmap.pkl
    Falls back gracefully if usearch not available.
    """
    _STORE_DIR = _semantic_store_dir()
    INDEX_PATH = os.path.join(_STORE_DIR, "brain.usearch")
    ID_MAP_PATH = os.path.join(_STORE_DIR, "brain.idmap.pkl")
    DIM = 512  # matches _numpy_word_embed n_features

    def __init__(self):
        self._index = None
        self._id_map: List[Any] = []
        self._fallback_vectors = None

    def rebuild_from_db(self) -> bool:
        """Build usearch index from brain.db using numpy word embeddings (no sklearn)."""
        try:
            import numpy as np
            import pickle

            init_db()
            conn = get_conn()
            rows = _tracer.trace_db(
                conn,
                "SELECT id, pattern, error_signature, category FROM fixes",
            )
            conn.close()

            if not rows:
                # Ensure the index can be built in fresh environments.
                seed_builtin_fixes()
                conn = get_conn()
                rows = _tracer.trace_db(
                    conn,
                    "SELECT id, pattern, error_signature, category FROM fixes",
                )
                conn.close()
                if not rows:
                    return False

            self._id_map = []
            vectors = []
            for row in rows:
                text = f"{row['pattern']} {row['error_signature'] or ''} {row['category'] or ''}"
                vec = _numpy_word_embed(text, n_features=self.DIM)
                if vec:
                    vectors.append(np.array(vec, dtype=np.float32))
                    self._id_map.append(row["id"])

            if not vectors:
                return False

            dense = np.array(vectors, dtype=np.float32)
            norms = np.linalg.norm(dense, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            dense /= norms
            self._fallback_vectors = dense

            try:
                from usearch.index import Index
            except Exception:
                # Keep fallback vectors in memory when usearch isn't available.
                self._index = None
                return True

            if os.path.exists(self.INDEX_PATH):
                os.remove(self.INDEX_PATH)
            index = Index(ndim=self.DIM, metric="cos")
            ids = np.arange(len(vectors), dtype=np.uint64)
            index.add(ids, dense)
            index.save(self.INDEX_PATH)

            with open(self.ID_MAP_PATH, "wb") as f:
                pickle.dump(self._id_map, f)
            self._index = index
            return True
        except Exception:
            return False

    def _load(self) -> bool:
        try:
            import pickle
            from usearch.index import Index
            if not os.path.exists(self.ID_MAP_PATH):
                return False
            with open(self.ID_MAP_PATH, "rb") as f:
                self._id_map = pickle.load(f)
            # ndim mismatch (old 64-dim index) will raise — caught and triggers rebuild
            if not os.path.exists(self.INDEX_PATH):
                return False
            self._index = Index(ndim=self.DIM, metric="cos")
            self._index.load(self.INDEX_PATH)
            return True
        except Exception:
            return False

    def _embed_query(self, text: str):
        import numpy as np
        vec = _numpy_word_embed(text, n_features=self.DIM)
        if vec is None:
            return None
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr /= norm
        return arr

    def add(self, row_id: Any, text: str) -> None:
        """Add a single entry — triggers full rebuild for simplicity."""
        self.rebuild_from_db()

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Return list of {id, score} sorted by score desc."""
        if self._index is None:
            if not self._load():
                if not self.rebuild_from_db():
                    return []
        vec = self._embed_query(query)
        if vec is None:
            return []
        if self._index is None and self._fallback_vectors is not None:
            try:
                import numpy as np
                sims = self._fallback_vectors @ vec
                order = np.argsort(-sims)[:max(1, top_k)]
                return [
                    {"id": self._id_map[int(i)], "score": float(sims[int(i)])}
                    for i in order
                    if int(i) < len(self._id_map)
                ]
            except Exception:
                return []
        if self._index is None:
            return []
        try:
            matches = self._index.search(vec, top_k)
            results = []
            for pos, dist in zip(matches.keys, matches.distances):
                pos = int(pos)
                if pos < len(self._id_map):
                    results.append({"id": self._id_map[pos], "score": float(1.0 - dist)})
            return results
        except Exception:
            return []


_SEMANTIC_INDEX: Optional["SemanticIndex"] = None


def get_semantic_index() -> "SemanticIndex":
    global _SEMANTIC_INDEX
    if _SEMANTIC_INDEX is None:
        _SEMANTIC_INDEX = SemanticIndex()
    return _SEMANTIC_INDEX


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fixes (
            id           TEXT PRIMARY KEY,
            pattern      TEXT NOT NULL,
            error_signature TEXT,
            category     TEXT,
            fix_diff     TEXT,
            verified     INTEGER DEFAULT 0,
            uses         INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            project_type TEXT,
            embedding    TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_category ON fixes(category)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_type ON fixes(project_type)
    """)
    # Projects table — tracks every fingerprinted project
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id           TEXT PRIMARY KEY,
            repo_path    TEXT NOT NULL,
            repo_name    TEXT,
            project_type TEXT,
            confidence   REAL,
            framework    TEXT,
            next_version TEXT,
            has_supabase INTEGER,
            has_stripe   INTEGER,
            common_failure TEXT,
            category     TEXT,
            all_scores   TEXT,
            env_vars     TEXT,
            sql_files    INTEGER,
            first_seen   TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen    TEXT DEFAULT CURRENT_TIMESTAMP,
            setup_count  INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_type_name ON projects(project_type)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flutter_fixes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_id TEXT,
            error_signature TEXT,
            category TEXT,
            chain TEXT,
            file_pattern TEXT,
            fix_diff TEXT,
            fix_hint TEXT,
            verified BOOLEAN DEFAULT 0,
            uses INTEGER DEFAULT 1,
            project_type TEXT,
            flutter_version TEXT,
            supabase_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS diag_cache (
            cache_key  TEXT PRIMARY KEY,
            findings   TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _cache_key(repo_path: str) -> str:
    """Hash of repo_path + mtimes of key auth/stripe files."""
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    key_files = [
        "package.json",
        "middleware.ts",
        "lib/supabase/server.ts",
        "lib/supabase/middleware.ts",
        "app/api/webhooks/stripe/route.ts",
    ]
    parts = [repo_path]
    for rel in key_files:
        abs_p = os.path.join(repo_path, rel)
        try:
            parts.append(f"{rel}:{os.path.getmtime(abs_p):.0f}")
        except OSError:
            parts.append(f"{rel}:missing")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def get_cached_findings(repo_path: str, ttl_seconds: int = 3600) -> Optional[List[Any]]:
    """Return cached chain_walker findings or None if missing/stale."""
    init_db()
    key = _cache_key(repo_path)
    conn = get_conn()
    row = conn.execute(
        "SELECT findings, created_at FROM diag_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    age = (datetime.datetime.utcnow() - datetime.datetime.fromisoformat(row["created_at"])).total_seconds()
    if age > ttl_seconds:
        return None
    try:
        return json.loads(row["findings"])
    except Exception:
        return None


def set_cached_findings(repo_path: str, findings: List[Any]) -> None:
    """Store chain_walker findings in cache."""
    init_db()
    key = _cache_key(repo_path)
    now = datetime.datetime.utcnow().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO diag_cache (cache_key, findings, created_at) VALUES (?, ?, ?)",
        (key, json.dumps(findings), now),
    )
    conn.commit()
    conn.close()


def save_project_fingerprint(fp_result: Dict[str, Any]) -> str:
    """
    Save or update a project fingerprint in the projects table.
    Returns the project id.
    """
    init_db()
    import os as _os
    repo_path = fp_result.get("repo_path", "")
    repo_name = _os.path.basename(repo_path)
    proj_id = hashlib.sha256(repo_path.encode()).hexdigest()[:16]

    conn = get_conn()
    existing = conn.execute("SELECT id, setup_count FROM projects WHERE id = ?", (proj_id,)).fetchone()
    now = datetime.datetime.utcnow().isoformat()

    if existing:
        conn.execute(
            """UPDATE projects SET
               project_type=?, confidence=?, framework=?, next_version=?,
               has_supabase=?, has_stripe=?, common_failure=?, category=?,
               all_scores=?, env_vars=?, sql_files=?,
               last_seen=?, setup_count=setup_count+1
               WHERE id=?""",
            (
                fp_result.get("project_type"),
                fp_result.get("confidence"),
                fp_result.get("framework"),
                fp_result.get("next_version"),
                int(fp_result.get("has_supabase", False)),
                int(fp_result.get("has_stripe", False)),
                fp_result.get("common_failure"),
                fp_result.get("category"),
                json.dumps(fp_result.get("all_scores", {})),
                json.dumps({k: v for k, v in fp_result.get("env_vars", {}).items()}),
                fp_result.get("sql_files_found", 0),
                now,
                proj_id,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO projects
               (id, repo_path, repo_name, project_type, confidence, framework, next_version,
                has_supabase, has_stripe, common_failure, category, all_scores, env_vars,
                sql_files, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                proj_id,
                repo_path,
                repo_name,
                fp_result.get("project_type"),
                fp_result.get("confidence"),
                fp_result.get("framework"),
                fp_result.get("next_version"),
                int(fp_result.get("has_supabase", False)),
                int(fp_result.get("has_stripe", False)),
                fp_result.get("common_failure"),
                fp_result.get("category"),
                json.dumps(fp_result.get("all_scores", {})),
                json.dumps({k: v for k, v in fp_result.get("env_vars", {}).items()}),
                fp_result.get("sql_files_found", 0),
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()
    return proj_id


def get_project_history() -> List[Dict[str, Any]]:
    """Return all fingerprinted projects ordered by last seen."""
    init_db()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM projects ORDER BY last_seen DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _make_id(pattern: str) -> str:
    return hashlib.sha256(pattern.encode()).hexdigest()[:16]


def save_fix(
    pattern: str,
    error_signature: str,
    category: str,
    fix_diff: str,
    project_type: str,
    verified: int = 0,
) -> str:
    """Save or update a fix. Returns the fix id."""
    init_db()
    fix_id = _make_id(pattern)
    embedding_json = None
    vec = _embed(f"{pattern} {error_signature} {category}")
    if vec:
        embedding_json = json.dumps(vec)

    conn = get_conn()
    existing = conn.execute("SELECT id, uses FROM fixes WHERE id = ?", (fix_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE fixes SET uses = uses + 1, verified = MAX(verified, ?), fix_diff = ? WHERE id = ?",
            (verified, fix_diff, fix_id),
        )
    else:
        conn.execute(
            """INSERT INTO fixes
               (id, pattern, error_signature, category, fix_diff, verified, uses, created_at, project_type, embedding)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                fix_id,
                pattern,
                error_signature,
                category,
                fix_diff,
                verified,
                datetime.datetime.utcnow().isoformat(),
                project_type,
                embedding_json,
            ),
        )
    conn.commit()
    conn.close()
    # Rebuild semantic index in background after each new pattern
    try:
        import threading
        threading.Thread(target=get_semantic_index().rebuild_from_db, daemon=True).start()
    except Exception:
        pass
    # When a fix is verified, rebuild both semantic + FTS indexes in background.
    if verified == 1:
        try:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            rebuild_script = os.path.join(repo_root, "engine", "rebuild_indexes.sh")
            subprocess.Popen(
                [rebuild_script],
                cwd=repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    return fix_id


def find_similar(query: str, top_k: int = 3, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Find similar fixes using vector cosine similarity.
    Falls back to keyword matching if embeddings unavailable.
    """
    init_db()
    conn = get_conn()

    if category:
        rows = _tracer.trace_db(
            conn,
            "SELECT * FROM fixes WHERE category = ? ORDER BY uses DESC",
            (category,),
        )
    else:
        rows = _tracer.trace_db(conn, "SELECT * FROM fixes ORDER BY uses DESC")

    conn.close()

    if not rows:
        return []

    query_vec = _embed(query)

    results = []
    for row in rows:
        row_dict = dict(row)
        if query_vec and row_dict.get("embedding"):
            try:
                row_vec = json.loads(row_dict["embedding"])
                score = _cosine(query_vec, row_vec)
                row_dict["_score"] = score
            except Exception:
                row_dict["_score"] = 0.0
        else:
            # Fallback: keyword overlap score
            query_words = set(query.lower().split())
            pattern_words = set((row_dict.get("pattern", "") + " " + row_dict.get("error_signature", "")).lower().split())
            overlap = len(query_words & pattern_words)
            row_dict["_score"] = overlap / max(len(query_words), 1)

        results.append(row_dict)

    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:top_k]


def _rrf_merge(
    semantic_results: List[Dict[str, Any]],
    fts_results: List[Dict[str, Any]],
    k: int = 60,
) -> tuple:
    """
    Reciprocal Rank Fusion: merge semantic and FTS result lists.
    Both return hex fix IDs directly.
    Returns (sorted_ids[:3], scores_dict) so callers can threshold on real score.
    """
    scores: Dict[str, float] = {}

    for rank, item in enumerate(semantic_results):
        # Semantic: id is the hex fix_id string from SemanticIndex._id_map
        db_id = str(item["id"])
        scores[db_id] = scores.get(db_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, item in enumerate(fts_results):
        # FTS: id is now the hex fix_id string directly
        db_id = str(item["id"])
        scores[db_id] = scores.get(db_id, 0.0) + 1.0 / (k + rank + 1)

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:3]
    return sorted_ids, scores


def hybrid_lookup(query: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Hybrid search: run SemanticIndex + BrainFTS in parallel, merge with RRF.
    Falls back to find_similar() if either search system fails.
    Returns the top-1 fix dict or None.
    """
    if not query or not query.strip():
        return None

    semantic_results: List[Dict[str, Any]] = []
    fts_results: List[Dict[str, Any]] = []

    try:
        semantic_results = get_semantic_index().search(query, top_k=5)
    except Exception:
        pass

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from brain_fts import get_brain_fts
        fts = get_brain_fts()
        if fts._index is None:
            fts._open_or_create()  # load from persisted index dir first
        if fts._index is None:
            fts.rebuild_from_db()  # only rebuild if dir doesn't exist yet
        fts_results = fts.search(query, top_k=5)
    except Exception:
        pass

    if not semantic_results and not fts_results:
        # Both failed — fall back to word n-gram cosine
        results = find_similar(query, top_k=1, category=category)
        return results[0] if results and results[0].get("_score", 0) >= 0.15 else None

    merged_ids, rrf_scores = _rrf_merge(semantic_results, fts_results)

    init_db()
    conn = get_conn()
    for db_id in merged_ids:
        rows = _tracer.trace_db(conn, "SELECT * FROM fixes WHERE id = ?", (db_id,))
        row = rows[0] if rows else None
        if row is None:
            continue
        row_dict = dict(row)
        if category and row_dict.get("category") and row_dict["category"] != category:
            continue
        best_score = rrf_scores.get(db_id, 0.0)
        if best_score < 0.012:  # below minimum RRF threshold — no confident match
            conn.close()
            return None
        conn.close()
        row_dict["_score"] = min(best_score, 0.74)
        return row_dict
    conn.close()
    return None


def get_all_fixes() -> List[Dict[str, Any]]:
    """Return all fixes ordered by usage."""
    init_db()
    conn = get_conn()
    rows = conn.execute("SELECT * FROM fixes ORDER BY uses DESC, verified DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_flutter_fix(finding: Dict[str, Any], repo_path: str) -> int:
    init_db()
    conn = get_conn()
    pattern_id = finding.get("pattern_id", finding.get("chain", "unknown"))
    category = finding.get("category", finding.get("chain", "OTHER"))
    file_pattern = finding.get("file_pattern") or finding.get("file") or finding.get("broken_at", "")
    error_signature = finding.get("error_signature")
    if not error_signature:
        error_signature = f"{category}|{pattern_id}|{file_pattern}"
    existing = conn.execute(
        """SELECT id FROM flutter_fixes
           WHERE pattern_id = ? AND error_signature = ? AND file_pattern = ?""",
        (pattern_id, error_signature, file_pattern),
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE flutter_fixes
               SET uses = uses + 1,
                   fix_diff = COALESCE(?, fix_diff),
                   fix_hint = COALESCE(?, fix_hint),
                   category = COALESCE(?, category),
                   chain = COALESCE(?, chain)
               WHERE id = ?""",
            (
                finding.get("fix_diff"),
                finding.get("fix_hint"),
                category,
                finding.get("chain"),
                existing["id"],
            ),
        )
        row_id = int(existing["id"])
    else:
        cur = conn.execute(
            """INSERT INTO flutter_fixes
               (pattern_id, error_signature, category, chain, file_pattern, fix_diff, fix_hint,
                verified, uses, project_type, flutter_version, supabase_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                pattern_id,
                error_signature,
                category,
                finding.get("chain"),
                file_pattern,
                finding.get("fix_diff"),
                finding.get("fix_hint"),
                int(bool(finding.get("verified", 0))),
                finding.get("project_type", "Other"),
                finding.get("flutter_version"),
                finding.get("supabase_version"),
            ),
        )
        row_id = int(cur.lastrowid)

    conn.commit()
    conn.close()
    return row_id


def lookup_flutter_fix(findings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM flutter_fixes ORDER BY uses DESC").fetchall()]
    conn.close()
    if not rows or not findings:
        return None

    def _sig(f: Dict[str, Any]) -> str:
        category = f.get("category", f.get("chain", "OTHER"))
        pattern_id = f.get("pattern_id", f.get("chain", "unknown"))
        file_pattern = f.get("file_pattern") or f.get("file") or f.get("broken_at", "")
        return f"{category}|{pattern_id}|{file_pattern}"

    best = None
    best_score = 0.0
    for finding in findings:
        qsig = _sig(finding)
        q_words = set(qsig.lower().replace("|", " ").replace("/", " ").split())
        for row in rows:
            rsig = row.get("error_signature") or f"{row.get('category','')}|{row.get('pattern_id','')}|{row.get('file_pattern','')}"
            r_words = set(rsig.lower().replace("|", " ").replace("/", " ").split())
            overlap = len(q_words & r_words)
            score = overlap / max(len(q_words | r_words), 1)
            if score > best_score:
                best_score = score
                best = row
    if best and best_score > 0.60:
        best["_score"] = best_score
        return best
    return None


def seed_builtin_fixes():
    """Seed the database with the 10 known Rocket.new hard-rule fixes."""
    fixes = [
        {
            "pattern": "getSession() in server code",
            "error_signature": "Not authenticated after login | dashboard blank | session null on server",
            "category": "AUTH",
            "project_type": "SaaS",
            "fix_diff": """--- a/lib/supabase/server.ts
+++ b/lib/supabase/server.ts
-  const { data: { session } } = await supabase.auth.getSession()
-  if (!session) redirect('/login')
+  const { data: { user }, error } = await supabase.auth.getUser()
+  if (error || !user) redirect('/login')""",
            "verified": 1,
        },
        {
            "pattern": "request.json() in Stripe webhook handler",
            "error_signature": "Stripe webhook 400 | No signatures found | webhook secret fails | constructEvent error",
            "category": "STRIPE",
            "project_type": "SaaS",
            "fix_diff": """--- a/app/api/webhooks/stripe/route.ts
+++ b/app/api/webhooks/stripe/route.ts
-  const body = await request.json()
+  const body = await request.text()""",
            "verified": 1,
        },
        {
            "pattern": "middleware.ts in /app directory",
            "error_signature": "OAuth redirect loop | middleware not running | auth redirect not firing",
            "category": "AUTH",
            "project_type": "SaaS",
            "fix_diff": "Move middleware.ts from app/middleware.ts to middleware.ts (project root)",
            "verified": 1,
        },
        {
            "pattern": "@supabase/auth-helpers-nextjs import",
            "error_signature": "createClientComponentClient is not a function | auth-helpers deprecated | type errors",
            "category": "SUPABASE",
            "project_type": "SaaS",
            "fix_diff": """--- a/lib/supabase/client.ts
+++ b/lib/supabase/client.ts
-import { createClientComponentClient } from '@supabase/auth-helpers-nextjs'
+import { createBrowserClient } from '@supabase/ssr'
-export const supabase = createClientComponentClient()
+export const supabase = createBrowserClient(
+  process.env.NEXT_PUBLIC_SUPABASE_URL!,
+  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
+)""",
            "verified": 1,
        },
        {
            "pattern": "cookies() without await in Next.js 15",
            "error_signature": "cookies() should be awaited | cookies is not a function | TypeError: cookieStore.getAll is not a function",
            "category": "AUTH",
            "project_type": "SaaS",
            "fix_diff": """--- a/lib/supabase/server.ts
+++ b/lib/supabase/server.ts
-  const cookieStore = cookies()
+  const cookieStore = await cookies()""",
            "verified": 1,
        },
        {
            "pattern": "NEXT_PUBLIC_ prefix on service role key",
            "error_signature": "RLS bypass | unauthorized data access | service_role key exposed",
            "category": "ENV",
            "project_type": "SaaS",
            "fix_diff": """--- a/.env.local
+++ a/.env.local
-NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY=eyJ...
+SUPABASE_SERVICE_ROLE_KEY=eyJ...""",
            "verified": 1,
        },
        {
            "pattern": "Missing RLS policy on table",
            "error_signature": "empty array from Supabase | data not showing | [] returned for authenticated user",
            "category": "SUPABASE",
            "project_type": "SaaS",
            "fix_diff": """-- Run in Supabase SQL editor
ALTER TABLE your_table ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own data" ON your_table FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users insert own data" ON your_table FOR INSERT WITH CHECK (auth.uid() = user_id);""",
            "verified": 1,
        },
        {
            "pattern": "Missing profile trigger on_auth_user_created",
            "error_signature": "dashboard blank after signup | profile null | foreign key violation on profiles",
            "category": "SUPABASE",
            "project_type": "SaaS",
            "fix_diff": """-- Run in Supabase SQL editor
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email), NEW.raw_user_meta_data->>'avatar_url');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();""",
            "verified": 1,
        },
        {
            "pattern": "Landing page RLS blocking INSERT on leads table",
            "error_signature": "contact form not saving | leads empty | 403 on insert | new row violates RLS",
            "category": "SUPABASE",
            "project_type": "Landing",
            "fix_diff": """-- Run in Supabase SQL editor
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
-- Allow anonymous inserts (contact form, newsletter signup)
CREATE POLICY "Anyone can submit lead" ON leads FOR INSERT WITH CHECK (true);
-- Only authenticated users (admins) can read leads
CREATE POLICY "Authenticated users read leads" ON leads FOR SELECT USING (auth.role() = 'authenticated');""",
            "verified": 1,
        },
        {
            "pattern": "Redirect URL not configured in Supabase Auth",
            "error_signature": "works locally broken on deploy | redirect_uri mismatch | OAuth error on production",
            "category": "AUTH",
            "project_type": "SaaS",
            "fix_diff": "In Supabase Dashboard → Authentication → URL Configuration → Add your deployed URL (https://yourapp.netlify.app) to Redirect URLs",
            "verified": 1,
        },
        {
            "pattern": "CSP headers missing in next.config — preview issues / scripts blocked",
            "error_signature": "preview broken | Refused to load script | connect-src blocked | CSP violation | Content-Security-Policy | wss supabase blocked | googletagmanager blocked | static.rocket.new blocked",
            "category": "BUILD",
            "project_type": "SaaS",
            "fix_diff": """--- a/next.config.ts
+++ b/next.config.ts
+const securityHeaders = [
+  {
+    key: 'Content-Security-Policy',
+    value: [
+      "default-src 'self'",
+      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new",
+      "script-src-elem 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new",
+      "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com https://bws.bioid.com https://*.bioid.com https://api.tryterra.co https://appanalytics.rocket.new",
+      "img-src 'self' data: blob: https:",
+      "font-src 'self' https://fonts.gstatic.com",
+      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
+    ].join('; '),
+  },
+]
 const nextConfig = {
+  async headers() {
+    return [{ source: '/(.*)', headers: securityHeaders }]
+  },
 }""",
            "verified": 1,
        },
    ]

    for f in fixes:
        save_fix(
            pattern=f["pattern"],
            error_signature=f["error_signature"],
            category=f["category"],
            fix_diff=f["fix_diff"],
            project_type=f["project_type"],
            verified=f["verified"],
        )


if __name__ == "__main__":
    print("Seeding fix database...")
    seed_builtin_fixes()
    fixes = get_all_fixes()
    print(f"Database seeded with {len(fixes)} fixes at {DB_PATH}")
    for f in fixes:
        print(f"  [{f['category']}] {f['pattern'][:60]}")
