"""One seasonal pass, end to end (D-M02-51, -53…56): used by `scripts/run_seasonal.py` and
by the logon refresh after the owner says Yes.

`prepare()` mines locally (no SEC) and estimates the requests the tests need, for the
refresh's Yes/No box; `run_pass()` does everything: form indexes, year-ago twins, mining,
screen, full tests, closing untested phrases, proposals, candidate companies and the
crowding count of every active theme phrase. Each step is resumable; the time budget and
an SEC throttle stop it cleanly, and the report says how to continue.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from engine.sec.client import SecClient, iso
from engine.themes import mining, seasonal, twins
from engine.themes.seasonal import Season

REQUESTS_PER_S = 2.0  # measured EFTS pace (D-M02-52 (6))


def core_and_promoted(engine: sqlite3.Connection, watchlist: Path) -> dict[str, str]:
    """cik → ticker for the owner's watchlist and promoted names (D-M02-52 (1))."""
    from engine.calls.transcripts import symbol_cik
    from engine.refresh import load_config
    from engine.themes import tiers

    out: dict[str, str] = {}
    for t in load_config(watchlist).tickers:
        if cik := symbol_cik(engine, t):
            out.setdefault(cik, t)
    for m in tiers.members(engine):
        if m.tier == "promoted":
            out.setdefault(m.cik, m.ticker)
    return out


def mine_lines(engine: sqlite3.Connection, corpus: sqlite3.Connection, s: Season,
               comps: dict[str, str], now: datetime) -> list[str]:  # fmt: skip
    res = mining.mine(engine, corpus, comps, s.day, exclude=seasonal.known_phrases(engine))
    added = seasonal.store_mined(engine, s, res, now)
    out = [f"\nmining (current {res.current[0]}..{res.current[1]} vs year ago "
           f"{res.year_ago[0]}..{res.year_ago[1]}): {len(res.compared)} companies compared, "
           f"{res.above_floor} phrases with ≥ 2 new adopters ({res.admin_dropped} more dropped "
           f"as accounting, tax or legal wording), {len(res.candidates)} kept, "
           f"{added} new this run; narrative sections only ({mining.MINER_VERSION})"]  # fmt: skip
    for cik, kinds in sorted(res.compared.items()):
        out.append(f"  {comps.get(cik, cik)}: compared {', '.join(kinds)}")
    for cik, why in sorted(res.not_compared.items()):
        out.append(f"  {comps.get(cik, cik)}: not compared — {why}")
    out.append("  top 50 (adopters − droppers, adopters, phrase):")
    for m in res.candidates[:50]:
        out.append(f"    {m.score:>3} {len(m.adopters):>3}  {m.phrase}  "
                   f"[{', '.join(comps.get(c, c) for c in m.adopters)}]")  # fmt: skip
    return out


@dataclass(frozen=True)
class Prepared:
    season: Season
    candidates: int  # phrases waiting for the screen
    requests: int  # estimate: twins + screen + full tests + theme phrases and crowding
    lines: list[str]

    @property
    def minutes(self) -> int:
        return max(1, round(self.requests / REQUESTS_PER_S / 60))

    def question(self) -> str:
        return (f"Seasonal pass {self.season.key} (due {self.season.day}): {self.candidates} "
                f"candidate phrases mined. Testing needs about {self.requests:,} SEC requests "
                f"(about {self.minutes} min, in the background).\n\nRun it now? No keeps the "
                "reminder; you can run scripts/run_seasonal.py later.")  # fmt: skip


def prepare(engine: sqlite3.Connection, corpus: sqlite3.Connection, s: Season,
            comps: dict[str, str], now: datetime) -> Prepared:  # fmt: skip
    """Local mining and the request estimate (D-M02-51: mine in the refresh, then ask)."""
    seasonal.ensure_run(engine, s, now)
    lines = mine_lines(engine, corpus, s, comps, now)
    todo, _ = twins.plan(engine, corpus, comps, s.day)
    est = seasonal.estimate(engine, s.key)
    themes = len(seasonal.known_phrases(engine))
    requests = 3 * len(todo) + est["screen"] + est["test_max"] + themes * (seasonal.TEST_PAGES + 2)
    cands = seasonal.stage_counts(engine, s.key).get("candidate", 0)
    return Prepared(s, cands, requests, lines)


def theme_crowding(client: SecClient, engine: sqlite3.Connection, s: Season, now: datetime,
                   over: Callable[[], bool]) -> int:  # fmt: skip
    """New fund registrations naming each active theme phrase, latest vs prior window
    (2 requests per phrase, stored per season) for the theme pages (D-M02-10)."""
    n = 0
    for r in engine.execute(
        "SELECT p.phrase FROM theme_phrase p JOIN theme t ON t.theme_id = p.theme_id "
        "WHERE t.status = 'active' AND p.status = 'active' ORDER BY p.phrase_id"
    ).fetchall():
        if over():
            break
        seasonal.crowding(client, engine, s, r[0].strip('"'), now)
        n += 1
    return n


def run_pass(
    client: SecClient,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    s: Season,
    comps: dict[str, str],
    now: datetime,
    budget: seasonal.Budget,
    progress: Callable[[str], None] | None = None,
) -> list[str]:
    from engine.themes.candidates import run_candidates
    from engine.themes.universe import ensure_quarters, quarters_between

    lines: list[str] = []
    seasonal.ensure_run(engine, s, now)
    try:
        qs = ensure_quarters(
            client, engine, quarters_between(date.fromisoformat(s.prior[0]), s.day), now
        )
        lines.append(f"form indexes: {sum(q.status == 'fetched' for q in qs)} fetched, "
                     f"{sum(q.status == 'failed' for q in qs)} failed; p0 = "
                     f"{seasonal.p0(engine, s):.3f}")  # fmt: skip
        tw = twins.fetch_twins(client, engine, corpus, comps, s.day, now)
        lines += tw.lines()
        if tw.throttled:
            raise seasonal.Throttled(tw.throttled)
        lines += mine_lines(engine, corpus, s, comps, now)
        seasonal.set_status(engine, s.key, "testing", now)
        n = seasonal.screen(client, engine, s, now, budget, progress=progress)
        lines.append(f"\nscreened {n} phrases this run")
        n = seasonal.test(client, engine, corpus, s, now, budget, progress=progress)
        lines.append(f"fully tested {n} phrases this run")
        if not budget.over() and (closed := seasonal.close_untested(engine, s, now)):
            lines.append(f"{closed} screened phrases beyond the {seasonal.TEST_CAP} full tests "
                         "closed for this season")  # fmt: skip
        lines.append(f"proposals: {seasonal.propose_pass(engine, s, now, comps)}")
        lines += run_candidates(client, engine, corpus, s, set(comps), now, budget.over).lines()
        crowd = theme_crowding(client, engine, s, now, budget.over)
        lines.append(f"theme crowding: {crowd} active theme phrases counted in fund filings")
        left = seasonal.stage_counts(engine, s.key)
        if budget.over():
            lines.append("\nSTOPPED at the time budget; run again to continue.")
        elif left.get("candidate") or left.get("screened"):
            lines.append("\nNot finished (candidates left); run again to continue.")
        else:
            seasonal.set_status(engine, s.key, "done", now, {"stages": left})
            lines.append(f"\nseason {s.key} done.")
    except seasonal.Throttled as e:
        lines.append(f"\nSTOPPED by SEC throttle: {e}; run again later to continue.")
    lines += stage_lines(engine, s) + company_lines(engine, s)
    sent = engine.execute("SELECT count(*) FROM fetch_log WHERE at >= ? AND from_cache = 0",
                          (iso(now),)).fetchone()[0]  # fmt: skip
    lines.append(f"\nSEC requests sent this run: {sent:,} in "
                 f"{(datetime.now(UTC) - now).seconds} s")  # fmt: skip
    return lines


def stage_lines(engine: sqlite3.Connection, s: Season) -> list[str]:
    out = [f"\nstages: {seasonal.stage_counts(engine, s.key)}"]
    for r in engine.execute(
        "SELECT * FROM seasonal_phrase WHERE season = ? AND stage IN ('passed', 'proposed', "
        "'listed', 'failed') ORDER BY stage, p_value", (s.key,)
    ):  # fmt: skip
        sp = json.loads(r["spread"] or "{}")
        groups = "; ".join(f"{g} {n}" for g, n in sp.get("groups", [])[:3])
        crowd = json.loads(r["crowding"] or "{}")
        theme = engine.execute("SELECT key FROM theme WHERE theme_id = ?",
                               (r["theme_id"],)).fetchone() if r["theme_id"] else None  # fmt: skip
        out.append(f"  [{r['stage']}] {r['phrase']}: {r['reason']}")
        if r["stage"] != "failed":
            top3 = f"{sp['top3']:.0%} of {sp.get('known')}" if sp.get("top3") is not None else "—"
            out.append(
                f"      spread: {groups} (top 3 {top3}) · finance {sp.get('finance')} · "
                f"blank {sp.get('blank_check')} · no SIC {sp.get('unknown')} · fund "
                f"filings {crowd.get('prior')} → {crowd.get('latest')}"
                f"{' (crowding)' if crowd.get('flag') else ''} · theme "
                f"{theme[0] if theme else 'new'} (overlap {r['overlap'] or 0:.0%})"
            )
    out.append("  screened out (first 30):")
    for r in engine.execute("SELECT phrase, reason FROM seasonal_phrase WHERE season = ? AND "
                            "stage = 'screened_out' ORDER BY rank LIMIT 30", (s.key,)):  # fmt: skip
        out.append(f"    {r[0]}: {r[1]}")
    return out


def company_lines(engine: sqlite3.Connection, s: Season) -> list[str]:
    out = ["\ncompanies (this season):"]
    for r in engine.execute(
        "SELECT c.*, t.key FROM seasonal_company c JOIN theme t USING (theme_id) WHERE "
        "c.season = ? ORDER BY c.tier, t.key, c.name", (s.key,)
    ):  # fmt: skip
        fl = json.loads(r["flags"] or "[]")
        out.append(f"  [{r['tier']}] {r['key']}: {r['ticker'] or '-'} {r['name']} · "
                   f"{r['section'] or '-'}{' · quantified' if r['quantified'] else ''} · first "
                   f"{r['first_mention']} · {r['size_label']}"
                   + (f" · FLAGS: {'; '.join(fl)}" if fl else ""))  # fmt: skip
    return out
