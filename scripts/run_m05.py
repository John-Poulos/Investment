"""M05 Capex & future spend: one owner script, one subcommand per build part (M05 Parts 1–2).

    uv run python scripts/run_m05.py demand --no-sec       # Part 1 live check (0 requests)
    uv run python scripts/run_m05.py export                # fixture export from stored facts (0)
    uv run python scripts/run_m05.py commitments --no-sec  # Part 2 live check (0 requests)
    uv run python scripts/run_m05.py export-text           # fixture export from stored text (0)
    uv run python scripts/run_m05.py --list                # the subcommand table

`commitments` (Part 2): the text finder over the stored 10-K / 10-Q main documents and the
purchase-obligation tags (per tag, D-SEC-31) for every covered name, the company's
`future_commitment` rows replaced, `commitment_cover` written; the log lists per name the
tags found and every sentence taken or set aside, with the reason, and the lease,
after-period, deposit and stale-tag lines. 0 requests (`--no-sec` changes nothing).

`export-text` (Part 2, 0 requests): trimmed excerpts (each commitment or deposit sentence
with one sentence either side) of the newest stored 10-K and 10-Q of NVDA, META and MU
(`--tickers` to change), as JSON in logs/, for the owner to send back as fixtures.

`demand` (Part 1): computes from stored facts and M04 rows (0 requests; `--no-sec` is
accepted for the D-M04-69 pattern and changes nothing, since the subcommand never calls
SEC) the three M05 rows — `capex_demand` (with the rule-4 capex vote), `growth_capex_roic`,
`bookings_cover` — for every covered name (watchlist, promoted and tracked), writes them,
and prints one line per name, the deposits line, the 8-FY capex ÷ depreciation strip of the
brief's companies, and the brief's worked-example figures to compare.

`export` (0 requests): writes the stored `fact` rows of the tags the Part 1 fixtures lack
(capex, depreciation, D&A, revenue, contract liabilities, RPO, OCF) for MU, INTC and MSFT
(`--tickers` to change) as trimmed companyfacts JSON in logs/, for the owner to send back
(Claude cannot read data\\; the files become fixtures in a later part).

Takes data/refresh.lock (one data-writing run at a time). Writes
logs/m05_<subcommand>_<YYYYMMDD-HHMMSS>.txt as it goes; the console shows the summary only.
Its own tracebacks go to the log too, so the log is all the owner sends back.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SUBCOMMANDS = (
    ("demand", "1", "capex_demand (+ vote), growth_capex_roic, bookings_cover; deposits line"),
    ("export", "1", "stored facts of MU, INTC, MSFT capex/depreciation/deposit tags (fixtures)"),
    ("commitments", "2", "commitment_cover, lease and post-period lines"),
    ("export-text", "2", "stored 10-K / 10-Q commitment and deposit excerpts (fixtures)"),
)
BUILT = {"demand", "export", "commitments", "export-text"}
SUMMARY_MARK = "=== Summary"
CONSOLE_ALWAYS = ("Log written to:", "FAILED", "Export written to:")
COUNTED_TABLES = ("signal",)
COMMIT_TABLES = ("signal", "future_commitment")
TEXT_TICKERS = ("NVDA", "META", "MU")
# The brief's commitment figures (docs/mvp/M05_MVP_BRIEF.md; docs/M05_FUTURE_SPEND.md Part 2).
COMMIT_CHECKPOINTS = (
    ("NVDA", "10-K FY2026: supply and capacity $95.2B ÷ TTM cost of revenue $62.48B = 1.52 "
     "years (cloud $27.0B, investments $11.4B, other $3.4B beside); 10-Q Q2 FY2027: $279B ÷ "
     "$76.73B = 3.64 years short_history (us-gaap:PurchaseObligation $45.77B at 2025-07-27 "
     "across a labelled break; tag stopped); cancellable flag set; MY/PT ✓"),
    ("META", "hyperscaler → PP&E numerator ÷ TTM capex, info; leases not yet commenced a "
     "separate line; July 2026 leases (about $68B) signed after the period; Unrecorded… tag "
     "labelled by the lease quote if amounts match"),
    ("MU", "customer deposit wording found (deposits mark, rule 6); PP&E commitments ÷ TTM "
     "capex, info"),
)  # fmt: skip
STRIP_TICKERS = ("MU", "INTC", "MSFT")
# The brief's worked example (docs/mvp/M05_MVP_BRIEF.md; docs/M05_FUTURE_SPEND.md "Live
# checks"), to compare with the lines above them.
CHECKPOINTS = (
    ("MU", "FY2022 1.72 BUILD_INTO_DEMAND (median 1.61); FY2023 1.00 CUTTING (capex ÷ revenue "
     "49.4% = 1.30× its 3-yr average, no M04 pointer); FY2024 1.09 MAINTENANCE (1.68); FY2025 "
     "1.92 BUILD (1.56); FY2026 3.26 BUILD_INTO_DEMAND (1.68); deposits $13.0B vs $169M"),
    ("INTC", "2023 capex ÷ revenue 1.75× its 3-yr average while revenue fell → AHEAD_OF_DEMAND, "
     "if its 2020–23 capex and revenue are stored; 2022 growth share 55%"),
    ("MSFT", "bookings_cover 1.33 → 2.06 (+55%) RISING; capex ÷ depreciation FY2026 3.38 "
     "(FY2025 2.93), capex_demand possibly INSUFFICIENT_HISTORY (no long depreciation series)"),
)  # fmt: skip
EXPORT_TAGS = (
    "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
    "Depreciation", "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet", "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
    "ContractWithCustomerLiability", "ContractWithCustomerLiabilityCurrent",
    "ContractWithCustomerLiabilityNoncurrent", "DeferredRevenue", "DeferredRevenueCurrent",
    "DeferredRevenueNoncurrent", "RevenueRemainingPerformanceObligation",
    "NetCashProvidedByUsedInOperatingActivities",
)  # fmt: skip


class Log:
    """Every line goes to the log file; the console shows the "=== Summary" block onward,
    failures and the log path."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(exist_ok=True)
        self._fh = path.open("w", encoding="utf-8")
        self._echo = False

    def __call__(self, *lines: str) -> None:
        for line in lines:
            if line.startswith((SUMMARY_MARK, "FAILED")):
                self._echo = True
            if self._echo or line.startswith(CONSOLE_ALWAYS):
                print(line)
            self._fh.write(line + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def counts(engine) -> dict[str, int]:
    return {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COUNTED_TABLES}


def companies(engine) -> dict[str, str]:
    """Covered names: watchlist (core) + active tier members (promoted, tracked)."""
    from engine.calls.transcripts import symbol_cik
    from engine.refresh import load_config
    from engine.themes import tiers

    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def strip_lines(r) -> list[str]:
    from engine.future_spend import demand

    s = r.series
    if s is None or not s.years:
        return [f"  {r.ticker}: no total capex stored"]
    out = [
        f"  {r.ticker} (rung: {demand.RUNG_NAME.get(s.rung, 'not split')}; "
        f"{len(s.years)} fiscal years with capex, {s.years[0].label}–{s.years[-1].label}):"
    ]
    for d in demand.strip(s):
        ratio = f"{d.ratio:.2f}" if d.ratio is not None else "—"
        med = f"{d.median:.2f}" if d.median is not None else "—"
        inten = (f"{d.intensity:.1%} ({d.intensity / d.intensity_avg:.2f}× its 3-FY avg)"
                 if d.intensity is not None and d.intensity_avg else
                 f"{d.intensity:.1%}" if d.intensity is not None else "—")  # fmt: skip
        out.append(f"    {d.label}: capex ÷ rung {ratio}, median {med}, capex "
                   f"{demand._pct(d.capex_yoy)}, revenue {demand._pct(d.rev_yoy)}, capex ÷ revenue "
                   f"{inten} → {d.state or 'missing: ' + str(d.missing)}")  # fmt: skip
    return out


def run_demand(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    """The Part 1 check. `engine` and `now` are injected by tests (never the real DB)."""
    from engine.future_spend import channels as channels_mod
    from engine.future_spend import step
    from engine.store.db import open_db

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    now = now or datetime.now(UTC)
    t0 = time.monotonic()
    before = counts(engine)
    comps = companies(engine) if args.companies is None else args.companies
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    chf = channels_mod.load_safe(ROOT / "config" / "m05_channels.toml")
    log(f"run_m05 demand · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} names · 0 requests"
        + (" · --no-sec" if args.no_sec else ""), "")  # fmt: skip
    if chf.error:
        log(f"channel file rejected, every company read as unset: {chf.error}")
    fp = step.future_spend_pass(engine, comps, now, chf=chf)
    log("Per name:")
    for t in sorted(fp.results):
        log("  " + step.line(fp.results[t]))
    for t, e in sorted(fp.errors.items()):
        log(f"  {t}: error — {e}")
    log("", "Missing rows (reason per signal):")
    miss = [f"  {r.ticker} {o.signal}: missing: {o.missing}" for r in fp.results.values()
            for o in r.rows if o.missing]  # fmt: skip
    log(*(miss or ["  none"]))
    log("", "Deposits (contract liabilities; repayable, not revenue):")
    for t in sorted(fp.results):
        r = fp.results[t]
        if r.deposits is not None and r.deposits.now is not None:
            log(f"  {t}: {r.deposits.text()}")
    log("", "Capex ÷ depreciation strip (brief's companies):")
    for t in STRIP_TICKERS:
        if t in fp.results:
            log(*strip_lines(fp.results[t]))
    log("", "Brief's worked example (compare with the lines above):")
    for who, what in CHECKPOINTS:
        log(f"  {who}: {what}")
    after = counts(engine)
    log("", SUMMARY_MARK)
    log(*step.summary_lines(fp))
    log(f"SEC requests: 0 · other requests: 0 · {time.monotonic() - t0:.1f} s")
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after))
    if own:
        engine.close()
    return 0


def export_facts(engine, cik: str, name: str) -> dict:
    """Stored `fact` rows of EXPORT_TAGS in SEC companyfacts layout (0 requests)."""
    facts: dict[str, dict] = {}
    marks = ",".join("?" * len(EXPORT_TAGS))
    for r in engine.execute(
        f"SELECT taxonomy, tag, unit, period_start, period_end, value, accession, form, filed, "
        f"fy, fp, frame FROM fact WHERE cik = ? AND tag IN ({marks}) ORDER BY taxonomy, tag, "
        "unit, period_end, filed",
        (cik, *EXPORT_TAGS),
    ):
        unit = facts.setdefault(r[0], {}).setdefault(r[1], {"units": {}})["units"]
        row = {"end": r[4], "val": r[5], "accn": r[6], "form": r[7], "filed": r[8]}
        if r[3]:
            row = {"start": r[3]} | row
        for k, v in (("fy", r[9]), ("fp", r[10]), ("frame", r[11])):
            if v is not None:
                row[k] = v
        unit.setdefault(r[2], []).append(row)
    return {"cik": int(cik), "entityName": name, "facts": facts}


def run_export(args, log: Log, folder: Path, engine=None, now: datetime | None = None) -> int:
    from engine.calls.transcripts import symbol_cik
    from engine.store.db import open_db

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    now = now or datetime.now(UTC)
    tickers = [t.strip().upper() for t in (args.tickers or ",".join(STRIP_TICKERS)).split(",")]
    log(f"run_m05 export · {now:%Y-%m-%d %H:%M} UTC · {', '.join(tickers)} · 0 requests", "")
    out_dir = args.out_dir or (ROOT / "logs")
    written = []
    for t in tickers:
        cik = symbol_cik(engine, t)
        if cik is None:
            log(f"  {t}: no CIK resolved, skipped")
            continue
        row = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
        data = export_facts(engine, cik, row[0] if row else t)
        n = sum(len(v) for tags in data["facts"].values() for u in tags.values()
                for v in u["units"].values())  # fmt: skip
        path = Path(out_dir) / f"m05_export_{t.lower()}_{now:%Y%m%d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
            fh.write("\n")
        tags = sorted(g for tags in data["facts"].values() for g in tags)
        log(f"  {t} ({cik}): {n} facts, tags {', '.join(tags) or 'none'}")
        written.append(path)
    log("", SUMMARY_MARK, f"{len(written)} export file(s); SEC requests: 0")
    for p in written:
        log(f"Export written to: {p}")
    if own:
        engine.close()
    return 0


def run_commitments(
    args, log: Log, folder: Path, engine=None, corpus=None, now: datetime | None = None
) -> int:
    """The Part 2 check. `engine`, `corpus` and `now` are injected by tests (never the real DB)."""
    from engine.future_spend import channels as channels_mod
    from engine.future_spend import commit_step
    from engine.store.db import open_db

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    corpus = corpus if corpus is not None else open_db("corpus", folder)
    now = now or datetime.now(UTC)
    t0 = time.monotonic()
    before = {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COMMIT_TABLES}
    comps = companies(engine) if args.companies is None else args.companies
    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",")}
        comps = {t: c for t, c in comps.items() if t in wanted}
    chf = channels_mod.load_safe(ROOT / "config" / "m05_channels.toml")
    log(f"run_m05 commitments · {now:%Y-%m-%d %H:%M} UTC · {len(comps)} names · 0 requests"
        + (" · --no-sec" if args.no_sec else ""), "")  # fmt: skip
    if chf.error:
        log(f"channel file rejected, every company read as unset: {chf.error}")
    cp = commit_step.commitments_pass(engine, corpus, comps, now, chf=chf)
    log(
        "Per name (cover line, tags found, per filing the counts by reason, every sentence taken, "
        "set-aside sentences with a dollar amount; --verbose prints all):"
    )
    for t in sorted(cp.results):
        r = cp.results[t]
        verbose = bool(getattr(args, "verbose", False))
        log("  " + commit_step.line(r), *commit_step.detail_lines(r, verbose=verbose))
    for t, e in sorted(cp.errors.items()):
        log(f"  {t}: error — {e}")
    log("", "Brief's figures (compare with the lines above):")
    for who, what in COMMIT_CHECKPOINTS:
        log(f"  {who}: {what}")
    after = {t: engine.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COMMIT_TABLES}
    log("", SUMMARY_MARK)
    log(*commit_step.summary_lines(cp))
    log(f"SEC requests: 0 · other requests: 0 · {time.monotonic() - t0:.1f} s")
    log("Rows added per table: " + ", ".join(f"{t} {after[t] - before[t]:+,}" for t in after)
        + " (future_commitment rows are replaced per company on every pass)")  # fmt: skip
    if own:
        engine.close()
        corpus.close()
    return 0


def text_excerpts(text: str, pad: int = 1) -> list[tuple[int, int]]:
    """Spans around every commitment or deposit hit: the sentence plus `pad` sentences each
    side, merged (the trimmed passages a fixture needs)."""
    from engine.financials.text import sentence_at
    from engine.future_spend import commitments as cm

    spans: list[tuple[int, int]] = []
    hits = [m.start() for rx in (cm.TRIGGER, cm.DEPOSIT) for m in rx.finditer(text)]
    for pos in sorted(hits):
        a, b = sentence_at(text, pos)
        for _ in range(pad):
            if a > 0:
                a = sentence_at(text, max(0, a - 2))[0]
            if b < len(text):
                b = sentence_at(text, min(len(text) - 1, b + 1))[1]
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], b))
        else:
            spans.append((a, b))
    return spans


def run_export_text(
    args, log: Log, folder: Path, engine=None, corpus=None, now: datetime | None = None
) -> int:
    """0 requests: trimmed commitment / deposit excerpts of the newest stored 10-K and 10-Q."""
    from engine.calls.transcripts import symbol_cik
    from engine.financials.text import docs_for
    from engine.future_spend import commitments as cm
    from engine.store.db import open_db

    own = engine is None
    engine = engine if engine is not None else open_db("engine", folder)
    corpus = corpus if corpus is not None else open_db("corpus", folder)
    now = now or datetime.now(UTC)
    tickers = [t.strip().upper() for t in (args.tickers or ",".join(TEXT_TICKERS)).split(",")]
    log(f"run_m05 export-text · {now:%Y-%m-%d %H:%M} UTC · {', '.join(tickers)} · 0 requests", "")
    out_dir = args.out_dir or (ROOT / "logs")
    written = []
    for t in tickers:
        cik = symbol_cik(engine, t)
        if cik is None:
            log(f"  {t}: no CIK resolved, skipped")
            continue
        picked = []
        for form in ("10-K", "10-Q"):
            rep = next((r for r in cm.reports(engine, cik) if r.form.startswith(form)), None)
            if rep is not None:
                picked.append(rep)
        out = {"ticker": t, "cik": cik, "exported": now.isoformat(timespec="seconds"),
               "note": "trimmed excerpts of stored text for M05 Part 2 fixtures (0 requests)",
               "documents": []}  # fmt: skip
        for rep in picked:
            docs = [
                d for d in docs_for(corpus, rep.accession) if cm._main_doc(d.doc_type, rep.form)
            ]
            if not docs:
                log(f"  {t} {rep.form} {rep.accession}: no stored main document")
                continue
            d = docs[0]
            spans = text_excerpts(d.text)
            out["documents"].append({
                "accession": rep.accession, "form": rep.form, "filed": rep.filed,
                "period_end": rep.period_end, "filename": d.filename, "doc_type": d.doc_type,
                "excerpts": [{"start": a, "end": b, "text": d.text[a:b]} for a, b in spans],
            })  # fmt: skip
            log(f"  {t} {rep.form} {rep.accession} (period {rep.period_end}): {len(spans)} "
                f"excerpt(s), {sum(b - a for a, b in spans):,} characters")  # fmt: skip
        path = Path(out_dir) / f"m05_text_{t.lower()}_{now:%Y%m%d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        written.append(path)
    log("", SUMMARY_MARK, f"{len(written)} export file(s); SEC requests: 0")
    for p in written:
        log(f"Export written to: {p}")
    if own:
        engine.close()
        corpus.close()
    return 0


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("subcommand", nargs="?", choices=[s for s, _, _ in SUBCOMMANDS])
    ap.add_argument(
        "--no-sec",
        action="store_true",
        help="accepted for the D-M04-69 pattern; no M05 subcommand calls SEC",
    )
    ap.add_argument("--tickers", help="comma-separated subset")
    ap.add_argument("--list", action="store_true", help="print the subcommand table")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="commitments: print every set-aside sentence and every filing",
    )
    args = ap.parse_args(argv)
    args.companies = None
    args.out_dir = None
    if args.list or not args.subcommand:
        for name, part, what in SUBCOMMANDS:
            print(f"{name:12} Part {part:2} {what}" + ("" if name in BUILT else "  (not built)"))
        return 0 if args.list else 2
    if args.subcommand not in BUILT:
        print(f"{args.subcommand}: not built")
        return 2
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.chdir(ROOT)  # data/, config/ and logs/ are relative to the repo
    from engine.store.db import data_dir

    log = Log(ROOT / "logs" / f"m05_{args.subcommand}_{datetime.now():%Y%m%d-%H%M%S}.txt")
    print(f"run_m05 {args.subcommand}: working; full detail goes to {log.path}")
    try:
        run = {"demand": run_demand, "export": run_export, "commitments": run_commitments,
               "export-text": run_export_text}[args.subcommand]  # fmt: skip
        return run(args, log, data_dir())
    except Exception:
        log("FAILED with a traceback:", traceback.format_exc())
        return 1
    finally:
        log(f"Log written to: {log.path}")
        log.close()


def main() -> int:
    if any(a in sys.argv[1:] for a in ("--list", "-h", "--help")) or len(sys.argv) < 2:
        return _main()  # no data touched: no lock needed
    if sys.argv[1] not in BUILT:
        return _main()
    from engine.store.lock import run_script

    return run_script(ROOT, "run_m05", _main)


if __name__ == "__main__":
    sys.exit(main())
