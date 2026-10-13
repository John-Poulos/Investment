"""Stored Form 4 rows as M07 reads them (rules 1, 3 and 7 of M07_OWNERSHIP.md).

- Kinds (rule 1, R22): `buy` = open-market P on a non-derivative line; `sale` = S on a
  non-derivative line; `issuer_buy` = P bought from the issuer (offering, private placement,
  "from the issuer") or code A with a price and a contract footnote (offer letter,
  purchase agreement; Tan) — shown, not scored, not in net flow; everything else (A, D, F,
  M, G, J, K, C, X, W, U, derivative P/S) is `other`: listed "not in total".
- Plan status of a sale (rule 3, D-SEC-10): a row footnote says 10b5-1 → `plan`; the form
  checkbox is set but the row is not identified → `plan_na`; otherwise non-plan.
- Form 4/A (rule 7, D-M07-15): a 4/A row replaces the earlier row of the same owner,
  transaction date and shares (`insider_txn.replaced_by`); when no row matches on shares and
  exactly one earlier row has the same owner, transaction date and code, that row is
  replaced instead ("matched on code"); with zero or several such rows the 4/A row stands
  alone and the pass logs it. The 4/A row keeps the original's filing day, so the day's
  signal is corrected in place and no second alert fires.
- Purchases in an underwritten or registered offering stay `issuer_buy`
  (`purchase_from_issuer`), never open-market buys (D-M07-16).
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
    r"underwritten offering|registered offering|in (the|an?|its) offering)\b",
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
    match: str | None = None  # how this 4/A row was matched: "shares" | "code" (D-M07-15)

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
    """Days for 4/A rows: the matching of `link_amendments`, applied where the stored link
    agrees (rows are in filing order, so a chain of amendments keeps the first original's
    day)."""
    pairs = match_amendments(
        [
            (r.accession, r.line, r.owner_cik, r.txn_date, r.shares, r.code, r.doc_type)
            for r in issuer.rows
        ]  # fmt: skip
    ).links
    at = {(r.accession, r.line): r for r in issuer.rows}
    for a_acc, a_line, o_acc, o_line, how in pairs:
        n, o = at[(a_acc, a_line)], at[(o_acc, o_line)]
        if o.replaced_by == a_acc:
            n.restates, n.day, n.match = o.accession, o.day, how


def _same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) < 0.5


@dataclass
class AmendMatch:
    # (4/A accession, line, original accession, line, "shares" | "code")
    links: list[tuple[str, int, str, int, str]] = field(default_factory=list)
    # (4/A accession, line, earlier unreplaced rows of the same owner, date and code)
    unmatched: list[tuple[str, int, int]] = field(default_factory=list)


def match_amendments(rows: list[tuple]) -> AmendMatch:
    """Rule 7 and D-M07-15 on rows (accession, line, owner CIK, txn date, shares, code, doc
    type) in filing order. Per 4/A, every row is first matched on (owner, date, shares) to the
    most recently filed earlier row not yet replaced; each row still unmatched then takes the
    only earlier unreplaced row of the same owner, date and code, if there is exactly one."""
    out = AmendMatch()
    replaced: set[tuple[str, int]] = set()
    for acc in dict.fromkeys(r[0] for r in rows if r[6] == "4/A"):
        first = next(i for i, r in enumerate(rows) if r[0] == acc)
        earlier = [r for r in rows[:first] if r[0] != acc]
        left = []
        for a in (r for r in rows if r[0] == acc and r[2] is not None):
            hit = next((o for o in reversed(earlier) if (o[0], o[1]) not in replaced
                        and o[2] == a[2] and o[3] == a[3] and _same(o[4], a[4])), None)  # fmt: skip
            if hit is None:
                left.append(a)
                continue
            replaced.add((hit[0], hit[1]))
            out.links.append((a[0], a[1], hit[0], hit[1], "shares"))
        for a in left:
            cands = [o for o in earlier if (o[0], o[1]) not in replaced and o[2] == a[2]
                     and o[3] == a[3] and o[5] == a[5]]  # fmt: skip
            if len(cands) == 1:
                o = cands[0]
                replaced.add((o[0], o[1]))
                out.links.append((a[0], a[1], o[0], o[1], "code"))
            else:
                out.unmatched.append((a[0], a[1], len(cands)))
    return out


@dataclass
class LinkResult:
    links: int = 0
    by_code: int = 0  # links made by the D-M07-15 fallback
    log: list[str] = field(default_factory=list)  # 4/A rows kept apart (both count)


def link_amendments(engine: sqlite3.Connection, cik: str) -> LinkResult:
    """Set `insider_txn.replaced_by` for the issuer from scratch (rule 7, D-M07-15; see
    `match_amendments`). Caller owns the transaction."""
    norm = normalize_cik(cik) or cik
    engine.execute("UPDATE insider_txn SET replaced_by = NULL WHERE issuer_cik = ?", (norm,))
    rows = engine.execute(
        "SELECT t.accession, t.line, t.owner_cik, t.owner_name, t.txn_date, t.shares, t.code, "
        "d.doc_type FROM insider_txn t JOIN form4_doc d ON d.accession = t.accession WHERE "
        "t.issuer_cik = ? ORDER BY d.filed, t.accession, t.line",
        (norm,),
    ).fetchall()
    m = match_amendments(
        [
            (
                r["accession"],
                r["line"],
                r["owner_cik"],
                r["txn_date"],
                _f(r["shares"]),
                r["code"],
                r["doc_type"],
            )
            for r in rows
        ]  # fmt: skip
    )
    engine.executemany(
        "UPDATE insider_txn SET replaced_by = ? WHERE accession = ? AND line = ?",
        [(a_acc, o_acc, o_line) for a_acc, _, o_acc, o_line, _ in m.links],
    )
    at = {(r["accession"], r["line"]): r for r in rows}
    res = LinkResult(len(m.links), sum(1 for x in m.links if x[4] == "code"))
    for acc, line, n in m.unmatched:
        r = at[(acc, line)]
        res.log.append(
            f"Form 4/A {acc} line {line} ({r['owner_name'] or r['owner_cik']}, {r['txn_date']}, "
            f"{r['code']} {r['shares']} sh): no earlier row of the same owner, date and shares; "
            + ("none of the same owner, date and code: stands alone (both count)" if n == 0
               else f"{n} of the same owner, date and code: ambiguous, kept apart (both count)")
        )  # fmt: skip
    return res
