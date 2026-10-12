"""Official feeds (M02 part 7b): Federal Register, Congress.gov, USAspending, arXiv.

    uv run python scripts/run_official.py                 # live check: all four, ~3 min
    uv run python scripts/run_official.py --only arxiv    # one source (fedreg, congress,
                                                          # usaspending, arxiv)

No SEC requests. Federal Register ~1 request per active phrase (once a day), Congress.gov
≈ 100 requests on the first run (the current Congress's bill and summary lists, key
CONGRESS_API_KEY from .env, never logged), USAspending ≤ 15 companies a run (≈ 4–12
requests each, weekly), arXiv ≤ 15 monthly counts a run (3 s apart). Each source has its
own time slice. Writes logs/official_<time>.txt (summary only).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_news import companies  # noqa: E402

from engine.news.vendors import key_from_env  # noqa: E402
from engine.official.step import run_official_step  # noqa: E402
from engine.official.views import usd  # noqa: E402
from engine.store.db import open_db  # noqa: E402

SOURCES = ("fedreg", "congress", "usaspending", "arxiv")


def summary(engine) -> list[str]:
    lines = ["", "Stored per theme (Federal Register documents · bills · arXiv months counted):"]
    for r in engine.execute(
        "SELECT t.name, "
        "(SELECT count(*) FROM official_theme o WHERE o.theme_id = t.theme_id "
        " AND o.source = 'fedreg') fr, "
        "(SELECT count(*) FROM official_theme o WHERE o.theme_id = t.theme_id "
        " AND o.source = 'congress') bills "
        "FROM theme t WHERE t.status = 'active' ORDER BY t.name"
    ):
        lines.append(f"  {r['name']}: {r['fr']} · {r['bills']}")
    lines.append("Federal Register by type: " + ", ".join(
        f"{r['doc_type']} {r['n']}" for r in engine.execute(
            "SELECT doc_type, count(*) n FROM fedreg_doc GROUP BY doc_type ORDER BY n DESC")
    ))  # fmt: skip
    lines.append("Newest Federal Register matches (5):")
    for r in engine.execute(
        "SELECT d.publication_date, d.doc_type, d.title, o.phrase FROM fedreg_doc d "
        "JOIN official_theme o ON o.source = 'fedreg' AND o.ref = d.document_number "
        "ORDER BY d.publication_date DESC LIMIT 5"
    ):
        lines.append(
            f"  {r['publication_date']} {r['doc_type']}: {r['title'][:90]} [{r['phrase']}]"
        )
    lines.append("Bills: " + ", ".join(f"{r['status']} {r['n']}" for r in engine.execute(
        "SELECT status, count(*) n FROM congress_bill GROUP BY status")))  # fmt: skip
    for r in engine.execute(
        "SELECT b.bill_type, b.number, b.title, b.status, o.phrase FROM congress_bill b "
        "JOIN official_theme o ON o.source = 'congress' AND o.ref = b.bill_id "
        "ORDER BY b.status = 'enacted' DESC, b.latest_action_date DESC LIMIT 5"
    ):
        lines.append(f"  {r['bill_type']} {r['number']} ({r['status']}): {r['title'][:90]} "
                     f"[{r['phrase']}]")  # fmt: skip
    lines.append("arXiv, latest counted month (top 10 phrases):")
    for r in engine.execute(
        "SELECT phrase, month, n FROM arxiv_count WHERE month = (SELECT max(month) "
        "FROM arxiv_count) ORDER BY n DESC LIMIT 10"
    ):
        lines.append(f"  {r['month']} {r['phrase']}: {r['n']}")
    lines.append("USAspending per searched company (mapped awards · obligated · unmapped found):")
    for r in engine.execute(
        "SELECT a.searched_cik cik, coalesce((SELECT min(ticker) FROM ticker t WHERE "
        "t.cik = a.searched_cik AND t.valid_to IS NULL), a.searched_cik) tk, "
        "sum(p.cik = a.searched_cik) mapped, sum(CASE WHEN p.cik = a.searched_cik "
        "THEN a.amount END) total, sum(p.cik IS NULL OR p.cik != a.searched_cik) other "
        "FROM usa_award a LEFT JOIN usa_recipient p USING (recipient_id) "
        "GROUP BY a.searched_cik ORDER BY total DESC"
    ):
        lines.append(f"  {r['tk']}: {r['mapped']} · {usd(r['total'])} · {r['other']}")
    hows = engine.execute("SELECT how, count(*) n FROM usa_recipient GROUP BY how")
    lines.append("Recipients by mapping: " + ", ".join(f"{r['how']} {r['n']}" for r in hows))
    lines.append(
        "Unmapped recipient names (10 with the most awards; check for missed subsidiaries):"
    )
    for r in engine.execute(
        "SELECT p.name, p.parent_name, count(*) n FROM usa_award a JOIN usa_recipient p "
        "USING (recipient_id) WHERE p.how = 'none' GROUP BY p.recipient_id "
        "ORDER BY n DESC LIMIT 10"
    ):
        lines.append(f"  {r['name']} (parent: {r['parent_name'] or '—'}): {r['n']}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=SOURCES, help="run one source")
    args = parser.parse_args()
    os.chdir(ROOT)
    engine = open_db("engine")
    rep = run_official_step(engine, companies(engine), datetime.now(UTC),
                            congress_key=key_from_env("CONGRESS_API_KEY"),
                            sources=(args.only,) if args.only else SOURCES)  # fmt: skip
    text = "\n".join(rep.lines + summary(engine)) + "\n"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    out = logs / f"official_{datetime.now():%Y%m%d-%H%M%S}.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Report written to: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
