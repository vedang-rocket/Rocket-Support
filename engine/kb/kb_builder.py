"""
kb_builder.py — Fetch Rocket.new reference docs from GitHub raw markdown.

Saves to ~/rocket-support/kb/{name}.md + metadata.json.
Run directly: python kb_builder.py
Or via:       engine/kb/refresh.sh
"""

import os
import json
import datetime
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

KB_DIR = os.path.expanduser("~/rocket-support/kb")

SOURCES = {
    # Supabase — verified paths as of 2026-04
    "supabase_ssr":     "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/auth/server-side/creating-a-client.mdx",
    "supabase_rls":     "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/database/postgres/row-level-security.mdx",
    # Next.js — verified paths as of 2026-04 (docs restructured; middleware renamed to proxy)
    "nextjs_middleware": "https://raw.githubusercontent.com/vercel/next.js/canary/docs/01-app/03-api-reference/03-file-conventions/proxy.mdx",
    "nextjs_cookies":   "https://raw.githubusercontent.com/vercel/next.js/canary/docs/01-app/03-api-reference/04-functions/cookies.mdx",
    "nextjs_15_upgrade": "https://raw.githubusercontent.com/vercel/next.js/canary/docs/01-app/02-guides/upgrading/version-15.mdx",
    "flutter_supabase_quickstart": "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/getting-started/quickstarts/flutter.mdx",
    "flutter_supabase_v2_upgrade": "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/reference/dart/upgrade-guide.mdx",
    "flutter_supabase_auth": "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/getting-started/tutorials/with-flutter.mdx",
    "flutter_deep_links": "https://raw.githubusercontent.com/flutter/website/main/src/content/ui/navigation/deep-linking.md",
    "flutter_pubspec": "https://raw.githubusercontent.com/flutter/website/main/src/content/tools/pubspec.md",
}

# Fallback URLs if primary 404s
FALLBACKS = {
    "supabase_ssr":     "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/auth/server-side/advanced-guide.mdx",
    "supabase_rls":     "https://raw.githubusercontent.com/supabase/supabase/master/apps/docs/content/guides/auth/row-level-security.mdx",
    "nextjs_middleware": "https://raw.githubusercontent.com/vercel/next.js/canary/docs/01-app/03-api-reference/03-file-conventions/middleware.mdx",
    "nextjs_cookies":   "https://raw.githubusercontent.com/vercel/next.js/canary/docs/app/api-reference/functions/cookies.mdx",
    "nextjs_15_upgrade": "https://raw.githubusercontent.com/vercel/next.js/canary/docs/app/guides/upgrading/version-15.mdx",
}

HEADERS = {
    "User-Agent": "rocket-support-kb/1.0 (github.com/rocket-new support tooling)",
}


def fetch_one(name: str, url: str) -> tuple[bool, str, str]:
    """
    Fetch a single URL.
    Returns (success, final_url, content_or_error).
    Tries primary URL, then fallback if 404.
    """
    for attempt_url in [url, FALLBACKS.get(name)]:
        if not attempt_url:
            continue
        try:
            resp = requests.get(attempt_url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                return True, attempt_url, resp.text
            elif resp.status_code == 404:
                print(f"  404: {attempt_url}")
                continue
            else:
                print(f"  HTTP {resp.status_code}: {attempt_url}")
                return False, attempt_url, f"HTTP {resp.status_code}"
        except requests.Timeout:
            print(f"  TIMEOUT: {attempt_url}")
            return False, attempt_url, "timeout"
        except Exception as e:
            print(f"  ERROR: {attempt_url} — {e}")
            return False, attempt_url, str(e)

    return False, url, "404 on all URLs"


def _build_index(kb_dir: str):
    """
    Pre-build pure-Python BM25 index from all *.md files and save as JSON.
    No sklearn/numpy required. Loads in ~20ms at search time.
    """
    import re
    import math
    import glob as _glob

    STOPWORDS = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
        "is", "are", "was", "be", "with", "this", "that", "it", "as", "by",
        "from", "you", "can", "will", "your", "not", "if", "do", "use",
        "more", "all", "have", "has", "we", "i", "s", "t",
    }

    def tokenise(text):
        tokens = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
        bigrams = [tokens[i] + "_" + tokens[i + 1] for i in range(len(tokens) - 1)]
        return [t for t in tokens + bigrams if t not in STOPWORDS and len(t) > 1]

    def split_chunks(text, size=400, overlap=80):
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

    md_files = sorted(_glob.glob(os.path.join(kb_dir, "*.md")))
    if not md_files:
        return

    all_chunks = []
    for path in md_files:
        source = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception:
            continue
        for chunk in split_chunks(content):
            all_chunks.append({"source": source, "chunk": chunk})

    if not all_chunks:
        return

    N = len(all_chunks)

    # Document frequency
    df: dict = {}
    chunk_terms = []
    for c in all_chunks:
        tks = tokenise(c["chunk"])
        term_set = set(tks)
        chunk_terms.append(tks)
        for t in term_set:
            df[t] = df.get(t, 0) + 1

    # BM25 IDF
    idf = {t: math.log((N - d + 0.5) / (d + 0.5) + 1) for t, d in df.items()}

    # Per-chunk TF (top 60 terms per chunk to keep JSON small)
    tf_list = []
    for tks in chunk_terms:
        freq: dict = {}
        total = max(len(tks), 1)
        for t in tks:
            freq[t] = freq.get(t, 0) + 1
        tf_norm = {t: v / total for t, v in freq.items()}
        # Keep only top terms by TF-IDF weight (prune low-signal terms)
        scored = sorted(tf_norm.items(), key=lambda x: x[1] * idf.get(x[0], 0), reverse=True)
        tf_list.append(dict(scored[:60]))

    index = {"chunks": all_chunks, "idf": idf, "tf": tf_list}
    idx_path = os.path.join(kb_dir, "kb_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))  # compact JSON

    size_kb = os.path.getsize(idx_path) // 1024
    print(f"Index built: {len(all_chunks)} chunks, {size_kb}KB → {idx_path}")


def build():
    """Fetch all sources, save markdown, and pre-build search index."""
    os.makedirs(KB_DIR, exist_ok=True)

    metadata = {
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sources": {},
    }

    for name, primary_url in SOURCES.items():
        print(f"\n[{name}]")
        success, final_url, content = fetch_one(name, primary_url)

        if success:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            doc = f"# {name}\nSource: {final_url}\nFetched: {now}\n---\n{content}"
            out_path = os.path.join(KB_DIR, f"{name}.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(doc)

            size = len(content)
            print(f"  OK  {size:,} chars → {out_path}")
            print(f"  Preview: {content[:200].strip()!r}")

            metadata["sources"][name] = {
                "url": final_url,
                "fetched_at": now,
                "size_chars": size,
                "status": "ok",
            }
        else:
            print(f"  SKIP {name}: {content}")
            metadata["sources"][name] = {
                "url": primary_url,
                "status": "failed",
                "error": content,
            }

    meta_path = os.path.join(KB_DIR, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"\nMetadata saved → {meta_path}")

    ok = sum(1 for v in metadata["sources"].values() if v["status"] == "ok")
    print(f"\nDone: {ok}/{len(SOURCES)} sources fetched successfully.")

    print("\nBuilding search index...")
    _build_index(KB_DIR)

    return metadata


if __name__ == "__main__":
    build()
