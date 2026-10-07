"""Form 4 insider transactions from raw XML (M00_SEC_DATA insiders.py; R7, R13, R16, R22).

Form 4s are structured XML since 2003, and the issuer's submissions list every one,
so raw Form 4s cover the full history (R13: totals from raw Form 4s). SEC's bulk
Insider Transactions Data Sets are a faster backfill path, deferred until checked live.

- The XML is the primary document without its rendering prefix
  ("xslF345X05/form4.xml" → "form4.xml"); if that file is missing, the filing
  index is searched for the Form 4 XML.
- Every non-derivative and derivative transaction becomes a row; holdings
  without a transaction are not rows. Joint filings keep every reporting owner
  (form4_doc.owners); rows carry the first owner for querying.
- 10b5-1: 1 if the 2023+ checkbox (aff10b5One) is set or a footnote referenced
  by the row mentions 10b5-1; 0 if the checkbox is explicitly unset and no such
  footnote; NULL (not disclosed) otherwise — never guessed as 0.
- Missing values stay missing (a gift with no price stores NULL, not 0).
"""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from engine.sec.client import SecClient, iso
from engine.sec.documents import fetch_filing_index, filing_folder
from engine.sec.identity import normalize_cik
from engine.sec.results import Empty, Failed, NotFound, Ok, Probe, Result
from engine.sec.submissions import Filing, stored_filings

PARSER_VERSION = "form4-1"
FORM4_FORMS = ("4", "4/A")
DOC_TTL_S = 3650 * 86400  # filings are immutable
_10B51 = re.compile(r"10b5-?1", re.IGNORECASE)


@dataclass(frozen=True)
class Owner:
    cik: str | None
    name: str | None
    is_director: bool
    is_officer: bool
    is_ten_percent: bool
    is_other: bool
    officer_title: str | None
    other_text: str | None

    @property
    def role(self) -> str:
        parts = []
        if self.is_director:
            parts.append("Director")
        if self.is_officer:
            parts.append(f"Officer ({self.officer_title})" if self.officer_title else "Officer")
        if self.is_ten_percent:
            parts.append("10% Owner")
        if self.is_other:
            parts.append(f"Other ({self.other_text})" if self.other_text else "Other")
        return "; ".join(parts) or "Not stated"


@dataclass(frozen=True)
class Transaction:
    line: int
    table_kind: str  # non_derivative | derivative
    security_title: str | None
    txn_date: str | None
    deemed_date: str | None
    code: str | None  # P purchase, S sale, A grant, M exercise, F tax withholding, G gift, ...
    equity_swap: bool | None
    shares: float | None
    price: float | None
    acquired_disposed: str | None  # A or D
    shares_after: float | None
    direct_indirect: str | None  # D or I
    nature_of_ownership: str | None
    conversion_price: float | None
    underlying_title: str | None
    underlying_shares: float | None
    footnotes: dict[str, str]
    is_10b5_1: bool | None


@dataclass(frozen=True)
class Form4:
    doc_type: str
    period_of_report: str | None
    issuer_cik: str
    issuer_name: str | None
    issuer_ticker: str | None
    aff_10b5_1: bool | None
    owners: tuple[Owner, ...]
    transactions: tuple[Transaction, ...]
    footnotes: dict[str, str] = field(default_factory=dict)


# --- Parsing -----------------------------------------------------------------


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    if found is None:
        return None
    value = found.find("value")
    raw = (value.text if value is not None else found.text) or ""
    raw = " ".join(raw.split())
    return raw or None


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("1", "true", "y", "yes"):
        return True
    if v in ("0", "false", "n", "no"):
        return False
    return None


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _footnote_ids(el: ET.Element) -> list[str]:
    return [f.get("id", "") for f in el.iter("footnoteId") if f.get("id")]


def parse_form4(xml: bytes | str) -> Form4:
    """Parse an ownershipDocument. Raises ValueError if it is not a Form 4 or lacks an issuer."""
    try:
        root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ET.ParseError as exc:
        raise ValueError(f"Form 4 XML unreadable: {exc}") from exc
    if root.tag != "ownershipDocument":
        raise ValueError(f"not an ownershipDocument: <{root.tag}>")
    doc_type = _text(root, "documentType") or ""
    if doc_type not in FORM4_FORMS:
        raise ValueError(f"document type {doc_type!r} is not a Form 4")
    issuer = root.find("issuer")
    issuer_cik = normalize_cik(_text(issuer, "issuerCik") or "")
    if issuer_cik is None:
        raise ValueError("Form 4 has no issuer CIK")

    footnotes = {
        f.get("id", ""): " ".join("".join(f.itertext()).split())
        for f in root.iter("footnote")
        if f.get("id")
    }
    aff = _bool(_text(root, "aff10b5One"))

    owners = []
    for o in root.findall("reportingOwner"):
        ident, rel = o.find("reportingOwnerId"), o.find("reportingOwnerRelationship")
        owners.append(
            Owner(
                cik=normalize_cik(_text(ident, "rptOwnerCik") or ""),
                name=_text(ident, "rptOwnerName"),
                is_director=bool(_bool(_text(rel, "isDirector"))),
                is_officer=bool(_bool(_text(rel, "isOfficer"))),
                is_ten_percent=bool(_bool(_text(rel, "isTenPercentOwner"))),
                is_other=bool(_bool(_text(rel, "isOther"))),
                officer_title=_text(rel, "officerTitle"),
                other_text=_text(rel, "otherText"),
            )
        )

    txns = []
    tables = (
        ("non_derivative", "nonDerivativeTable/nonDerivativeTransaction"),
        ("derivative", "derivativeTable/derivativeTransaction"),
    )
    for kind, path in tables:
        for t in root.findall(path):
            refs = {i: footnotes[i] for i in _footnote_ids(t) if i in footnotes}
            mentions = any(_10B51.search(text) for text in refs.values())
            if aff is True or mentions:
                flag: bool | None = True
            elif aff is False:
                flag = False
            else:
                flag = None
            amounts = t.find("transactionAmounts")
            coding = t.find("transactionCoding")
            underlying = t.find("underlyingSecurity")
            txns.append(
                Transaction(
                    line=len(txns) + 1,
                    table_kind=kind,
                    security_title=_text(t, "securityTitle"),
                    txn_date=_text(t, "transactionDate"),
                    deemed_date=_text(t, "deemedExecutionDate"),
                    code=_text(coding, "transactionCode"),
                    equity_swap=_bool(_text(coding, "equitySwapInvolved")),
                    shares=_num(_text(amounts, "transactionShares")),
                    price=_num(_text(amounts, "transactionPricePerShare")),
                    acquired_disposed=_text(amounts, "transactionAcquiredDisposedCode"),
                    shares_after=_num(
                        _text(t, "postTransactionAmounts/sharesOwnedFollowingTransaction")
                    ),
                    direct_indirect=_text(t, "ownershipNature/directOrIndirectOwnership"),
                    nature_of_ownership=_text(t, "ownershipNature/natureOfOwnership"),
                    conversion_price=_num(_text(t, "conversionOrExercisePrice")),
                    underlying_title=_text(underlying, "underlyingSecurityTitle"),
                    underlying_shares=_num(_text(underlying, "underlyingSecurityShares")),
                    footnotes=refs,
                    is_10b5_1=flag,
                )
            )

    return Form4(
        doc_type=doc_type,
        period_of_report=_text(root, "periodOfReport"),
        issuer_cik=issuer_cik,
        issuer_name=_text(issuer, "issuerName"),
        issuer_ticker=_text(issuer, "issuerTradingSymbol"),
        aff_10b5_1=aff,
        owners=tuple(owners),
        transactions=tuple(txns),
        footnotes=footnotes,
    )


def raw_xml_name(primary_doc: str | None) -> str | None:
    """'xslF345X05/form4.xml' → 'form4.xml' (strip the rendering stylesheet folder)."""
    if not primary_doc or not primary_doc.lower().endswith(".xml"):
        return None
    return primary_doc.rsplit("/", 1)[-1]


# --- Fetch and store -------------------------------------------------------------


def fetch_form4(client: SecClient, filing: Filing) -> Result[tuple[str, bytes]]:
    """(filename, raw XML bytes) of the Form 4; the parser honours the declared encoding."""
    folder = filing_folder(filing.cik, filing.accession)
    probes = []
    name = raw_xml_name(filing.primary_doc)
    if name:
        url = f"{folder}/{name}"
        res = client.get_bytes(url, ttl_s=DOC_TTL_S)
        if isinstance(res, Ok):
            return Ok((name, res.data), source_ref=url, fetched_at=res.fetched_at)
        if not isinstance(res, NotFound):
            return res
        probes.append(Probe("Form 4 XML", url, "HTTP 404: no file at this URL"))

    index = fetch_filing_index(client, filing.cik, filing.accession)
    if isinstance(index, Empty):
        return Empty((*probes, *index.paths_checked))
    if not isinstance(index, Ok):
        return index
    xml_docs = [d for d in index.data if d.filename.lower().endswith(".xml")
                and (d.doc_type or "") in FORM4_FORMS]  # fmt: skip
    for doc in xml_docs:
        res = client.get_bytes(doc.url, ttl_s=DOC_TTL_S)
        if isinstance(res, Ok):
            return Ok((doc.filename, res.data), source_ref=doc.url, fetched_at=res.fetched_at)
        if not isinstance(res, NotFound):
            return res
        probes.append(Probe("Form 4 XML", doc.url, "HTTP 404: no file at this URL"))
    probes.append(Probe("filing index", index.source_ref, f"{len(xml_docs)} Form 4 XML listed"))
    return Empty(tuple(probes))


def store_form4(
    engine: sqlite3.Connection, filing: Filing, filename: str, form: Form4, now: datetime
) -> int:
    """Replace this accession's rows. Caller owns the transaction. Returns rows stored."""
    first = form.owners[0] if form.owners else None
    engine.execute("DELETE FROM insider_txn WHERE accession = ?", (filing.accession,))
    engine.executemany(
        "INSERT INTO insider_txn (accession, line, issuer_cik, owner_cik, owner_name, role, "
        "table_kind, security_title, txn_date, code, acquired_disposed, shares, price, "
        "shares_after, direct_indirect, is_10b5_1, officer_title, deemed_date, equity_swap, "
        "nature_of_ownership, conversion_price, underlying_title, underlying_shares, footnotes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                filing.accession,
                t.line,
                form.issuer_cik,
                first.cik if first else None,
                first.name if first else None,
                first.role if first else None,
                t.table_kind,
                t.security_title,
                t.txn_date,
                t.code,
                t.acquired_disposed,
                t.shares,
                t.price,
                t.shares_after,
                t.direct_indirect,
                None if t.is_10b5_1 is None else int(t.is_10b5_1),
                first.officer_title if first else None,
                t.deemed_date,
                None if t.equity_swap is None else int(t.equity_swap),
                t.nature_of_ownership,
                t.conversion_price,
                t.underlying_title,
                t.underlying_shares,
                json.dumps(t.footnotes) if t.footnotes else None,
            )  # fmt: skip
            for t in form.transactions
        ],
    )
    engine.execute(
        "INSERT INTO form4_doc (accession, issuer_cik, issuer_name, issuer_ticker, doc_type, "
        "period_of_report, filed, filename, aff_10b5_1, owners, transactions, parser_version, "
        "parsed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (accession) DO "
        "UPDATE SET issuer_cik = excluded.issuer_cik, issuer_name = excluded.issuer_name, "
        "issuer_ticker = excluded.issuer_ticker, doc_type = excluded.doc_type, "
        "period_of_report = excluded.period_of_report, filed = excluded.filed, "
        "filename = excluded.filename, aff_10b5_1 = excluded.aff_10b5_1, "
        "owners = excluded.owners, transactions = excluded.transactions, "
        "parser_version = excluded.parser_version, parsed_at = excluded.parsed_at",
        (
            filing.accession,
            form.issuer_cik,
            form.issuer_name,
            form.issuer_ticker,
            form.doc_type,
            form.period_of_report,
            filing.filed,
            filename,
            None if form.aff_10b5_1 is None else int(form.aff_10b5_1),
            json.dumps([{**o.__dict__, "role": o.role} for o in form.owners]),
            len(form.transactions),
            PARSER_VERSION,
            iso(now),
        ),  # fmt: skip
    )
    return len(form.transactions)


def ingest_form4(
    client: SecClient, engine: sqlite3.Connection, filing: Filing, now: datetime
) -> Result[int]:
    fetched = fetch_form4(client, filing)
    if not isinstance(fetched, Ok):
        return fetched
    filename, raw = fetched.data
    try:
        form = parse_form4(raw)
    except ValueError as exc:
        return Failed(str(exc), url=fetched.source_ref)
    engine.execute("BEGIN")
    try:
        n = store_form4(engine, filing, filename, form, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return Ok(n, source_ref=fetched.source_ref, fetched_at=iso(now))


@dataclass(frozen=True)
class InsiderSync:
    issuer_cik: str
    filings: int
    ingested: int
    already: int
    transactions: int
    failed: tuple[str, ...] = field(default_factory=tuple)  # "accession: reason"

    @property
    def complete(self) -> bool:
        return not self.failed


def sync_insiders(
    client: SecClient,
    engine: sqlite3.Connection,
    issuer_cik: str,
    now: datetime,
    *,
    since: str | None = None,
    limit: int | None = None,
) -> Result[InsiderSync]:
    """Parse every stored Form 4 / 4-A listed under the issuer that is not yet parsed.

    Needs sync_filings first (the filing index). Newest first; `limit` caps the
    number fetched this run (the rest are picked up next run).
    """
    norm = normalize_cik(issuer_cik)
    if norm is None:
        return Empty((Probe("CIK", str(issuer_cik), "not a CIK"),))
    filings = stored_filings(engine, norm, forms=FORM4_FORMS, since=since)
    done = {
        r[0]
        for r in engine.execute(
            "SELECT accession FROM form4_doc WHERE parser_version = ?", (PARSER_VERSION,)
        )
    }
    todo = [f for f in filings if f.accession not in done]
    if limit is not None:
        todo = todo[:limit]

    ingested = rows = 0
    failed = []
    for f in todo:
        res = ingest_form4(client, engine, f, now)
        if isinstance(res, Ok):
            ingested += 1
            rows += res.data
        elif isinstance(res, Failed) and res.throttled:
            failed.append(f"{f.accession}: {res.reason}")
            break  # breaker open: stop this run, retry later
        else:
            reason = res.reason if isinstance(res, Failed) else str(res)
            failed.append(f"{f.accession}: {reason}")
    summary = InsiderSync(norm, len(filings), ingested, len(filings) - len(todo), rows,
                          tuple(failed))  # fmt: skip
    return Ok(summary, fetched_at=iso(now))


# --- Reads -----------------------------------------------------------------------


def transactions(
    engine: sqlite3.Connection,
    issuer_cik: str,
    *,
    since: str | None = None,
    codes: Iterable[str] | None = None,
    table_kind: str | None = None,
) -> list[sqlite3.Row]:
    """Stored transactions for an issuer, newest first."""
    sql = "SELECT * FROM insider_txn WHERE issuer_cik = ?"
    args: list[object] = [normalize_cik(issuer_cik) or issuer_cik]
    if since:
        sql += " AND txn_date >= ?"
        args.append(since)
    code_list = list(codes or [])
    if code_list:
        sql += f" AND code IN ({', '.join('?' * len(code_list))})"
        args += code_list
    if table_kind:
        sql += " AND table_kind = ?"
        args.append(table_kind)
    sql += " ORDER BY txn_date DESC, accession DESC, line"
    return engine.execute(sql, args).fetchall()
