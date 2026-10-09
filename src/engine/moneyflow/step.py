"""The money-flow step of a refresh run (M02 part 3). Never fails the run.

1. Stated capex actuals from every stored release and call (local).
2. Extension facts from XBRL instances (SEC, one request per new 10-K/10-Q) for
   companies with an override recipe or financing coverage below 80%.
3. Per company: capex guidance lines with freshness, actuals and reconciliation
   (`m02_capex_gap` on an exact recipe more than 1% off), capital allocation
   (`m02_tag` items when coverage < 80%), spender→theme sentences (`m02_spender`).
4. Annual capex frames (SEC, refreshed every 30 days) → spender candidates
   (`m02_candidate`, weekly cap, largest first).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from datetime import datetime

from engine.moneyflow import instance, links, spenders, stated
from engine.moneyflow.actuals import Book, actual_for, latest_clause, overrides_by_cik
from engine.moneyflow.allocation import COVERAGE_MIN, allocation, raise_tag_items
from engine.moneyflow.guided import guided_lines
from engine.moneyflow.views import _quarter_labels, money
from engine.sec.client import SecClient
from engine.themes import proposals, tiers


def _gap_items(
    engine: sqlite3.Connection, cik: str, ticker: str, clause: str | None, override, now
) -> list[str]:
    book = Book(engine, cik)
    st = stated.stated_for(engine, cik)
    out = []
    for label in _quarter_labels(book) + sorted({p.split()[0] for p in st}):
        a = actual_for(book, label, clause, override, st)
        if a.status not in ("gap", "doubtful statement") or a.gap is None or a.stated is None:
            continue
        shown = (
            "the recipe is shown: a gap this large usually means the sentence was misread "
            "(a year or year-to-date figure, another item)"
            if a.status == "doubtful statement"
            else "the stated figure is shown (D-M02-32)"
        )
        payload = {
            "ticker": ticker,
            "period": label,
            "recipe": a.recipe.value,
            "recipe_label": a.recipe.recipe.label,
            "how": a.recipe.how,
            "stated": a.stated.value,
            "quote": a.stated.quote,
            "gap": a.gap,
            "why": f"recipe {money(a.recipe.value)} vs stated {money(a.stated.value)} "
            f"({a.gap:+.1%}); {shown}. If the "
            "company's definition differs, add a section to "
            "config/capex_definitions.toml.",
        }
        res = proposals.propose(
            engine,
            "m02_capex_gap",
            f"{cik}:{label}",
            f"{ticker} {label}: capex recipe {a.gap:+.1%} off the stated figure",
            payload,
            now,
            cik=cik,
        )
        if res in ("queued", "overflow"):
            out.append(f"{label} {a.gap:+.1%}")
    return out


def company_lines(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection | None,
    cik: str,
    ticker: str,
    now: datetime,
    override=None,
) -> list[str]:
    """Live-check summary for one company (also used by scripts/run_money.py)."""
    out = [f"  {ticker}:"]
    for g in guided_lines(engine, cik, now.date(), corpus, override):
        state = "ended" if g.ended else g.freshness.state
        out.append(
            f"    guidance {g.period}: {g.value_text} [{g.source_text}] growth "
            f"{g.growth_text}; {state}"
        )
    book = Book(engine, cik)
    clause = latest_clause(engine, cik)
    st = stated.stated_for(engine, cik)
    for label in _quarter_labels(book)[:4]:
        a = actual_for(book, label, clause, override, st)
        rec = f"{money(a.recipe.value)}{' ≈' if a.recipe.approximate else ''}" if a.recipe else "—"
        sv = money(a.stated.value) if a.stated else "—"
        out.append(
            f"    actual {label}: recipe {rec}, stated {sv}, shown {money(a.shown)} ({a.label})"
        )
    for w in allocation(engine, cik, clause, override):
        cover = w.ocf_cover_text
        out.append(
            f"    allocation {w.label}: OCF {money(w.ocf)}, capex {money(w.capex)}, "
            f"OCF÷capex {cover}, net debt {money(w.net_debt)}, net equity "
            f"{money(w.net_equity)}; {w.coverage_text}"
            + (f"; unmapped {len(w.unmapped)}" if w.unmapped else "")
        )
    return out


def run_money_step(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    detail: bool = False,
) -> list[str]:
    lines = ["Money flow (M02 part 3):"]
    try:
        n = stated.scan_all(engine, corpus)
        lines.append(f"stated capex actuals: {n} sentence(s) from stored releases and calls")
        overrides = overrides_by_cik(engine)
        for ticker, cik in sorted(companies.items()):
            clause = latest_clause(engine, cik)
            windows = allocation(engine, cik, clause, overrides.get(cik))
            low = any(w.coverage is not None and w.coverage < COVERAGE_MIN for w in windows)
            if client is not None and (cik in overrides or low):
                read, new, problems = instance.sync_instances(client, engine, cik, now)
                if read or problems:
                    lines.append(
                        f"  {ticker}: XBRL instances read {read}, extension facts "
                        f"{new}" + (f"; problems: {'; '.join(problems)}" if problems else "")
                    )
                windows = allocation(engine, cik, clause, overrides.get(cik))
            tags = raise_tag_items(engine, cik, ticker, windows, now)
            gaps = _gap_items(engine, cik, ticker, clause, overrides.get(cik), now)
            found = links.scan_company(engine, corpus, cik, now)
            linked = links.store_and_propose(engine, cik, ticker, found, now)
            if tags or gaps or found:
                lines.append(
                    f"  {ticker}: tag items {tags}; recipe gaps {gaps or 'none'}; "
                    f"theme sentences {len(found)} {linked or ''}".rstrip()
                )
            m = tiers.member(engine, cik)
            if (
                m
                and m.tier == "tracked"
                and links.company_links(engine, cik)
                and any(r["status"] == "confirmed" for r in links.company_links(engine, cik))
            ):
                proposals.suggest_promotion(
                    engine, cik, "confirmed spending link to a theme", "money_flow", now
                )
            if detail:
                lines += company_lines(engine, corpus, cik, ticker, now, overrides.get(cik))
        year = now.year - 1
        if client is not None:
            problems = spenders.fetch_frames(client, engine, [year - 1, year], now)
            lines += [f"  frames: {p}" for p in problems]
        rows, total = spenders.spenders(engine, year)
        lines.append(
            f"capex frames CY{year}: {len(rows)} filers"
            + (f", all-filer capex {money(total)}" if total else " (not stored)")
        )
        exclude = set(companies.values()) | {m.cik for m in tiers.members(engine)}
        counts = spenders.propose_candidates(engine, year, exclude, now)
        lines.append(f"spender candidates: {dict(Counter(counts)) or 'none new'}")
    except Exception as e:  # the money-flow step must not break the run report
        lines.append(f"error — {type(e).__name__}: {e}")
    return lines
