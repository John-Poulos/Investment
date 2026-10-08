"""Print guidance-like lines from each company's latest earnings release (R19 parser design).

    uv run python scripts/guidance_samples.py

For every company with a stored EX-99.1, takes the latest release (by filing
date) and its top passages for outlook/guidance wording, and prints only lines
with numbers or guidance words (plus the line before each), to keep the log
small. Writes logs/guidance_samples_<YYYYMMDD-HHMMSS>.txt. Read-only; no network.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.search.query import get_passage, search  # noqa: E402
from engine.store.db import open_db  # noqa: E402

QUERY = (
    'outlook OR guidance OR NEAR(expect* revenue, 8) OR NEAR(expect* "gross margin", 8) '
    "OR NEAR(anticipat* revenue, 8)"
)
KEEP = re.compile(
    r"\d|outlook|guidance|expect|anticipat|forecast|range|approximately|quarter|fiscal",
    re.IGNORECASE,
)
PASSAGES_PER_RELEASE = 3


def main() -> int:
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"guidance_samples_{datetime.now():%Y%m%d-%H%M%S}.txt"
    corpus = open_db("corpus", ROOT / "data")
    engine = open_db("engine", ROOT / "data")
    lines: list[str] = []

    releases = corpus.execute(
        "SELECT DISTINCT cik, accession FROM document WHERE doc_type = 'EX-99.1'"
    ).fetchall()
    filed = {
        r["accession"]: r["filed"]
        for r in engine.execute("SELECT accession, filed FROM filing WHERE form LIKE '8-K%'")
    }
    names = {r["cik"]: r["name"] for r in engine.execute("SELECT cik, name FROM entity")}
    latest: dict[str, str] = {}
    for r in releases:
        a = r["accession"]
        if r["cik"] not in latest or filed.get(a, "") > filed.get(latest[r["cik"]], ""):
            latest[r["cik"]] = a

    for cik, accession in sorted(latest.items()):
        name = names.get(cik, "?")
        lines.append(f"\n#### {cik} {name}  {accession}  filed {filed.get(accession)}")
        hits = search(corpus, QUERY, accessions=[accession], limit=PASSAGES_PER_RELEASE)
        if not hits:
            lines.append("(no guidance-like passages)")
        for h in sorted(hits, key=lambda h: h.start):
            p = get_passage(corpus, h.passage_id)
            assert p is not None
            lines.append(f"--- passage {p.passage_id} [{p.start}:{p.end}]")
            text_lines = p.text.split("\n")
            kept: set[int] = set()
            for i, line in enumerate(text_lines):
                if line.strip() and KEEP.search(line):
                    kept.update({i - 1, i} if i else {i})
            last = -2
            for i in sorted(kept):
                if text_lines[i].strip():
                    if i != last + 1:
                        lines.append("  ...")
                    lines.append("  " + text_lines[i].replace("\t", " | ")[:400])
                    last = i

    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(latest)} companies; log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
