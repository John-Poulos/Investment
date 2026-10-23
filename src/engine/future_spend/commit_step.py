"""M05 Part 2 inside the refresh and the `commitments` script (D-M05-18…; rules 5–8).

`commitments_pass` (local, 0 requests): after M05 Part 1's pass (MVP_PLAN local-step order,
M05 before M06 / M03 / M07). Per covered name: the channel and the M04 routing (not
applicable → one missing row), the text finder over the stored 10-K / 10-Q main documents
and the purchase-obligation tags (`commitments.scan_company`), the company's
`future_commitment` rows replaced and the `commitment_cover` row written, in one short
transaction per name (LESSONS: the app writes too).

Weights (signals-out table): fabless and outsourced → MY ✓, PT ✓, ST info (R9: commitments
lead); every other channel and "channel unset" → info in every timeframe.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from engine.financials import models as models_mod
from engine.future_spend import channels as channels_mod
from engine.future_spend import commitments as cm
from engine.future_spend.step import ALL, Out, not_applicable, write_rows
from engine.sec.identity import normalize_cik
from engine.signals import Source

SIGNAL = "commitment_cover"
LEAD_INFO = ("ST",)


@dataclass
class CommitResult:
    ticker: str
    cik: str
    channel: channels_mod.Channel
    rows: list[Out]
    cover: cm.Cover | None = None
    scan: cm.CompanyScan | None = None
    not_applicable: str | None = None

    def row(self, signal: str = SIGNAL) -> Out | None:
        return next((o for o in self.rows if o.signal == signal), None)


def info_for(ch: channels_mod.Channel) -> tuple[str, ...]:
    return LEAD_INFO if ch.commitments_lead else ALL


def newest_period(engine: sqlite3.Connection, cik: str) -> str | None:
    ends = [r.period_end for r in cm.reports(engine, cik) if r.period_end]
    return max(ends) if ends else None


def name_result(
    engine: sqlite3.Connection,
    ticker: str,
    cik: str,
    now: datetime,
    *,
    chf: channels_mod.ChannelFile,
    mf: models_mod.ModelFile,
    scan: cm.CompanyScan | None = None,
) -> CommitResult:
    """With `scan`, replace the company's `future_commitment` rows first (caller owns the
    transaction); without it (the app), read the stored rows only."""
    norm = normalize_cik(cik) or cik
    day = now.date().isoformat()
    ch = chf.for_company(norm, ticker)
    newest = newest_period(engine, norm)
    na, how, tag = not_applicable(engine, ch, mf, norm, ticker, newest)
    r = CommitResult(ticker, norm, ch, [])
    if na is not None:
        r.not_applicable = na
        r.rows.append(Out(SIGNAL, day, f"{how}; {ch.text()}", missing=na, info=ALL))
        return r
    if scan is not None:
        r.scan = scan
        cm.store(engine, scan, now)
        newest = scan.newest_period or newest
    c = cm.cover(engine, norm, ch, newest)
    r.cover = c
    method = cm.method_text(c, ch) + (f"; M04 tag {tag}" if tag else "")
    info = info_for(ch)
    srcs: list[Source] = []
    if c.point is not None:
        srcs.append(Source(c.point.accession, c.point.filed, "A",
                           f"commitments ({c.point.label})"))  # fmt: skip
    if c.denom is not None and c.denom.accession:
        srcs.append(Source(c.denom.accession, c.denom.filed, "A", c.denom.what))
    as_of = max((s.date for s in srcs if s.date), default=day)
    if c.missing is not None or c.value is None:
        reason = c.missing or "no cover"
        if cm.scan_state(engine, norm) is None:
            reason = "commitments pass not run (scripts/run_m05.py commitments or the refresh)"
        r.rows.append(Out(SIGNAL, as_of, method, missing=reason, sources=srcs, info=info))
        return r
    r.rows.append(Out(SIGNAL, as_of, method, value=round(c.value, 4), text=c.state,
                      sources=srcs, info=info))  # fmt: skip
    return r


@dataclass
class CommitPass:
    results: dict[str, CommitResult]
    written: int = 0
    stored: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    channel_error: str = ""


def commitments_pass(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    chf: channels_mod.ChannelFile | None = None,
    mf: models_mod.ModelFile | None = None,
) -> CommitPass:
    """Every covered name (0 requests); one name's error does not stop the others."""
    chf = chf if chf is not None else channels_mod.load_safe()
    mf = mf if mf is not None else models_mod.load_safe()
    cp = CommitPass({}, channel_error=chf.error)
    for ticker, cik in sorted(companies.items()):
        if not cik:
            continue
        try:
            norm = normalize_cik(cik) or cik
            ch = chf.for_company(norm, ticker)
            na, _, _ = not_applicable(engine, ch, mf, norm, ticker, newest_period(engine, norm))
            # the scan reads only (corpus text, facts): outside the write transaction
            scan = None if na else cm.scan_company(engine, corpus, norm, now.date().isoformat())
            engine.execute("BEGIN")
            try:
                r = name_result(engine, ticker, cik, now, chf=chf, mf=mf, scan=scan)
                n = write_rows(engine, r)  # type: ignore[arg-type]  # same fields as NameResult
                engine.execute("COMMIT")
            except Exception:
                engine.execute("ROLLBACK")
                raise
            cp.results[ticker] = r
            cp.written += n
            cp.stored += r.scan.rows_written if r.scan else 0
        except Exception as e:
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            cp.errors[ticker] = f"{type(e).__name__}: {e}"
    return cp


def line(r: CommitResult) -> str:
    if r.not_applicable:
        return f"{r.ticker}: commitment_cover {r.not_applicable}"
    o = r.row()
    head = f"{r.ticker} [{r.channel.channel}]: commitment_cover "
    if o is None:
        return head + "—"
    if o.missing is not None:
        return head + f"missing: {o.missing}"
    c = r.cover
    extra = ""
    if c is not None and c.point is not None and c.denom is not None:
        extra = (f" ({cm._m(c.point.amount)} {c.point.label} ÷ {c.denom.what} "
                 f"{cm._m(c.denom.value)} at {c.point.as_of})")  # fmt: skip
    weight = "info" if set(o.info) == set(ALL) else "✓ MY/PT"
    return head + f"{o.text} {o.value:.2f} years{extra} · {weight}"


def reason_key(reason: str) -> str:
    """A set-aside reason without its dates or detail (the per-filing count line)."""
    return re.sub(r" as of \d{4}-\d{2}-\d{2}|;.*$", "", reason).split(" (")[0]


def detail_lines(r: CommitResult, quote_chars: int = 240, *, verbose: bool = False) -> list[str]:
    """Tags found, then per stored 10-K / 10-Q one count line (taken, set aside by reason),
    every sentence taken and the set-aside sentences that carry a dollar amount; filings
    with no stored main document collapse into one count (LESSONS: short live logs).
    `verbose` prints every set-aside sentence and every filing, as before."""
    out = []
    s = r.scan
    if s is None:
        return out
    if s.xbrl:
        for tag, pts in sorted(s.xbrl.items()):
            last = pts[-1]
            out.append(f"    tag {tag}: {len(pts)} instants, last {cm._m(float(last.value))} at "
                       f"{last.end} ({last.accession})")  # fmt: skip
    else:
        out.append("    tags: none of the purchase-obligation tags stored")
    if not s.reports:
        out.append("    reports: no stored 10-K / 10-Q in the filing index")
    no_text = 0
    for rs in s.reports:
        rep = rs.report
        head = f"    {rep.form} {rep.accession} (period {rep.period_end or '?'}, filed {rep.filed})"
        if rs.no_text:
            no_text += 1
            if verbose:
                out.append(head + ": no stored main document")
            continue
        by: dict[str, int] = {}
        for a in rs.set_aside:
            k = reason_key(a.reason)
            by[k] = by.get(k, 0) + 1
        why = "; ".join(f"{k} {v}" for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0])))
        out.append(
            head
            + f": {len(rs.findings)} taken, {len(rs.set_aside)} set aside"
            + (f" ({why})" if why else "")
            + (f", {rs.unverified} unverified (not stored)" if rs.unverified else "")
        )
        for f in rs.findings:
            flags = [x for x, on in (("cancellable", f.cancellable),
                                     (f"after the period {f.stated_date or ''}".strip(),
                                      f.after_period)) if on]  # fmt: skip
            q = f.quote[:quote_chars] + ("…" if len(f.quote) > quote_chars else "")
            out.append(
                f"      taken {cm.CATEGORY_LABEL[f.category]} {cm._m(f.amount)} at {f.as_of}"
                + (f" [{', '.join(flags)}]" if flags else "")
                + f": “{q}”"
            )
        for a in rs.set_aside:
            if not (verbose or a.raw):
                continue
            q = a.quote[:160] + ("…" if len(a.quote) > 160 else "")
            out.append(f"      set aside ({a.reason}{'; ' + a.raw if a.raw else ''}): “{q}”")
    if no_text and not verbose:
        out.append(f"    {no_text} older filing(s) with no stored main document")
    if s.duplicates:
        out.append(f"    {s.duplicates} repeated row key(s) skipped at store")
    c = r.cover
    if c is not None:
        for x in c.leases + c.after_period + c.deposits + c.stale + c.marks:
            out.append(f"    line: {x}")
    return out


def summary_lines(cp: CommitPass) -> list[str]:
    states: dict[str, int] = {}
    missing = 0
    weighted = []
    for r in cp.results.values():
        o = r.row()
        if o is None:
            continue
        if o.missing is not None:
            missing += 1
        else:
            states[o.text or "?"] = states.get(o.text or "?", 0) + 1
            if set(o.info) != set(ALL):
                weighted.append(r.ticker)
    out = [
        f"M05 commitments: {len(cp.results)} names; {cp.written} signal rows, {cp.stored} "
        f"future_commitment rows, {missing} missing covers",
        "  commitment_cover "
        + (", ".join(f"{k} {v}" for k, v in sorted(states.items())) or "—"),  # fmt: skip
        "  carries weight (fabless / outsourced, MY and PT): "
        + (", ".join(sorted(weighted)) or "none"),
    ]
    if cp.channel_error:
        out.append(f"  channel file rejected, every company read as unset: {cp.channel_error}")
    out += [f"  {t}: error — {e}" for t, e in sorted(cp.errors.items())]
    return out


def run_local_part(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """The refresh hook (after M05 Part 1's pass, before M07). Never fails."""
    t0 = clock()
    try:
        lines = summary_lines(commitments_pass(engine, corpus, companies, now))
    except Exception as e:
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        lines = [f"  M05 commitments: error — {type(e).__name__}: {e}"]
    return [f"M05 commitments — local pass (Part 2, 0 requests) ({clock() - t0:.1f} s):", *lines]
