"""Scan stored earnings releases into the R19 guidance ledger and report (M00_SEARCH D-SRCH-11).

    uv run python scripts/run_guidance.py            # releases not yet scanned by this parser
    uv run python scripts/run_guidance.py --force    # re-scan every release

Code only (no LLM, no network). Writes engine.db (guidance, guidance_scan,
review_queue) and logs/guidance_<YYYYMMDD-HHMMSS>.txt listing, per company and
release, the parsed items and every sentence sent to the review queue.
Does not run while the nightly refresh holds data/refresh.lock.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.guidance.ledger import REVIEW_KINDS, scan_all  # noqa: E402
from engine.store.db import open_db  # noqa: E402


def fmt(v: float | int | None, unit: str) -> str:
    if v is None:
        return "-"
    d = Decimal(str(v))
    if unit == "USD" and abs(d) >= 10**6:
        return f"${d / 10**9:,.3f}B" if abs(d) >= 10**9 else f"${d / 10**6:,.1f}M"
    if unit == "USD":
        return f"${d}"
    if unit == "count":
        return f"{d / 10**6:,.1f}M"
    return f"{d}%"


def main() -> int:
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: nightly refresh running; try again later.")
        return 1
    force = "--force" in sys.argv[1:]
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"guidance_{datetime.now():%Y%m%d-%H%M%S}.txt"
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")

    results = scan_all(engine, corpus, datetime.now(UTC), force=force)
    names = {r["cik"]: r["name"] for r in engine.execute("SELECT cik, name FROM entity")}
    lines = [f"scanned {len(results)} releases (force={force})"]
    totals: dict[str, int] = {}
    for r in results:
        totals[r.outcome] = totals.get(r.outcome, 0) + 1
    lines.append(f"outcomes: {totals}")

    marks = ", ".join("?" * len(REVIEW_KINDS))
    for res in results:
        rel = res.release
        lines.append(
            f"\n## {names.get(rel.cik, rel.cik)}  {rel.accession}  filed {rel.filed}  "
            f"{res.outcome}: {res.items} items, {res.unparsed} unparsed, "
            f"{res.conflicts} conflicts, {res.candidates} candidates"
        )
        for g in engine.execute(
            "SELECT * FROM guidance WHERE accession = ? AND filename = ? "
            "ORDER BY period, metric, basis",
            (rel.accession, rel.filename),
        ):
            value = (
                fmt(g["low"], g["unit"])
                if g["low"] == g["high"]
                else f"{fmt(g['low'], g['unit'])} – {fmt(g['high'], g['unit'])}"
            )
            prior = (
                f"  prior {fmt(g['prior_low'], g['unit'])} – {fmt(g['prior_high'], g['unit'])}"
                if g["prior_low"] is not None
                else ""
            )
            lines.append(
                f"  {g['period']:<17}{g['metric']:<20}{g['basis']:<12}{g['kind']:<10}"
                f"{value}{prior}  [{g['source']} @{g['quote_start']}, "
                f'period "{g["period_quote"]}"]'
            )
        for q in engine.execute(
            f"SELECT kind, reason, payload FROM review_queue WHERE resolved_at IS NULL "
            f"AND kind IN ({marks}) AND json_extract(payload, '$.accession') = ? "
            "AND json_extract(payload, '$.filename') = ?",
            (*REVIEW_KINDS, rel.accession, rel.filename),
        ):
            p = json.loads(q["payload"])
            body = p.get("text") or f"kept: {p.get('kept')} | other: {p.get('other')}"
            lines.append(f"  REVIEW {q['kind']}: {q['reason']}")
            lines.append(f"    {' '.join(body.split())[:500]}")

    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:2]))
    print(f"Log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
