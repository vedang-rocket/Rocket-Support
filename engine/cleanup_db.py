"""
One-time cleanup: remove garbage entries and fix crossed error_signatures.
Safe to re-run (idempotent).

Usage: engine/.venv/bin/python engine/cleanup_db.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def cleanup():
    db.init_db()
    conn = db.get_conn()

    before = conn.execute("SELECT count(*) FROM fixes").fetchone()[0]
    conn.execute("DELETE FROM fixes WHERE pattern LIKE 'Manual fix:%'")
    after_delete = conn.execute("SELECT count(*) FROM fixes").fetchone()[0]
    print(f"Deleted {before - after_delete} 'Manual fix:' entries. Remaining: {after_delete}")

    # Fix crossed error_signatures
    # be38dc53: AUTH pattern (ROCKET RULE 1: getUser) has STRIPE error_sig
    conn.execute(
        "UPDATE fixes SET error_signature = ? WHERE id = ?",
        (
            "Not authenticated after login | dashboard blank | session null on server | "
            "getUser() vs getSession() | JWT not validated",
            "be38dc53f31131d6",
        ),
    )
    # 9196750b: getSession AUTH pattern has SUPABASE RLS error_sig
    conn.execute(
        "UPDATE fixes SET error_signature = ? WHERE id = ?",
        (
            "getSession() reads cookies without JWT validation | use getUser() in server components",
            "9196750b369166fa",
        ),
    )
    conn.commit()
    conn.close()
    print("Fixed 2 crossed error_signatures.")
    print("Cleanup complete.")


if __name__ == "__main__":
    cleanup()
