"""Earnings-release exhibits for M04 (Part 7a; D-M04-42, S5.5–S5.7, S16).

- **EX-99.2:** many companies put the shareholder letter or CFO commentary (unit KPIs,
  credits, segment detail) in a second exhibit beside the EX-99.1 release. For every core
  and promoted company the last 4 earnings 8-Ks (Item 2.02) are checked once: the filing
  index is usually cached already (M02 fetched it for EX-99.1), so a listed EX-99.2 costs
  one request; ≤ 60 a year for 15 companies.
- **Release tables** (Invitae, S16): a company-stated "Non-GAAP gross profit" row and the
  release's revenue row, current and prior-year columns of the same release, stored as
  `non_gaap` rows. The non-GAAP margin and its year-over-year change are computed on the
  release's own pair, never across releases (a later release may restate the prior year).
- **Episode companies outside the watchlist** (Invitae 2020–22): their earnings 8-Ks are
  listed from submissions and only EX-99.1 is fetched (index + exhibit per filing).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.financials import units
from engine.sec.client import SecClient, iso
from engine.sec.documents import ingest_filing
from engine.sec.results import Failed, Ok
from engine.sec.submissions import earnings_releases, sync_filings

EX992 = "EX-99.2"
RELEASES = 4
STATE = "ex992:"  # refresh_state: the filing's index was checked for EX-99.2
EXTRACTOR = "release-table-1"


@dataclass
class ExhibitPass:
    checked: int = 0
    found: int = 0
    stored: int = 0
    failed: list[str] | None = None
    throttled: bool = False


def ex992_due(engine: sqlite3.Connection, cik: str, *, releases: int = RELEASES) -> list:
    """The company's last `releases` earnings 8-Ks not yet checked for EX-99.2."""
    out = []
    for f in earnings_releases(engine, cik)[:releases]:
        done = engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (STATE + f.accession,)
        ).fetchone()
        if done is None:
            out.append(f)
    return out


def fetch_ex992(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    cik: str,
    now: datetime,
    *,
    releases: int = RELEASES,
    filings: list | None = None,
) -> ExhibitPass:
    """Check the last earnings 8-Ks for an EX-99.2 and store it (index cached; 1 request
    per exhibit). A filing without one is recorded so it is not checked again."""
    res = ExhibitPass(failed=[])
    for f in filings if filings is not None else ex992_due(engine, cik, releases=releases):
        got = ingest_filing(client, corpus, f, now, types=(EX992,))
        res.checked += 1
        if not isinstance(got, Ok):
            res.failed.append(f"{f.accession}: {getattr(got, 'reason', got)}")
            if isinstance(got, Failed) and got.throttled:
                res.throttled = True
                break
            continue
        docs = got.data
        res.found += bool(docs.stored)
        res.stored += sum(1 for d in docs.stored if d.new)
        if docs.failed:
            res.failed += [f"{f.accession}: {x}" for x in docs.failed]
            continue
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (name) DO UPDATE SET fetched_at = excluded.fetched_at, "
            "detail = excluded.detail",
            (
                STATE + f.accession,
                got.source_ref,
                iso(now),
                '{"found": %s}' % ("true" if docs.stored else "false"),
            ),
        )
    return res


def fetch_episode_releases(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    cik: str,
    since: str,
    until: str,
    now: datetime,
) -> tuple[int, int, list[str]]:
    """EX-99.1 of a non-covered company's earnings 8-Ks filed in [since, until] (Invitae
    2020–22). Lists filings from submissions when none are stored. → (filings, new docs,
    problems)."""
    problems: list[str] = []
    have = [f for f in earnings_releases(engine, cik) if since <= f.filed <= until]
    if not have:
        s = sync_filings(client, engine, cik, now)
        if not isinstance(s, Ok):
            return 0, 0, [f"submissions: {getattr(s, 'reason', s)}"]
        have = [f for f in earnings_releases(engine, cik) if since <= f.filed <= until]
    new = 0
    for f in sorted(have, key=lambda f: f.filed):
        got = ingest_filing(client, corpus, f, now, types=("EX-99.1",))
        if not isinstance(got, Ok):
            problems.append(f"{f.accession}: {getattr(got, 'reason', got)}")
            if isinstance(got, Failed) and got.throttled:
                problems.append("SEC throttle: the rest waits for the next run")
                break
            continue
        new += sum(1 for d in got.data.stored if d.new)
        problems += [f"{f.accession}: {x}" for x in got.data.failed]
    return len(have), new, problems


# --- Release tables: stated non-GAAP gross profit and revenue ------------------------------

_QUARTER = re.compile(
    r"\b(first|second|third|fourth) quarter(?: and full[- ]year)?(?: of| ended \w+ \d{1,2},)?"
    r"(?: fiscal)? (\d{4})\b",
    re.I,
)
_NGP = re.compile(r"^non-gaap gross profit$", re.I)
_REV = re.compile(r"^(?:total |net )?revenues?$", re.I)


def release_quarter(text: str) -> tuple[int, int] | None:
    m = _QUARTER.search(text)
    if not m:
        return None
    return units.QUARTER_WORDS[m.group(1).lower()], int(m.group(2))


def _row(text: str, rx: re.Pattern) -> tuple[list[float], str] | None:
    for line in text.split("\n"):
        cs = units.cells(line)
        if cs and rx.match(cs[0]):
            vals = [v for v in (units.number(c) for c in cs[1:]) if v is not None]
            if len(vals) >= 2:
                return vals, "\t".join(cs)
    return None


def release_metrics(text: str, fye: str | None = "1231") -> list[units.Metric]:
    """Non-GAAP gross profit and revenue for the release's quarter and the same quarter a
    year earlier (first two columns); a fourth-quarter release's year columns as FY rows."""
    q = release_quarter(text)
    ngp, rev = _row(text, _NGP), _row(text, _REV)
    if q is None or ngp is None:
        return []
    qn, y = q
    scale = units._scale(text)
    out = []
    for metric, row in (("non_gaap_gross_profit", ngp), ("revenue_stated", rev)):
        if row is None:
            continue
        vals, quote = row
        cols = [
            (f"Q{qn}-{y}", units.quarter_dates(qn, y, fye), "stated"),
            (f"Q{qn}-{y - 1}", units.quarter_dates(qn, y - 1, fye), "prior-year column"),
        ]
        if qn == 4 and len(vals) >= 4:
            cols += [
                (f"FY{y}", units.year_dates(y, fye), "stated"),
                (f"FY{y - 1}", units.year_dates(y - 1, fye), "prior-year column"),
            ]
        for (label, (start, end), basis), v in zip(cols, vals, strict=False):
            kind = "non_gaap" if metric.startswith("non_gaap") else "kpi"
            out.append(
                units.Metric(
                    metric, "", label, start, end, v * scale, "USD", kind, basis, quote, EXTRACTOR
                )
            )
    return out


@dataclass(frozen=True)
class MarginYoY:
    label: str
    margin: float
    prior: float
    pp: float
    accession: str


def non_gaap_margin_yoy(engine: sqlite3.Connection, cik: str) -> list[MarginYoY]:
    """Per release: non-GAAP gross margin on its own revenue, current vs prior-year column,
    in percentage points (S16; Invitae 2020Q1 −7.0 pp)."""
    out = []
    accs = [
        r[0]
        for r in engine.execute(
            "SELECT DISTINCT accession FROM unit_metric WHERE cik = ? AND metric = "
            "'non_gaap_gross_profit' AND extractor = ? ORDER BY filed",
            (cik, EXTRACTOR),
        )
    ]
    for acc in accs:
        rows = engine.execute(
            "SELECT metric, period_label, basis, value FROM unit_metric WHERE cik = ? AND "
            "accession = ? AND metric IN ('non_gaap_gross_profit', 'revenue_stated') AND "
            "period_label LIKE 'Q%'",
            (cik, acc),
        ).fetchall()
        v = {(r["metric"], r["basis"]): (r["period_label"], float(r["value"])) for r in rows}
        try:
            (lab, ngp), (_, rev) = (
                v[("non_gaap_gross_profit", "stated")],
                v[("revenue_stated", "stated")],
            )
            (_, ngp0), (_, rev0) = (
                v[("non_gaap_gross_profit", "prior-year column")],
                v[("revenue_stated", "prior-year column")],
            )
        except KeyError:
            continue
        if not rev or not rev0:
            continue
        out.append(MarginYoY(lab, ngp / rev, ngp0 / rev0, (ngp / rev - ngp0 / rev0) * 100, acc))
    return out


def scan_releases(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, cik: str, now: datetime
) -> int:
    """Release-table rows from the company's stored EX-99.1/EX-99.2 (0 requests)."""
    fye = units.fiscal_year_end(engine, cik)
    n = 0
    for d in corpus.execute(
        "SELECT doc_id, accession, filename, doc_type FROM document WHERE cik = ? AND doc_type "
        "IN ('EX-99.1', 'EX-99.2') ORDER BY accession",
        (cik,),
    ).fetchall():
        f = engine.execute(
            "SELECT filed FROM filing WHERE accession = ?", (d["accession"],)
        ).fetchone()
        if f is None:
            continue
        text = corpus.execute(
            "SELECT text FROM document WHERE doc_id = ?", (d["doc_id"],)
        ).fetchone()[0]
        got = release_metrics(text, fye)
        if not got:
            continue
        engine.execute("BEGIN")
        try:
            n += units.store(
                engine,
                cik,
                got,
                accession=d["accession"],
                filename=d["filename"],
                filed=f["filed"],
                source=d["doc_type"],
                now=now,
            )
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise
    return n
