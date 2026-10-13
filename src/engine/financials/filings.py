"""Old filings M04 reads as text (M04 Part 3; D-M04-15, -17; SB.16).

- **Prior 10-Ks** (D-M04-17, DS7): the two annual reports before the latest one, per core
  or promoted company (at most ~28), stored as corpus documents and passages for Part 6's
  recurrence tests. `fund`-tagged companies (ETV) and `spac_shell` years (INFQ's shell
  10-Ks, keyed on period end) are skipped (D-M04-8).
- **Old filings for the walk** (D-M04-15, DS15): at most ~35 filings that changed a value
  the restatement walk could not label from stored text (`restate.old_filing_targets`).
- **8-K texts for events** (D-M04-37): an event class that needs its text (3.01, 4.01, …).

One request per filing: the primary document named in the stored submissions row (the
filing index is read only when that name is missing). A document above ~2 MB is parsed,
stored as text and passages, then dropped from `http_cache` (SB.16). Nothing here runs
on first sight inside the refresh except the per-new-filing 8-K texts (D-M04-70).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from engine.financials import models
from engine.sec.client import SecClient, cache_key
from engine.sec.documents import (
    DOC_TTL_S,
    IndexDoc,
    fetch_filing_index,
    filing_folder,
    ingest_filing,
    store_document,
)
from engine.sec.identity import entity_links
from engine.sec.results import Failed, NotFound, Ok
from engine.sec.submissions import filing_by_accession

ANNUAL_FORMS = ("10-K", "10-KT", "20-F", "40-F")
PRIOR_PER_COMPANY = 2  # D-M04-17
PRIOR_CAP = 28
OLD_FILING_CAP = 35  # D-M04-15
DROP_ABOVE_BYTES = 2_000_000  # SB.16


@dataclass(frozen=True)
class Fetched:
    accession: str
    outcome: str  # stored | already stored | not found | failed | throttled
    detail: str = ""
    mb: float = 0.0

    @property
    def throttled(self) -> bool:
        return self.outcome == "throttled"


def stored_accessions(corpus: sqlite3.Connection, accessions: Iterable[str]) -> set[str]:
    accs = list(dict.fromkeys(accessions))
    out: set[str] = set()
    for i in range(0, len(accs), 500):
        chunk = accs[i : i + 500]
        out |= {
            r[0]
            for r in corpus.execute(
                f"SELECT DISTINCT accession FROM document WHERE accession IN "
                f"({','.join('?' * len(chunk))})",
                chunk,
            )
        }
    return out


def _via_index(
    client: SecClient,
    corpus: sqlite3.Connection,
    cik: str,
    accession: str,
    form: str | None,
    now: datetime,
) -> Fetched:
    """A filing outside the stored index (e.g. GE for the Round 2 walk): its index page,
    then the document typed as its form (2 requests)."""
    idx = fetch_filing_index(client, cik, accession)
    if not isinstance(idx, Ok):
        if isinstance(idx, Failed) and idx.throttled:
            return Fetched(accession, "throttled", idx.reason)
        return Fetched(
            accession, "not found" if not isinstance(idx, Failed) else "failed", str(idx)
        )
    want = (form or "").split("/")[0]
    doc = next((d for d in idx.data if want and (d.doc_type or "") == form), None) or next(
        (d for d in idx.data if (d.doc_type or "").startswith(("10-K", "10-Q", "20-F"))), None
    )
    if doc is None:
        return Fetched(accession, "not found", "no 10-K/10-Q/20-F document in the index")
    res = client.get_bytes(doc.url, ttl_s=DOC_TTL_S)
    if not isinstance(res, Ok):
        if isinstance(res, Failed) and res.throttled:
            return Fetched(accession, "throttled", res.reason)
        return Fetched(accession, "failed", str(res))
    store_document(corpus, cik, accession, doc, res.data, now)
    if len(res.data) > DROP_ABOVE_BYTES:
        corpus.execute("DELETE FROM http_cache WHERE cache_key = ?", (cache_key(doc.url, None),))
    return Fetched(
        accession, "stored", f"{doc.filename} (via the filing index)", len(res.data) / 1e6
    )


def fetch_primary(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    accession: str,
    now: datetime,
    *,
    cik: str | None = None,
    form: str | None = None,
) -> Fetched:
    """Store a filing's primary document (1 request; 2 when the name is not stored or the
    filing is not in the stored index — then `cik` and `form` name it)."""
    if stored_accessions(corpus, [accession]):
        return Fetched(accession, "already stored")
    row = engine.execute("SELECT * FROM filing WHERE accession = ?", (accession,)).fetchone()
    if row is None:
        if not cik:
            return Fetched(accession, "failed", "not in the filing index")
        return _via_index(client, corpus, cik, accession, form, now)
    if not row["primary_doc"]:
        filing = filing_by_accession(engine, accession)
        res = ingest_filing(client, corpus, filing, now, types={row["form"]})
        if isinstance(res, Ok):
            n = len(res.data.stored)
            return Fetched(
                accession, "stored" if n else "not found", f"{n} document(s) via the filing index"
            )
        if isinstance(res, Failed) and res.throttled:
            return Fetched(accession, "throttled", res.reason)
        return Fetched(accession, "failed", str(res))
    url = f"{filing_folder(row['cik'], accession)}/{row['primary_doc']}"
    res = client.get_bytes(url, ttl_s=DOC_TTL_S)
    if isinstance(res, NotFound):
        return Fetched(accession, "not found", url)
    if not isinstance(res, Ok):
        if isinstance(res, Failed) and res.throttled:
            return Fetched(accession, "throttled", res.reason)
        return Fetched(accession, "failed", res.reason if isinstance(res, Failed) else str(res))
    doc = IndexDoc(
        1, row["primary_doc_desc"], row["primary_doc"], url, row["form"], len(res.data), False
    )
    store_document(corpus, row["cik"], accession, doc, res.data, now)
    if len(res.data) > DROP_ABOVE_BYTES:
        corpus.execute("DELETE FROM http_cache WHERE cache_key = ?", (cache_key(url, None),))
    return Fetched(accession, "stored", row["primary_doc"], len(res.data) / 1e6)


def fetch_all(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    accessions: list[str],
    now: datetime,
    log: Callable[[str], None] | None = None,
    names: dict[str, tuple[str, str]] | None = None,
) -> list[Fetched]:
    """Fetch in order; a throttle stops the batch (the rest waits for the next run).
    `names`: accession → (cik, form) for filings outside the stored index."""
    out = []
    for acc in accessions:
        cik, form = (names or {}).get(acc, (None, None))
        f = fetch_primary(client, engine, corpus, acc, now, cik=cik, form=form)
        out.append(f)
        if log:
            log(
                f"  {acc}: {f.outcome}"
                + (f" — {f.detail}" if f.detail else "")
                + (f" ({f.mb:.1f} MB)" if f.mb else "")
            )
        if f.throttled:
            if log:
                log("  SEC throttle: the rest waits for the next run")
            break
    return out


# --- Prior 10-Ks (D-M04-17) ----------------------------------------------------------------


def shell_before(engine: sqlite3.Connection, cik: str) -> str | None:
    """The de-SPAC closing date when the company was a shell under its own CIK."""
    dates = [lk.boundary_date for lk in entity_links(engine, cik) if lk.kind == "spac_shell"]
    return max(dates) if dates else None


@dataclass(frozen=True)
class PriorTarget:
    ticker: str
    cik: str
    accessions: tuple[str, ...]  # the two annual reports before the latest
    stored: tuple[str, ...]
    note: str = ""


def prior_targets(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    mf: models.ModelFile,
) -> list[PriorTarget]:
    """Per company the two annual reports before the latest one (D-M04-17)."""
    out = []
    marks = ",".join("?" * len(ANNUAL_FORMS))
    for ticker, cik in sorted(companies.items()):
        tag = mf.for_company(cik, ticker)
        if tag is not None and tag.tag == "fund":
            out.append(PriorTarget(ticker, cik, (), (), "skipped: fund (D-M04-8)"))
            continue
        shell = shell_before(engine, cik)
        rows = engine.execute(
            f"SELECT f.accession, f.report_date, f.filed FROM filing f JOIN filing_cik c ON "
            f"c.accession = f.accession WHERE c.cik = ? AND f.form IN ({marks}) "
            "ORDER BY f.filed DESC, f.accession DESC",
            (cik, *ANNUAL_FORMS),
        ).fetchall()
        skipped = 0
        if shell:
            kept = [r for r in rows if (r["report_date"] or r["filed"]) >= shell]
            skipped = len(rows) - len(kept)
            rows = kept
        prior = tuple(r["accession"] for r in rows[1 : 1 + PRIOR_PER_COMPANY])
        note = []
        if skipped:
            note.append(f"{skipped} shell-year annual report(s) skipped (before {shell})")
        if len(rows) < 1 + PRIOR_PER_COMPANY:
            note.append(f"{max(len(rows) - 1, 0)} prior annual report(s) stored in the index")
        have = stored_accessions(corpus, prior)
        out.append(
            PriorTarget(ticker, cik, prior, tuple(a for a in prior if a in have), "; ".join(note))
        )
    return out
