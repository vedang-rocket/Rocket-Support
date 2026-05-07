"""
brain_fts.py — tantivy full-text index over brain.db fixes.

Stored at ~/.rocket-support/brain_fts/
Fields: category (raw), symptom (text), error_msg (text, exact), fix_summary (text)

Usage:
    from brain_fts import BrainFTS
    fts = BrainFTS()
    fts.rebuild_from_db()
    results = fts.search("PGRST301 permission denied", top_k=3)
    # returns [{id, category, score}, ...]
"""
import os
import sys
from typing import Any, Dict, List, Optional

DEFAULT_INDEX_PATH = os.path.expanduser("~/.rocket-support/brain_fts")

_tantivy_available = None


def _check_tantivy() -> bool:
    global _tantivy_available
    if _tantivy_available is None:
        try:
            import tantivy as _t  # noqa: F401
            _tantivy_available = True
        except ImportError:
            _tantivy_available = False
    return bool(_tantivy_available)


class BrainFTS:
    def __init__(self, index_path: str = DEFAULT_INDEX_PATH):
        self.index_path = index_path
        self._index = None
        self._writer = None

    def _build_schema(self):
        import tantivy
        builder = tantivy.SchemaBuilder()
        builder.add_integer_field("id", stored=True, indexed=True)
        builder.add_text_field("category", stored=True, tokenizer_name="raw")
        builder.add_text_field("symptom", stored=True, tokenizer_name="en_stem")
        builder.add_text_field("error_msg", stored=True, tokenizer_name="en_stem")
        builder.add_text_field("fix_summary", stored=True, tokenizer_name="en_stem")
        return builder.build()

    def _open_or_create(self):
        if self._index is not None:
            return
        if not _check_tantivy():
            return
        import tantivy
        os.makedirs(self.index_path, exist_ok=True)
        schema = self._build_schema()
        try:
            self._index = tantivy.Index(schema, path=self.index_path)
        except Exception:
            self._index = tantivy.Index(schema, path=self.index_path)

    def add_doc(self, row_id: int, category: str, symptom: str,
                error_msg: str, fix_summary: str) -> None:
        self._open_or_create()
        if self._index is None:
            return
        if self._writer is None:
            self._writer = self._index.writer()
        import tantivy
        doc = tantivy.Document(
            id=row_id,
            category=category or "",
            symptom=symptom or "",
            error_msg=error_msg or "",
            fix_summary=fix_summary or "",
        )
        self._writer.add_document(doc)

    def commit(self):
        if self._writer:
            self._writer.commit()
            self._writer = None
        if self._index:
            self._index.reload()

    def rebuild_from_db(self) -> int:
        """Rebuild full index from brain.db. Returns number of docs indexed."""
        if not _check_tantivy():
            return 0
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import db
        db.init_db()
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT id, pattern, error_signature, category, fix_diff FROM fixes"
        ).fetchall()
        conn.close()

        # Wipe and recreate index
        import shutil
        if os.path.exists(self.index_path):
            shutil.rmtree(self.index_path)
        self._index = None
        self._writer = None

        for i, row in enumerate(rows):
            self.add_doc(
                row_id=i,
                category=row["category"] or "",
                symptom=row["pattern"] or "",
                error_msg=row["error_signature"] or "",
                fix_summary=(row["fix_diff"] or "")[:200],
            )
        self.commit()
        return len(rows)

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """BM25 search. Returns [{id, category, score}, ...] sorted by score desc."""
        if not _check_tantivy():
            return []
        self._open_or_create()
        if self._index is None:
            return []
        try:
            searcher = self._index.searcher()
            query_obj = self._index.parse_query(
                query, ["symptom", "error_msg", "fix_summary"]
            )
            results = searcher.search(query_obj, top_k).hits
            out = []
            for score, addr in results:
                doc = searcher.doc(addr)
                try:
                    row_id = doc["id"][0]
                except (KeyError, IndexError, TypeError):
                    row_id = 0
                try:
                    category = doc["category"][0]
                except (KeyError, IndexError, TypeError):
                    category = ""
                out.append({"id": row_id, "category": category, "score": float(score)})
            return out
        except Exception:
            return []


_BRAIN_FTS: Optional["BrainFTS"] = None


def get_brain_fts() -> "BrainFTS":
    global _BRAIN_FTS
    if _BRAIN_FTS is None:
        _BRAIN_FTS = BrainFTS()
    return _BRAIN_FTS
