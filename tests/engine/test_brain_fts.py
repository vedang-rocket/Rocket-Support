import sys, os, tempfile, sqlite3
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import brain_fts


def test_tantivy_index_and_search():
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    idx.add_doc("abc001", "AUTH", "getSession server component auth failure",
                "Not authenticated after login", "Replace with getUser()")
    idx.add_doc("abc002", "STRIPE", "Stripe webhook 400 request.json",
                "Stripe webhook 400 No signatures", "Use request.text()")
    idx.commit()

    results = idx.search("getSession server", top_k=3)
    assert len(results) > 0
    assert results[0]["id"] == "abc001"


def test_tantivy_error_code_match():
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    idx.add_doc("rls001", "SUPABASE", "RLS blocking SELECT", "PGRST301 permission denied", "Add SELECT policy")
    idx.add_doc("auth001", "AUTH", "getSession used", "session null", "use getUser")
    idx.commit()
    results = idx.search("PGRST301", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "rls001"


def test_rebuild_from_db():
    """BrainFTS rebuilds from real brain.db — indexes all patterns, not just verified."""
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    count = idx.rebuild_from_db()
    db_path = os.path.expanduser("~/.rocket-support/brain.db")
    conn = sqlite3.connect(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM fixes").fetchone()[0]
    finally:
        conn.close()
    assert total > 0, "Expected at least one fix in brain.db"
    assert count == total, (
        f"Expected rebuild count to match all fixes ({total}), got {count}"
    )
    results = idx.search("getSession dashboard blank", top_k=3)
    assert len(results) > 0
