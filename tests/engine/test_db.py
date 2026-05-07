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


def test_db_lookup_no_stripe_bias():
    """Auth hint should not return STRIPE patterns."""
    import rkt_engine
    result = rkt_engine.db_lookup("dashboard blank after login", category="AUTH")
    if result:
        assert result.get("category") != "STRIPE", (
            f"Got STRIPE match for AUTH hint: {result.get('pattern')}"
        )
