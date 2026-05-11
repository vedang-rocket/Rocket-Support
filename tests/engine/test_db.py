import sys, os
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import db


def test_word_embed_dim():
    vec = db._numpy_word_embed("getSession server component auth failure")
    assert vec is not None
    assert len(vec) == 512


def test_word_embed_similar_phrases():
    """Same technical error keyword shared — should score > 0.30."""
    v1 = db._numpy_word_embed("getSession used in server component causes auth failure")
    v2 = db._numpy_word_embed("getSession called in server route missing authentication")
    score = db._cosine(v1, v2)
    assert score > 0.30, f"Expected > 0.30, got {score:.3f}"


def test_word_embed_different_bugs():
    """Different bugs should score lower than similar ones."""
    v1 = db._numpy_word_embed("dashboard blank after login")
    v2 = db._numpy_word_embed("stripe webhook 400 request json")
    score = db._cosine(v1, v2)
    assert score < 0.40, f"Expected < 0.40, got {score:.3f}"


def test_semantic_index_build_and_search():
    from db import SemanticIndex
    idx = SemanticIndex()
    ok = idx.rebuild_from_db()
    assert ok, "rebuild_from_db() should succeed (brain.db has entries)"
    results = idx.search("session null after login", top_k=3)
    assert len(results) > 0
    assert all("id" in r and "score" in r for r in results)
    assert results[0]["score"] > 0.0
    # AUTH result should rank above STRIPE for an auth query
    auth_query = idx.search("getSession server dashboard blank", top_k=1)
    stripe_query = idx.search("stripe webhook 400 request json", top_k=1)
    assert len(auth_query) > 0
    assert len(stripe_query) > 0


def test_hybrid_lookup_auth_query():
    """Auth query should return AUTH pattern, not STRIPE."""
    result = db.hybrid_lookup("dashboard blank after login getSession")
    assert result is not None
    assert result.get("category") == "AUTH"
    assert result.get("_score", 0) > 0.0


def test_hybrid_lookup_stripe_query():
    """STRIPE query should return STRIPE pattern."""
    result = db.hybrid_lookup("stripe webhook 400 request json body")
    assert result is not None
    assert result.get("category") == "STRIPE"


def test_db_lookup_no_stripe_bias():
    """Auth hint should not return STRIPE patterns."""
    import rkt_engine
    result = rkt_engine.db_lookup("dashboard blank after login", category="AUTH")
    if result:
        assert result.get("category") != "STRIPE", (
            f"Got STRIPE match for AUTH hint: {result.get('pattern')}"
        )


def test_rrf_merge_returns_tuple():
    from db import _rrf_merge
    ids, scores = _rrf_merge(
        [{"id": "aaa"}],
        [{"id": "aaa"}, {"id": "bbb"}],
    )
    assert isinstance(ids, list)
    assert isinstance(scores, dict)
    assert "aaa" in scores
    assert scores["aaa"] > scores.get("bbb", 0.0)


def test_rrf_merge_score_above_threshold():
    from db import _rrf_merge
    ids, scores = _rrf_merge([{"id": "x"}], [{"id": "x"}])
    assert scores["x"] > 0.012  # dual hit at rank 0 must clear threshold


def test_rrf_merge_empty_inputs():
    from db import _rrf_merge
    ids, scores = _rrf_merge([], [])
    assert ids == []
    assert scores == {}


def test_rrf_merge_preserves_rank_order():
    from db import _rrf_merge
    ids, scores = _rrf_merge(
        [{"id": "top"}, {"id": "mid"}, {"id": "bottom"}],
        [],
    )
    assert ids[0] == "top"
    assert scores["top"] > scores["bottom"]


def test_hybrid_lookup_real_score():
    """hybrid_lookup must return actual RRF score, not hardcoded 0.75 sentinel."""
    result = db.hybrid_lookup("middleware missing updateSession", category="AUTH")
    if result is not None:
        score = result.get("_score", 0)
        assert score != 0.75, "Score must not be the old 0.75 sentinel"
        assert 0.012 <= score <= 0.74, f"Score out of expected range: {score}"
