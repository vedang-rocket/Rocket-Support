"""
One-time script: regenerate all brain.db embeddings with new 512-dim word n-gram method.
Run once after updating _embed() in db.py.

Usage: engine/.venv/bin/python engine/migrate_embeddings.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def migrate():
    db.init_db()
    conn = db.get_conn()
    rows = conn.execute("SELECT id, pattern, error_signature, category FROM fixes").fetchall()
    updated = 0
    vec = None
    for row in rows:
        text = f"{row['pattern']} {row['error_signature'] or ''} {row['category'] or ''}"
        vec = db._embed(text)
        if vec:
            conn.execute(
                "UPDATE fixes SET embedding = ? WHERE id = ?",
                (json.dumps(vec), row["id"])
            )
            updated += 1
    conn.commit()
    conn.close()
    print(f"Migrated {updated}/{len(rows)} embeddings to 512-dim word n-gram.")
    if vec:
        print(f"Embedding dim: {len(vec)}")


if __name__ == "__main__":
    migrate()
