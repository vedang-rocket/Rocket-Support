import sys, os, tempfile
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import brain_fts


def test_tantivy_index_and_search():
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    idx.add_doc(1, "AUTH", "getSession server component auth failure",
                "Not authenticated after login", "Replace with getUser()")
    idx.add_doc(2, "STRIPE", "Stripe webhook 400 request.json",
                "Stripe webhook 400 No signatures", "Use request.text()")
    idx.commit()

    results = idx.search("getSession server", top_k=3)
    assert len(results) > 0
    assert results[0]["id"] == 1


def test_tantivy_error_code_match():
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    idx.add_doc(0, "SUPABASE", "RLS blocking SELECT", "PGRST301 permission denied", "Add SELECT policy")
    idx.add_doc(1, "AUTH", "getSession used", "session null", "use getUser")
    idx.commit()
    results = idx.search("PGRST301", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == 0


def test_rebuild_from_db():
    """BrainFTS rebuilds from real brain.db."""
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    count = idx.rebuild_from_db()
    assert count == 29, f"Expected 29 entries, got {count}"
    results = idx.search("getSession dashboard blank", top_k=3)
    assert len(results) > 0
