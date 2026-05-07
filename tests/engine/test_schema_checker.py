import sys, os, tempfile
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import schema_checker


def _make_migrations(sql: str) -> str:
    d = tempfile.mkdtemp()
    mdir = os.path.join(d, "supabase", "migrations")
    os.makedirs(mdir)
    with open(os.path.join(mdir, "001_init.sql"), "w") as f:
        f.write(sql)
    return d


def test_rls_insert_policy_missing():
    repo = _make_migrations(
        "ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY \"read\" ON profiles FOR SELECT USING (auth.uid() = id);\n"
    )
    results = schema_checker.check(repo)
    failures = schema_checker.failures(results)
    checks = [f["check"] for f in failures]
    assert "rls:insert_policy" in checks


def test_rls_insert_policy_present():
    repo = _make_migrations(
        "ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY \"insert\" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);\n"
    )
    results = schema_checker.check(repo)
    failures = schema_checker.failures(results)
    checks = [f["check"] for f in failures]
    assert "rls:insert_policy" not in checks
