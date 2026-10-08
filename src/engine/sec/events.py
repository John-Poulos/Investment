"""Typed 8-K events from the stored filing index (M00_SEC_DATA events.py; R16, R19, M04).

Each item on an 8-K / 8-K/A becomes one event (6-K current reports of foreign
filers carry no item codes and become one "6-K" event). Classification uses a
versioned catalog of every Form 8-K item; item codes outside the catalog (e.g.
pre-2004 numbering) are kept as category "unknown", never dropped.

Severity is a default for alerting (M01 rule 6: events surface immediately);
defaults approved by the owner 2026-10-07 and adjustable later (M00_SEC_DATA,
D-SEC-12). The engine signals; the owner decides (D8, D16).
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from engine.sec.client import SecClient
from engine.sec.documents import FilingDocs, ingest_filing
from engine.sec.identity import normalize_cik
from engine.sec.results import Empty, Failed, Ok, Probe, Result
from engine.sec.submissions import Filing, filing_by_accession, stored_filings

CATALOG_VERSION = "items-2026-10"
EVENT_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A")
SEVERITIES = ("high", "medium", "low", "none")


@dataclass(frozen=True)
class ItemSpec:
    title: str
    category: str
    severity: str
    modules: tuple[str, ...]


# Form 8-K items. Severity defaults approved 2026-10-07 (D-SEC-12).
CATALOG: dict[str, ItemSpec] = {
    "1.01": ItemSpec(
        "Entry into a Material Definitive Agreement", "agreement", "medium", ("M02", "M05", "M06")
    ),
    "1.02": ItemSpec(
        "Termination of a Material Definitive Agreement",
        "agreement",
        "medium",
        ("M02", "M04", "M06"),
    ),
    "1.03": ItemSpec("Bankruptcy or Receivership", "red_flag", "high", ("M04", "M11")),
    "1.04": ItemSpec(
        "Mine Safety - Reporting of Shutdowns and Patterns of Violations", "other", "low", ("M04",)
    ),
    "1.05": ItemSpec("Material Cybersecurity Incidents", "red_flag", "medium", ("M04", "M11")),
    "2.01": ItemSpec(
        "Completion of Acquisition or Disposition of Assets", "agreement", "medium", ("M02", "M04")
    ),
    "2.02": ItemSpec(
        "Results of Operations and Financial Condition", "earnings", "medium", ("M04", "M11")
    ),
    "2.03": ItemSpec(
        "Creation of a Direct Financial Obligation or an Obligation under an "
        "Off-Balance Sheet Arrangement",
        "capital",
        "low",
        ("M04",),
    ),
    "2.04": ItemSpec(
        "Triggering Events That Accelerate or Increase a Direct Financial Obligation",
        "red_flag",
        "high",
        ("M04", "M11"),
    ),
    "2.05": ItemSpec(
        "Costs Associated with Exit or Disposal Activities", "red_flag", "medium", ("M04",)
    ),
    "2.06": ItemSpec("Material Impairments", "red_flag", "medium", ("M04",)),
    "3.01": ItemSpec(
        "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
        "red_flag",
        "high",
        ("M04", "M11"),
    ),
    "3.02": ItemSpec(
        "Unregistered Sales of Equity Securities", "capital", "medium", ("M04", "M07")
    ),
    "3.03": ItemSpec(
        "Material Modification to Rights of Security Holders", "capital", "medium", ("M04", "M07")
    ),
    "4.01": ItemSpec(
        "Changes in Registrant's Certifying Accountant", "red_flag", "medium", ("M04",)
    ),
    "4.02": ItemSpec(
        "Non-Reliance on Previously Issued Financial Statements or a Related Audit Report",
        "red_flag",
        "high",
        ("M04", "M11"),
    ),
    "5.01": ItemSpec("Changes in Control of Registrant", "people", "high", ("M07", "M11")),
    "5.02": ItemSpec(
        "Departure/Election of Directors or Officers; Compensatory Arrangements",
        "people",
        "medium",
        ("M07", "M11"),
    ),
    "5.03": ItemSpec(
        "Amendments to Articles of Incorporation or Bylaws; Change in Fiscal Year",
        "governance",
        "low",
        ("M04",),
    ),
    "5.04": ItemSpec(
        "Temporary Suspension of Trading Under Registrant's Employee Benefit Plans",
        "governance",
        "low",
        ("M07",),
    ),
    "5.05": ItemSpec(
        "Amendments to the Code of Ethics, or Waiver of a Provision", "governance", "low", ("M04",)
    ),
    "5.06": ItemSpec("Change in Shell Company Status", "governance", "medium", ("M04",)),
    "5.07": ItemSpec(
        "Submission of Matters to a Vote of Security Holders", "governance", "low", ("M07",)
    ),
    "5.08": ItemSpec("Shareholder Director Nominations", "governance", "low", ("M07",)),
    "6.01": ItemSpec("ABS Informational and Computational Material", "abs", "none", ()),
    "6.02": ItemSpec("Change of Servicer or Trustee", "abs", "none", ()),
    "6.03": ItemSpec("Change in Credit Enhancement or Other External Support", "abs", "none", ()),
    "6.04": ItemSpec("Failure to Make a Required Distribution", "abs", "none", ()),
    "6.05": ItemSpec("Securities Act Updating Disclosure", "abs", "none", ()),
    "6.06": ItemSpec("Static Pool", "abs", "none", ()),
    "6.10": ItemSpec("Alternative Filings of Asset-Backed Issuers", "abs", "none", ()),
    "7.01": ItemSpec("Regulation FD Disclosure", "disclosure", "low", ("M02", "M11")),
    "8.01": ItemSpec("Other Events", "disclosure", "low", ("M02", "M11")),
    "9.01": ItemSpec("Financial Statements and Exhibits", "exhibits", "none", ()),
}
FOREIGN = ItemSpec(
    "Report of Foreign Private Issuer (6-K)", "foreign_report", "low", ("M02", "M11")
)
UNKNOWN_SEVERITY = "low"


@dataclass(frozen=True)
class Event:
    accession: str
    item: str
    cik: str
    form: str
    filed: str
    accepted_at: str | None
    report_date: str | None
    category: str
    severity: str
    title: str
    modules: tuple[str, ...]
    amended: bool


def classify_filing(filing: Filing) -> list[Event]:
    """Events for one stored filing (empty for forms that are not current reports)."""
    if filing.form not in EVENT_FORMS:
        return []
    amended = filing.form.endswith("/A")
    if filing.form.startswith("6-K"):
        pairs = [("6-K", FOREIGN)]
    elif not filing.items:
        pairs = [("unlisted", ItemSpec("8-K without item codes", "unknown", UNKNOWN_SEVERITY, ()))]
    else:
        pairs = []
        for code in filing.items:
            spec = CATALOG.get(code)
            if spec is None:
                spec = ItemSpec(f"Item {code} (not in catalog {CATALOG_VERSION})", "unknown",
                                UNKNOWN_SEVERITY, ())  # fmt: skip
            pairs.append((code, spec))
    return [
        Event(filing.accession, code, filing.cik, filing.form, filing.filed, filing.accepted_at,
              filing.report_date, spec.category, spec.severity, spec.title, spec.modules, amended)
        for code, spec in pairs
    ]  # fmt: skip


@dataclass(frozen=True)
class EventBuild:
    cik: str
    filings: int
    events: int
    by_category: dict[str, int]
    unknown_items: dict[str, int] = field(default_factory=dict)


def build_events(engine: sqlite3.Connection, cik: str) -> Result[EventBuild]:
    """Rebuild the cik's events from its stored filing index (run after sync_filings)."""
    norm = normalize_cik(cik)
    if norm is None:
        return Empty((Probe("CIK", str(cik), "not a CIK"),))
    filings = stored_filings(engine, norm, forms=EVENT_FORMS)
    events = [e for f in filings for e in classify_filing(f)]
    engine.execute("BEGIN")
    try:
        engine.execute("DELETE FROM event WHERE cik = ?", (norm,))
        engine.executemany(
            "INSERT INTO event (accession, item, cik, form, filed, accepted_at, report_date, "
            "category, severity, title, modules, amended, catalog) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    e.accession,
                    e.item,
                    e.cik,
                    e.form,
                    e.filed,
                    e.accepted_at,
                    e.report_date,
                    e.category,
                    e.severity,
                    e.title,
                    json.dumps(list(e.modules)),
                    int(e.amended),
                    CATALOG_VERSION,
                )
                for e in events
            ],  # fmt: skip
        )
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    unknown = Counter(e.item for e in events if e.category == "unknown")
    summary = EventBuild(
        norm, len(filings), len(events), dict(Counter(e.category for e in events)), dict(unknown)
    )
    return Ok(summary)


def events(
    engine: sqlite3.Connection,
    cik: str,
    *,
    since: str | None = None,
    categories: Iterable[str] | None = None,
    min_severity: str = "none",
) -> list[Event]:
    """Stored events for a cik, newest first, at or above `min_severity`."""
    if min_severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    allowed = SEVERITIES[: SEVERITIES.index(min_severity) + 1]
    sql = f"SELECT * FROM event WHERE cik = ? AND severity IN ({', '.join('?' * len(allowed))})"
    args: list[object] = [normalize_cik(cik) or cik, *allowed]
    if since:
        sql += " AND filed >= ?"
        args.append(since)
    cats = list(categories or [])
    if cats:
        sql += f" AND category IN ({', '.join('?' * len(cats))})"
        args += cats
    sql += " ORDER BY filed DESC, accepted_at DESC, accession DESC, item"
    return [
        Event(r["accession"], r["item"], r["cik"], r["form"], r["filed"], r["accepted_at"],
              r["report_date"], r["category"], r["severity"], r["title"],
              tuple(json.loads(r["modules"])), bool(r["amended"]))
        for r in engine.execute(sql, args)
    ]  # fmt: skip


@dataclass(frozen=True)
class EventDocs:
    stored: dict[str, FilingDocs]  # accession → documents stored
    failed: tuple[str, ...] = field(default_factory=tuple)  # "accession: reason"

    @property
    def complete(self) -> bool:
        return not self.failed


def ingest_event_documents(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    selected: Iterable[Event],
    now: datetime,
) -> Result[EventDocs]:
    """Store the text of the filings behind selected events (sections such as
    "8-K Item 4.02"), so modules and the grounded LLM can read them later.
    Failures are listed per accession; one failure does not stop the rest,
    except a throttle, which stops the run."""
    stored: dict[str, FilingDocs] = {}
    failed: list[str] = []
    for accession in dict.fromkeys(e.accession for e in selected):
        filing = filing_by_accession(engine, accession)
        if filing is None:
            failed.append(f"{accession}: not in the filing index")
            continue
        res = ingest_filing(client, corpus, filing, now)
        if isinstance(res, Ok):
            stored[accession] = res.data
            continue
        failed.append(f"{accession}: {res.reason if isinstance(res, Failed) else res}")
        if isinstance(res, Failed) and res.throttled:
            break
    return Ok(EventDocs(stored, tuple(failed)))
