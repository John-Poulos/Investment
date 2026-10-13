"""Stored Form 4 rows as M07 reads them (rules 1, 3 and 7 of M07_OWNERSHIP.md).

- Kinds (rule 1, R22): `buy` = open-market P on a non-derivative line; `sale` = S on a
  non-derivative line; `issuer_buy` = P bought from the issuer (offering, private placement,
  "from the issuer") or code A with a price and a contract footnote (offer letter,
  purchase agreement; Tan) — shown, not scored, not in net flow; everything else (A, D, F,
  M, G, J, K, C, X, W, U, derivative P/S) is `other`: listed "not in total".
- Plan status of a sale (rule 3, D-SEC-10): a row footnote says 10b5-1 → `plan`; the form
  checkbox is set but the row is not identified → `plan_na`; otherwise non-plan.
- Form 4/A (rule 7): a 4/A row replaces the earlier row of the same owner, transaction date
  and shares (`insider_txn.replaced_by`); the 4/A row keeps the original's filing day, so the
  day's signal is corrected in place and no second alert fires.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field

from engine.sec.identity import normalize_cik
from engine.sec.insiders import BASIS_FORM_ONLY

_ISSUER_P = re.compile(
    r"\b(from the (issuer|company|registrant)|directly from|private placement|registered direct|"
    r"subscription agreement|securities purchase agreement|public offering|"
    r"in (the|an|its) (underwritten |registered )?offering)\b",
    re.IGNORECASE,
)
_CONTRACT_A = re.compile(
    r"\b(offer letter|employment agreement|letter agreement|purchase agreement|subscription "
    r"agreement|required to purchase|agreed to purchase|purchased? from the (issuer|company)|"
    r"private placement)\b",
    re.IGNORECASE,
)


@dataclass
class Row:
    accession: str
    line: int
    filed: str  # the form's filing date
    doc_type: str  # 4 or 4/A
    owner_cik: str | None
    owner_name: str | None
    role: str | None
    table_kind: str | None
    title: str | None
    txn_date: str | None
    code: str | None
    acquired_disposed: str | None
    shares: float | None
    price: float | None
    shares_after: float | None
    direct_indirect: str | None
    nature: str | None
    footnotes: dict[str, str]
    is_10b5_1: int | None
    plan_basis: str | None
    replaced_by: str | None
    parser_version: str
    day: str = ""  # filing day the row counts on (a 4/A row: the original's)
    restates: str | None = None  # accession of the row this 4/A row replaced

    @property
    def usd(self) -> float | None:
        if self.shares is None or self.price is None:
            return None
        return float(self.shares) * float(self.price)

    @property
    def kind(self) -> str:
        return row_kind(self)

    @property
    def plan(self) -> str | None:
        """plan | plan_na | non_plan for a sale; None otherwise."""
        if self.kind != "sale":
            return None
        if self.is_10b5_1 == 1:
            return "plan"
        if self.is_10b5_1 is None and self.plan_basis == BASIS_FORM_ONLY:
            return "plan_na"
        return "non_plan"

    @property
    def effective(self) -> bool:
        return self.replaced_by is None


def row_kind(r: Row) -> str:
    notes = " ".join(r.footnotes.values())
    if r.table_kind == "non_derivative" and r.code == "P":
        return "issuer_buy" if _ISSUER_P.search(notes) else "buy"
    if r.table_kind == "non_derivative" and r.code == "S":
        return "sale"
    if r.code == "A" and r.price and float(r.price) > 0 and _CONTRACT_A.search(notes):
        return "issuer_buy"
    return "other"


@dataclass
class HoldingLine:
    accession: str
    line: int
    table_kind: str
    title: str | None
    shares: float | None
    direct_indirect: str | None
    nature: str | None


@dataclass
class Issuer:
    """Every stored Form 4 row and holding line of one issuer, with 4/A links applied."""

    cik: str
    rows: list[Row] = field(default_factory=list)
    holdings: dict[str, list[HoldingLine]] = field(default_factory=dict)

    def by_accession(self) -> dict[str, list[Row]]:
        out: dict[str, list[Row]] = {}
        for r in self.rows:
            out.setdefault(r.accession, []).append(r)
        return out

    def effective(self) -> list[Row]:
        return [r for r in self.rows if r.effective]


def load(engine: sqlite3.Connection, cik: str) -> Issuer:
    norm = normalize_cik(cik) or cik
    out = Issuer(norm)
    for r in engine.execute(
        "SELECT t.*, d.filed, d.doc_type, d.parser_version FROM insider_txn t JOIN form4_doc d "
        "ON d.accession = t.accession WHERE t.issuer_cik = ? ORDER BY d.filed, t.accession, t.line",
        (norm,),
    ):
        out.rows.append(
            Row(
                accession=r["accession"],
                line=r["line"],
                filed=r["filed"] or "",
                doc_type=r["doc_type"],
                owner_cik=r["owner_cik"],
                owner_name=r["owner_name"],
                role=r["role"],
                table_kind=r["table_kind"],
                title=r["security_title"],
                txn_date=r["txn_date"],
                code=r["code"],
                acquired_disposed=r["acquired_disposed"],
                shares=_f(r["shares"]),
                price=_f(r["price"]),
                shares_after=_f(r["shares_after"]),
                direct_indirect=r["direct_indirect"],
                nature=r["nature_of_ownership"],
                footnotes=json.loads(r["footnotes"]) if r["footnotes"] else {},
                is_10b5_1=r["is_10b5_1"],
                plan_basis=r["plan_basis"],
                replaced_by=r["replaced_by"],
                parser_version=r["parser_version"],
                day=r["filed"] or "",
            )  # fmt: skip
        )
    for h in engine.execute(
        "SELECT h.* FROM form4_holding h JOIN form4_doc d ON d.accession = h.accession "
        "WHERE d.issuer_cik = ? ORDER BY h.accession, h.line",
        (norm,),
    ):
        out.holdings.setdefault(h["accession"], []).append(
            HoldingLine(
                h["accession"],
                h["line"],
                h["table_kind"],
                h["title"],
                _f(h["shares"]),
                h["direct_indirect"],
                h["nature"],
            )  # fmt: skip
        )
    _attribute(out)
    return out


def _f(v: object) -> float | None:
    return None if v is None else float(v)  # type: ignore[arg-type]


def _attribute(issuer: Issuer) -> None:
    """Days for 4/A rows from the stored links (rows are in filing order, so a chain of
    amendments keeps the first original's day)."""
    for r in issuer.rows:
        if r.replaced_by is None:
            continue
        # the replacing row: the 4/A's row of the same owner, date and shares
        for n in issuer.rows:
            if (n.accession == r.replaced_by and n.restates is None and n.owner_cik == r.owner_cik
                    and n.txn_date == r.txn_date and _same(n.shares, r.shares)):  # fmt: skip
                n.restates = r.accession
                n.day = r.day
                break


def _same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) < 0.5


def link_amendments(engine: sqlite3.Connection, cik: str) -> int:
    """Set `insider_txn.replaced_by` for the issuer from scratch (rule 7). Each 4/A row
    replaces at most one earlier row of the same owner, transaction date and shares — the
    most recently filed one not yet replaced. Caller owns the transaction. Returns links."""
    norm = normalize_cik(cik) or cik
    engine.execute("UPDATE insider_txn SET replaced_by = NULL WHERE issuer_cik = ?", (norm,))
    rows = engine.execute(
        "SELECT t.accession, t.line, t.owner_cik, t.txn_date, t.shares, d.filed, d.doc_type "
        "FROM insider_txn t JOIN form4_doc d ON d.accession = t.accession WHERE "
        "t.issuer_cik = ? ORDER BY d.filed, t.accession, t.line",
        (norm,),
    ).fetchall()
    replaced: set[tuple[str, int]] = set()
    links = []
    for i, a in enumerate(rows):
        if a["doc_type"] != "4/A" or a["owner_cik"] is None:
            continue
        for o in reversed(rows[:i]):
            key = (o["accession"], o["line"])
            if (o["accession"] != a["accession"] and key not in replaced
                    and o["owner_cik"] == a["owner_cik"] and o["txn_date"] == a["txn_date"]
                    and _same(_f(o["shares"]), _f(a["shares"]))):  # fmt: skip
                replaced.add(key)
                links.append((a["accession"], o["accession"], o["line"]))
                break
    engine.executemany(
        "UPDATE insider_txn SET replaced_by = ? WHERE accession = ? AND line = ?", links
    )
    return len(links)
