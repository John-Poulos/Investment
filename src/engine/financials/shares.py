"""Share series (D-M04-2; M04 Part 1a).

Four series that are never mixed, plus stock-based compensation:

- `shares_period_end` — `CommonStockSharesOutstanding` on the balance-sheet date;
- `shares_cover` — the cover count on its own cover date: `dei:EntityCommonStockShares
  Outstanding` where the company reports a total, else the class-summed count from the
  filing's R1 page (`sec/cover.py`); a filing whose R1 is not a cover falls back to basic
  weighted average, labelled;
- `shares_basic_wavg`, `shares_diluted_wavg` — weighted averages per quarter and year;
- `sbc` — share-based compensation.

Implied float shares = `dei:EntityPublicFloat` ÷ the close on its date, once a year,
labelled "implied" (M07 owns R22). Split guard: every share count is scaled by the splits
recorded in the company's price bars after its date (Tiingo split factors), and the
factor is shown; a count with no price history says so.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta

from engine.sec.cover import r1_outcome
from engine.sec.identity import normalize_cik
from engine.sec.xbrl_facts import CONCEPT_BY_NAME, get_series

SERIES_LABELS = {
    "shares_cover": "Cover shares (all classes, cover date)",
    "shares_period_end": "Period-end shares (balance sheet)",
    "shares_basic_wavg": "Basic weighted-average shares",
    "shares_diluted_wavg": "Diluted weighted-average shares",
    "sbc": "Share-based compensation",
    "implied_float": "Implied float shares (yearly)",
}
PERIODIC = ("10-K", "10-Q", "10-KT", "10-QT", "10-K/A", "10-Q/A")


@dataclass
class ShareValue:
    series: str
    date: str  # period end, cover date or float date
    value: float | None
    ptype: str = "I"  # I | Q | FY
    start: str | None = None
    tag: str = ""
    accession: str = ""
    first_filed: str = ""
    latest_filed: str = ""
    note: str = ""  # split factor, implied, fallback
    classes: list[tuple[str, float]] = field(default_factory=list)


# --- Prices and splits -------------------------------------------------------------------


def price_symbols(engine: sqlite3.Connection, cik: str) -> list[str]:
    norm = normalize_cik(cik) or cik
    rows = engine.execute(
        "SELECT symbol FROM price_fetch WHERE cik = ? UNION "
        "SELECT ticker FROM ticker WHERE cik = ? AND valid_to IS NULL",
        (norm, norm),
    ).fetchall()
    return [r[0] for r in rows]


def splits_after(engine: sqlite3.Connection, cik: str, day: str) -> tuple[float, list[str]]:
    """(product of split factors on bars after `day`, ["2024-08-08 ×10", …])."""
    factor, seen = 1.0, []
    symbols = price_symbols(engine, cik)
    if not symbols:
        return 1.0, []
    marks = ",".join("?" * len(symbols))
    done: set[str] = set()
    for r in engine.execute(
        f"SELECT date, split_factor FROM price_bar WHERE symbol IN ({marks}) AND date > ? "
        "AND split_factor IS NOT NULL AND split_factor != 1 ORDER BY date",
        (*symbols, day),
    ):
        if r["date"] in done:  # GOOG and GOOGL carry the same split
            continue
        done.add(r["date"])
        factor *= float(r["split_factor"])
        seen.append(f"{r['date']} ×{float(r['split_factor']):g}")
    return factor, seen


def has_prices(engine: sqlite3.Connection, cik: str) -> bool:
    symbols = price_symbols(engine, cik)
    if not symbols:
        return False
    marks = ",".join("?" * len(symbols))
    return (
        engine.execute(
            f"SELECT 1 FROM price_bar WHERE symbol IN ({marks}) LIMIT 1", symbols
        ).fetchone()
        is not None
    )


def close_on(
    engine: sqlite3.Connection, cik: str, day: str, tolerance_days: int = 5
) -> tuple[float, str] | None:
    """Raw close on `day`, or the last bar up to `tolerance_days` before it."""
    symbols = price_symbols(engine, cik)
    if not symbols:
        return None
    marks = ",".join("?" * len(symbols))
    lo = (date.fromisoformat(day) - timedelta(days=tolerance_days)).isoformat()
    row = engine.execute(
        f"SELECT close, date FROM price_bar WHERE symbol IN ({marks}) AND date <= ? AND date >= ? "
        "AND close IS NOT NULL ORDER BY date DESC LIMIT 1",
        (*symbols, day, lo),
    ).fetchone()
    return (float(row["close"]), row["date"]) if row else None


def split_note(engine: sqlite3.Connection, cik: str, day: str) -> tuple[float, str]:
    factor, seen = splits_after(engine, cik, day)
    if seen:
        return factor, f"split-adjusted ×{factor:g} ({', '.join(seen)})"
    if not has_prices(engine, cik):
        return 1.0, "split check: no price history stored"
    return 1.0, ""


# --- Cover counts ------------------------------------------------------------------------


def _dei_covers(engine: sqlite3.Connection, cik: str) -> dict[str, ShareValue]:
    """accession → cover count from the non-dimensional dei tag (first filed version)."""
    out: dict[str, ShareValue] = {}
    for r in engine.execute(
        "SELECT period_end, value, accession, filed, form FROM fact WHERE cik = ? AND "
        "taxonomy = 'dei' AND tag = 'EntityCommonStockSharesOutstanding' AND unit = 'shares' "
        "ORDER BY filed, accession",
        (cik,),
    ):
        value = ShareValue(
            "shares_cover",
            r["period_end"],
            float(r["value"]),
            tag="dei:EntityCommonStockSharesOutstanding",
            accession=r["accession"],
            first_filed=r["filed"],
            latest_filed=r["filed"],
        )
        out.setdefault(r["accession"], value)
    return out


def _r1_covers(engine: sqlite3.Connection, cik: str) -> dict[str, ShareValue]:
    rows = engine.execute(
        "SELECT accession, class_label, shares, cover_date, filed FROM cover_shares "
        "WHERE cik = ? ORDER BY accession, class_label",
        (cik,),
    ).fetchall()
    out: dict[str, ShareValue] = {}
    for r in rows:
        v = out.setdefault(r["accession"], ShareValue(
            "shares_cover", r["cover_date"], 0.0, tag="R1 cover page (classes summed)",
            accession=r["accession"], first_filed=r["filed"] or "", latest_filed=r["filed"] or "",
        ))  # fmt: skip
        v.classes.append((r["class_label"] or "(no class)", float(r["shares"])))
        v.value = (v.value or 0.0) + float(r["shares"])
    return out


def cover_counts(engine: sqlite3.Connection, cik: str) -> list[ShareValue]:
    """Cover counts, newest first: R1 class sums where read, else the dei total; each
    split-adjusted to today with the factor in its note."""
    norm = normalize_cik(cik) or cik
    merged = _dei_covers(engine, norm) | _r1_covers(engine, norm)
    out = []
    for v in merged.values():
        factor, note = split_note(engine, norm, v.date)
        if factor != 1.0 and v.value is not None:
            v.value *= factor
            v.classes = [(c, n * factor) for c, n in v.classes]
        v.note = note
        out.append(v)
    return sorted(out, key=lambda v: (v.date, v.accession), reverse=True)


def latest_periodic(engine: sqlite3.Connection, cik: str) -> sqlite3.Row | None:
    """Latest 10-K/10-Q whose facts are stored (companyfacts can lag a filing by a day)."""
    marks = ",".join("?" * len(PERIODIC))
    return engine.execute(
        f"SELECT f.accession, f.form, f.filed, f.report_date FROM filing f WHERE f.cik = ? "
        f"AND f.form IN ({marks}) AND EXISTS (SELECT 1 FROM fact x WHERE x.cik = f.cik AND "
        "x.accession = f.accession) ORDER BY f.filed DESC LIMIT 1",
        (cik, *PERIODIC),
    ).fetchone()


def needs_r1(engine: sqlite3.Connection, cik: str) -> bool:
    """Multi-class filer without a total: its latest periodic filing's facts carry no
    non-dimensional dei cover count (GOOG, META, MSTR, SPCX in 2026, D-M04-2)."""
    norm = normalize_cik(cik) or cik
    latest = latest_periodic(engine, norm)
    if latest is None:
        return False
    return (
        engine.execute(
            "SELECT 1 FROM fact WHERE cik = ? AND accession = ? AND taxonomy = 'dei' AND "
            "tag = 'EntityCommonStockSharesOutstanding'",
            (norm, latest["accession"]),
        ).fetchone()
        is None
    )


def cover_missing_reason(engine: sqlite3.Connection, cik: str) -> str:
    norm = normalize_cik(cik) or cik
    latest = latest_periodic(engine, norm)
    if latest is None:
        return "no 10-K or 10-Q facts stored"
    if not needs_r1(engine, norm):
        return "no cover count stored"
    state = r1_outcome(engine, latest["accession"])
    if state is None:
        return "multi-class, no total tag (R1 page not read yet)"
    if state.get("outcome") == "not_cover":
        return "multi-class, no total tag; R1 is not a cover page"
    return f"multi-class, no total tag; R1 {state.get('outcome', 'unread')}"


def basic_fallback(engine: sqlite3.Connection, cik: str, period_end: str) -> ShareValue | None:
    """Basic weighted average for a period whose cover count is missing (labelled)."""
    rows = [r for r in get_series(engine, cik, "shares_basic_wavg") if r.end == period_end]
    if not rows:
        return None
    r = max(rows, key=lambda x: x.ptype == "Q")
    factor, note = split_note(engine, cik, r.end)
    return ShareValue(
        "shares_cover", r.end, float(r.latest.value) * factor, r.ptype, r.start, r.method,
        r.latest.accession, r.first.filed, r.latest.filed,
        "basic weighted average (no cover count)" + (f"; {note}" if note else ""),
    )  # fmt: skip


# --- Series and implied float ----------------------------------------------------------------


def series_values(
    engine: sqlite3.Connection, cik: str, concept: str, ptypes: tuple[str, ...] = ("Q", "FY", "I")
) -> list[ShareValue]:
    norm = normalize_cik(cik) or cik
    out = []
    for r in get_series(engine, norm, concept):
        if r.ptype not in ptypes:
            continue
        value, note = float(r.latest.value), ""
        if r.unit == "shares":
            factor, note = split_note(engine, norm, r.end)
            value *= factor
        out.append(ShareValue(concept, r.end, value, r.ptype, r.start, r.method,
                              r.latest.accession, r.first.filed, r.latest.filed, note))  # fmt: skip
    return sorted(out, key=lambda v: (v.date, v.ptype), reverse=True)


def implied_float(engine: sqlite3.Connection, cik: str) -> list[ShareValue]:
    """Float $ ÷ close on the float date, yearly, labelled "implied" (D-M04-2)."""
    norm = normalize_cik(cik) or cik
    out = []
    for r in get_series(engine, norm, "public_float", "I"):
        close = close_on(engine, norm, r.end)
        base = ShareValue("implied_float", r.end, None, "I", None, r.method, r.latest.accession,
                          r.first.filed, r.latest.filed)  # fmt: skip
        if close is None:
            base.note = f"missing: no close on {r.end} (float ${float(r.latest.value) / 1e6:,.1f}M)"
        else:
            factor, note = split_note(engine, norm, close[1])
            base.value = float(r.latest.value) / close[0] * factor
            base.note = (
                f"implied: float ${float(r.latest.value) / 1e6:,.1f}M ÷ close "
                f"${close[0]:,.2f} on {close[1]}" + (f"; {note}" if note else "")
            )
        out.append(base)
    return sorted(out, key=lambda v: v.date, reverse=True)


@dataclass
class ShareRow:
    series: str
    label: str
    values: list[ShareValue]
    missing: str | None = None  # "missing: <reason>" when no value


def share_rows(engine: sqlite3.Connection, cik: str, keep: int = 4) -> list[ShareRow]:
    """The Financials tab's share block: newest `keep` values per series."""
    norm = normalize_cik(cik) or cik
    rows = []
    covers = cover_counts(engine, norm)
    if not covers:
        latest = latest_periodic(engine, norm)
        state = r1_outcome(engine, latest["accession"]) if latest else None
        fb = (basic_fallback(engine, norm, latest["report_date"])
              if latest and latest["report_date"] and state and state.get("outcome") == "not_cover"
              else None)  # fmt: skip
        reason = f"missing: {cover_missing_reason(engine, norm)}"
        rows.append(ShareRow("shares_cover", SERIES_LABELS["shares_cover"],
                             [fb] if fb else [], None if fb else reason))  # fmt: skip
    else:
        rows.append(ShareRow("shares_cover", SERIES_LABELS["shares_cover"], covers[:keep]))
    flows = ("Q", "FY")
    for concept, ptypes in (
        ("shares_period_end", ("I",)),
        ("shares_basic_wavg", flows),
        ("shares_diluted_wavg", flows),
        ("sbc", flows),
    ):
        vals = series_values(engine, norm, concept, ptypes)[:keep]
        tags = ", ".join(f"{t}:{g}" for t, g in CONCEPT_BY_NAME[concept].tags)
        why = None if vals else f"missing: none of {tags} reported"
        rows.append(ShareRow(concept, SERIES_LABELS[concept], vals, why))
    floats = implied_float(engine, norm)[:keep]
    why = None if floats else "missing: no dei:EntityPublicFloat stored"
    rows.append(ShareRow("implied_float", SERIES_LABELS["implied_float"], floats, why))
    return rows
