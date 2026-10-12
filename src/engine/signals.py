"""D13 signal writer, shared by every module (D-M04-9, D-M04-74; M04 Part 1a).

One row per (cik, module, signal, timeframe, as_of); the ticker is for display only, so two
companies that used the same ticker (BBBY) keep separate rows.

- Numbers go in `value`; enums and states in `value_text`. Text never goes in `value`
  (in a NUMERIC column it sorts above every number). Both may be set (a number with its
  band, e.g. `mscore`).
- Missing: both empty and `method` = "missing: <reason>"; never zero. Grade and source
  may be empty only on such rows.
- `evidence_grade` = the weakest deciding input (A filings and verified quotes; B
  transcripts, third-party data, owner entries without a filing; C rumour).
- `source_ref` = the newest accession, "+N" when there are more; the full input list goes
  in `method`.
- Timeframes listed in `info` are written with "info (weight 0)" in the method (the
  Signals-out table's "info" cells; ST rows of most M04 signals).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from engine.sec.identity import normalize_cik

TIMEFRAMES = ("MY", "PT", "ST")
GRADES = ("A", "B", "C")  # strongest first


@dataclass(frozen=True)
class Source:
    """A deciding input: an accession (or document id), its date and grade."""

    ref: str
    date: str
    grade: str = "A"
    what: str = ""  # e.g. "10-K cover", "dei:EntityPublicFloat"


def weakest(grades: Iterable[str]) -> str | None:
    found = [g for g in grades if g]
    bad = [g for g in found if g not in GRADES]
    if bad:
        raise ValueError(f"unknown evidence grade {bad[0]!r}")
    return max(found, key=GRADES.index) if found else None


def source_ref(sources: Sequence[Source]) -> str | None:
    """Newest input's reference, '+N' for the others."""
    if not sources:
        return None
    ordered = sorted(sources, key=lambda s: (s.date, s.ref), reverse=True)
    extra = len({s.ref for s in ordered}) - 1
    return ordered[0].ref + (f" +{extra}" if extra > 0 else "")


def _inputs(sources: Sequence[Source]) -> str:
    ordered = sorted(sources, key=lambda s: (s.date, s.ref), reverse=True)
    return "; ".join(
        f"{s.ref}{f' ({s.what})' if s.what else ''} {s.date} grade {s.grade}" for s in ordered
    )


def write_signal(
    engine: sqlite3.Connection,
    *,
    cik: str,
    module_id: str,
    signal: str,
    as_of: str,
    method: str,
    value: float | int | None = None,
    value_text: str | None = None,
    sources: Sequence[Source] = (),
    ticker: str | None = None,
    timeframes: Sequence[str] = TIMEFRAMES,
    info: Iterable[str] = (),
    missing: str | None = None,
) -> int:
    """Upsert one row per timeframe. Returns rows written. Caller owns the transaction.

    `missing="<reason>"` writes a missing row (value and text empty)."""
    norm = normalize_cik(cik)
    if norm is None:
        raise ValueError(f"not a CIK: {cik!r}")
    if isinstance(value, bool) or (value is not None and not isinstance(value, int | float)):
        raise TypeError(f"value must be a number, got {type(value).__name__}: text goes in "
                        "value_text (D-M04-9)")  # fmt: skip
    if value_text is not None and not isinstance(value_text, str):
        raise TypeError("value_text must be text")
    info = set(info)
    unknown = [t for t in [*timeframes, *info] if t not in TIMEFRAMES]
    if unknown:
        raise ValueError(f"unknown timeframe {unknown[0]!r}")
    if missing is not None:
        if value is not None or value_text is not None:
            raise ValueError("a missing signal has no value and no value_text")
        text = f"missing: {missing}" + (f"; {method}" if method else "")
        grade, ref = weakest(s.grade for s in sources), source_ref(sources)
    else:
        if value is None and value_text is None:
            raise ValueError("no value: pass missing='<reason>' for a missing signal (never 0)")
        if not sources:
            raise ValueError("a signal with a value needs its deciding inputs (sources)")
        text = method
        grade, ref = weakest(s.grade for s in sources), source_ref(sources)
    if sources:
        text += f"; inputs: {_inputs(sources)}"
    rows = [
        (norm, ticker, module_id, signal, tf, as_of, value, value_text, grade, ref,
         text + ("; info (weight 0)" if tf in info else ""))
        for tf in timeframes
    ]  # fmt: skip
    engine.executemany(
        "INSERT INTO signal (cik, ticker, module_id, signal, timeframe, as_of, value, value_text, "
        "evidence_grade, source_ref, method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (cik, module_id, signal, timeframe, as_of) DO UPDATE SET "
        "ticker = excluded.ticker, value = excluded.value, value_text = excluded.value_text, "
        "evidence_grade = excluded.evidence_grade, source_ref = excluded.source_ref, "
        "method = excluded.method",
        rows,
    )
    return len(rows)


def latest_signal(
    engine: sqlite3.Connection, cik: str, module_id: str, signal: str, timeframe: str = "MY"
) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT * FROM signal WHERE cik = ? AND module_id = ? AND signal = ? AND timeframe = ? "
        "ORDER BY as_of DESC LIMIT 1",
        (normalize_cik(cik) or cik, module_id, signal, timeframe),
    ).fetchone()
