"""Build passages for the stored corpus and run sample searches (M00_SEARCH, D-SRCH-7).

    uv run python scripts/search_check.py

Applies corpus migrations, builds passages for documents that have none (one
transaction per document), then prints passage statistics and the top hits for
a fixed set of queries. Writes logs/search_check_<YYYYMMDD-HHMMSS>.txt. Calls no
network service. Does not run while the nightly refresh holds data/refresh.lock.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.search.passages import MAX_CHARS, ensure_passages  # noqa: E402
from engine.search.query import QueryError, phrase, search  # noqa: E402
from engine.store.db import open_db  # noqa: E402

QUERIES = [
    ("risk factors (phrase)", phrase("risk factors"), {}),
    ("10b5-1 (domain term)", phrase("10b5-1"), {}),
    ("HBM3E (domain term)", phrase("HBM3E"), {}),
    ("HBM prefix", "hbm*", {}),
    ("guidance in EX-99.1", "outlook OR guidance", {"doc_types": ["EX-99.1"]}),
    ("expects revenue NEAR", "NEAR(expect* revenue, 5)", {"doc_types": ["EX-99.1"]}),
    ("supply in Item 1A only", "supply", {"sections": ["10-K Item 1A"]}),
    ("label filter syntax", 'label:"Item 1A" AND customer*', {}),
    ("purchase obligations", phrase("purchase obligations"), {}),
    ("remaining performance obligations", phrase("remaining performance obligations"), {}),
]


def main() -> int:
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: nightly refresh running; try again later.")
        return 1
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"search_check_{datetime.now():%Y%m%d-%H%M%S}.txt"
    corpus = open_db("corpus", ROOT / "data")
    lines: list[str] = []

    def out(s: str = "") -> None:
        lines.append(s)
        print(s)

    t0 = time.perf_counter()
    built = ensure_passages(corpus)
    out(f"passages built: {built} in {time.perf_counter() - t0:.1f}s")

    out("\n== Passages by document type ==")
    out(f"{'doc_type':<12}{'docs':>6}{'passages':>10}{'avg':>8}{'min':>7}{'max':>7}{'>max':>6}")
    for r in corpus.execute(
        "SELECT d.doc_type, count(DISTINCT d.doc_id) docs, count(*) n, "
        "avg(p.end_offset - p.start_offset) avg, min(p.end_offset - p.start_offset) mn, "
        "max(p.end_offset - p.start_offset) mx, "
        "sum(p.end_offset - p.start_offset > ?) over_max "
        "FROM passage p JOIN document d ON d.doc_id = p.doc_id GROUP BY d.doc_type ORDER BY n DESC",
        (MAX_CHARS,),
    ):
        out(
            f"{r['doc_type'] or '-':<12}{r['docs']:>6}{r['n']:>10}{r['avg']:>8.0f}"
            f"{r['mn']:>7}{r['mx']:>7}{r['over_max']:>6}"
        )
    missing = corpus.execute(
        "SELECT count(*) FROM document d WHERE NOT EXISTS "
        "(SELECT 1 FROM passage p WHERE p.doc_id = d.doc_id)"
    ).fetchone()[0]
    out(f"documents without passages: {missing}")

    for name, query, filters in QUERIES:
        out(f"\n== {name}: {query} {filters or ''} ==")
        t = time.perf_counter()
        try:
            hits = search(corpus, query, limit=5, **filters)
        except QueryError as e:
            out(f"QUERY ERROR: {e}")
            continue
        out(f"{len(hits)} shown, {1000 * (time.perf_counter() - t):.0f} ms")
        for h in hits:
            out(f"  {h.score:7.2f}  {h.cik}  {h.accession}  {h.doc_type}  {h.section}")
            out(f"           {h.snippet.replace(chr(10), ' ')[:240]}")

    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nLog written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
