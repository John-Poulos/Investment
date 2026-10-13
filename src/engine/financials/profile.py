"""Company profile passes and views (M04 Part 1c; D-M04-4, -7, -8, -12, -46, -71, -80).

- `stage_pass` (local, 0 requests; every refresh and `run_financials.py profile`): per
  full-scope company (core and promoted; tracked names get no review items, D-M04-80;
  `fund` / `financial` tags excluded, D-M04-8) the stage is recomputed and stored; the
  first run opens one setup `m04_stage` item per company (outside the cap); later, a new
  fiscal year whose computed stage differs from the owner's, or is ambiguous, opens a
  capped `m04_stage` item (priority group 2, D-M04-71); `lifecycle_stage` is written.
- `peer_pass` (`run_financials.py profile` only): shortlist per target from the stored
  browse-by-SIC listing, form indexes and revenue frames; one setup `m04_peer` item per
  target.
- `setup_view` / `company_profile`: the "M04 setup" page and the Financials-tab block.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from engine.financials import models as models_mod
from engine.financials import peers, queue, stage
from engine.sec.browse import BROWSE_FORM
from engine.sec.identity import normalize_cik
from engine.themes import tiers


def full_scope(engine: sqlite3.Connection, companies: dict[str, str]) -> dict[str, str]:
    """Core and promoted names (tracked names: facts-only rows, no review items, D-M04-80)."""
    tracked = {m.cik for m in tiers.members(engine, "tracked")}
    return {t: c for t, c in companies.items() if c not in tracked}


# --- Stage pass ------------------------------------------------------------------------------


def _payload(ticker: str, r: stage.StageResult, why: list[str], tag: str | None) -> dict:
    return {
        "ticker": ticker,
        "period_end": r.period_end,
        "fiscal_label": r.label,
        "computed": r.computed,
        "years": [
            {
                "label": y.label,
                "signs": y.signs,
                "stage": y.stage,
                "signs_total": y.signs_total,
                "stage_total": y.stage_total,
                "missing": y.missing,
            }
            for y in r.years
        ],  # fmt: skip
        "rev_cagr3": r.cagr3,
        "cagr_note": r.cagr_note,
        "why": why,
        "total_note": r.total_note,
        "tag": tag,
    }


def stage_reason(ticker: str, r: stage.StageResult, why: list[str]) -> str:
    held = stage.STAGE_NAMES[r.computed] if r.computed else "no stage holds"
    return f"{ticker}: {held} ({r.label}); " + "; ".join(stage.REASONS[w] for w in why)


@dataclass
class StagePass:
    results: dict[str, stage.StageResult] = field(default_factory=dict)  # ticker → result
    opened: dict[str, str] = field(default_factory=dict)  # ticker → queue outcome
    excluded: dict[str, str] = field(default_factory=dict)  # ticker → why
    errors: list[str] = field(default_factory=list)


def stage_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    models: models_mod.ModelFile,
    now: datetime,
) -> StagePass:
    out = StagePass()
    today = now.date().isoformat()
    at = now.isoformat(timespec="seconds")
    for ticker, cik in sorted(full_scope(engine, companies).items()):
        try:
            tag, how = models_mod.route(engine, models, cik, ticker)
            if tag in models_mod.EXCLUDED:
                out.excluded[ticker] = how
                engine.execute("BEGIN")
                try:
                    stage.stage_signal(engine, cik, ticker, today, tag, how)
                    engine.execute("COMMIT")
                except Exception:
                    engine.execute("ROLLBACK")
                    raise
                continue
            r = stage.compute(engine, cik, today)
            out.results[ticker] = r
            engine.execute("BEGIN")
            try:
                stage.store(engine, r, at)
                conf = stage.confirmed(engine, cik)
                ambiguous = [c for c in r.reasons if c in stage.AMBIGUOUS]
                tag_note = ["tag_first"] if tag else []
                outcome = None
                if conf is None:
                    why = ["first", *ambiguous, *tag_note]
                    outcome = queue.propose(engine, "m04_stage", f"{cik}:setup",
                                            stage_reason(ticker, r, why),
                                            _payload(ticker, r, why, tag), now, cik=cik,
                                            setup=True)  # fmt: skip
                elif r.period_end and r.period_end > conf["period_end"]:
                    changed = r.computed is not None and r.computed != conf["confirmed"]
                    if changed or ambiguous:
                        why = (["changed"] if changed else []) + ambiguous + tag_note
                        p = _payload(ticker, r, why, tag) | {"confirmed": conf["confirmed"]}
                        outcome = queue.propose(engine, "m04_stage", f"{cik}:{r.period_end}",
                                                stage_reason(ticker, r, why), p, now,
                                                cik=cik)  # fmt: skip
                if outcome is not None:
                    out.opened[ticker] = outcome
                    pr = engine.execute(
                        "SELECT item_id FROM m04_proposal WHERE kind = 'm04_stage' AND cik = ? "
                        "AND item_id IS NOT NULL ORDER BY first_seen_at DESC LIMIT 1", (cik,)
                    ).fetchone()  # fmt: skip
                    if pr and r.period_end:
                        engine.execute("UPDATE company_stage SET item_id = ? WHERE cik = ? AND "
                                       "period_end = ? AND item_id IS NULL",
                                       (pr[0], cik, r.period_end))  # fmt: skip
                stage.stage_signal(engine, cik, ticker, today, tag, how if tag else "")
                engine.execute("COMMIT")
            except Exception:
                engine.execute("ROLLBACK")
                raise
        except Exception as e:  # one company's error must not stop the others
            if engine.in_transaction:
                engine.execute("ROLLBACK")
            out.errors.append(f"  {ticker}: stage error — {type(e).__name__}: {e}")
    engine.execute("BEGIN")
    try:
        queue.flush_overflow(engine, now)
        engine.execute("COMMIT")
    except Exception:
        engine.execute("ROLLBACK")
        raise
    return out


def stage_lines(sp: StagePass, engine: sqlite3.Connection) -> list[str]:
    lines = [f"Life-cycle stages ({len(sp.results)} computed; {len(sp.excluded)} excluded by tag):"]
    for ticker, r in sorted(sp.results.items()):
        held = stage.STAGE_NAMES[r.computed] if r.computed else "none holds"
        years = " · ".join(f"{y.label} {y.signs}"
                           + (f" {stage.STAGE_NAMES[y.stage]}" if y.stage else f" ({y.missing})")
                           for y in r.years) or "no fiscal year"  # fmt: skip
        cagr = f"{r.cagr3:+.1%}" if r.cagr3 is not None else r.cagr_note
        conf = stage.confirmed(engine, r.cik)
        state = f"confirmed {stage.STAGE_NAMES[conf['confirmed']]}" if conf else "unconfirmed"
        review = ", ".join(stage.REASONS[c] for c in r.reasons) or "no ambiguity"
        lines.append(f"  {ticker}: {held} — {years}; CAGR 3y {cagr}; {state}; review: {review}"
                     + (f"; item {sp.opened[ticker]}" if ticker in sp.opened else ""))  # fmt: skip
        if r.total_note:
            lines.append(f"    {r.total_note}")
    for ticker, how in sorted(sp.excluded.items()):
        lines.append(f"  {ticker}: excluded — {how}")
    lines += sp.errors
    return lines


# --- Peer pass -------------------------------------------------------------------------------


@dataclass
class PeerPass:
    shortlists: dict[str, peers.Shortlist] = field(default_factory=dict)  # ticker → list
    opened: dict[str, str] = field(default_factory=dict)
    no_sic: dict[str, str] = field(default_factory=dict)  # ticker → why no SIC shortlist
    gaps: list[str] = field(default_factory=list)


def peer_targets(
    engine: sqlite3.Connection, companies: dict[str, str], models: models_mod.ModelFile
) -> dict[str, tuple[str, str | None, str | None]]:
    """ticker → (cik, SIC to browse or None, why none) for full-scope, non-excluded names."""
    out = {}
    for ticker, cik in sorted(full_scope(engine, companies).items()):
        tag, how = models_mod.route(engine, models, cik, ticker)
        if tag in models_mod.EXCLUDED:
            continue
        row = engine.execute("SELECT sic FROM entity WHERE cik = ?", (cik,)).fetchone()
        sic = row["sic"] if row else None
        if tag is not None:
            out[ticker] = (cik, None, f"model tag {tag} overrides SIC {sic or 'unknown'} "
                                      "(D-M04-8): no SIC shortlist; add peers by hand")  # fmt: skip
        elif not sic:
            out[ticker] = (cik, None, "missing: no SIC stored")
        else:
            out[ticker] = (cik, sic, None)
    return out


def peer_pass(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    models: models_mod.ModelFile,
    now: datetime,
) -> PeerPass:
    """Shortlists from stored listings and frames; one setup `m04_peer` item per target."""
    out = PeerPass(gaps=peers.index_gaps(engine, now.date()))
    targets = peer_targets(engine, companies, models)
    for ticker, (cik, sic, why) in targets.items():
        s = (peers.shortlist(engine, cik, sic, now.date()) if sic else
             peers.Shortlist(cik, None, 0, 0, None, "", note=why or ""))  # fmt: skip
        out.shortlists[ticker] = s
        if why:
            out.no_sic[ticker] = why
        engine.execute("BEGIN")
        try:
            peers.store_shortlist(engine, s, now)
            if s.candidates:
                reason = (f"{ticker}: confirm peers — {len(s.candidates)} ranked from SIC {sic} "
                          f"({s.listed} listed, {s.active} active)")  # fmt: skip
            else:
                reason = f"{ticker}: no SIC shortlist ({s.note or why}); add peers or confirm none"
            payload = {
                "ticker": ticker,
                "sic": sic,
                "listed": s.listed,
                "active": s.active,
                "shortlist": [c.name for c in s.candidates],
                "revenue_suspect": [f"{n} ({w})" for n, w in s.suspects],
                "note": s.note or why or "",
            }
            out.opened[ticker] = queue.propose(engine, "m04_peer", cik, reason, payload, now,
                                               cik=cik, setup=True)  # fmt: skip
            engine.execute("COMMIT")
        except Exception:
            engine.execute("ROLLBACK")
            raise
    return out


# --- Views -----------------------------------------------------------------------------------


def _open_item(engine: sqlite3.Connection, kind: str, cik: str) -> sqlite3.Row | None:
    return engine.execute(
        "SELECT item_id, payload FROM review_queue WHERE kind = ? AND cik = ? AND "
        "resolved_at IS NULL ORDER BY item_id DESC LIMIT 1",
        (kind, cik),
    ).fetchone()


@dataclass
class StageRow:
    ticker: str
    cik: str
    fiscal_label: str
    years: list[dict[str, Any]]
    total_note: str
    cagr3: float | None
    cagr_note: str
    computed: str | None
    why: list[str]
    item_id: int | None
    confirmed: str | None
    confirmed_at: str | None
    tag: str | None
    plain_mature: bool


@dataclass
class PeerTarget:
    ticker: str
    cik: str
    item_id: int | None
    target_revenue: float | None
    candidates: list[peers.Candidate]
    confirmed: list[sqlite3.Row]
    note: str


@dataclass
class PeerGroup:
    sic: str | None
    title: str
    listed: int
    active: int
    browse: list[sqlite3.Row]
    targets: list[PeerTarget]


@dataclass
class SetupView:
    stages: list[StageRow]
    plain_mature: list[int]
    groups: list[PeerGroup]
    tags: models_mod.ModelFile
    index_gaps: list[str]
    overflow: list[dict[str, Any]]


def setup_view(
    engine: sqlite3.Connection,
    companies: dict[str, str],
    models: models_mod.ModelFile,
    now: datetime,
) -> SetupView:
    scope = full_scope(engine, companies)
    stages: list[StageRow] = []
    for ticker, cik in sorted(scope.items()):
        tag, _ = models_mod.route(engine, models, cik, ticker)
        if tag in models_mod.EXCLUDED:
            continue
        row = stage.latest_row(engine, cik)
        conf = stage.confirmed(engine, cik)
        item = _open_item(engine, "m04_stage", cik)
        p = json.loads(item["payload"]) if item else {}
        why = p.get("why") or (json.loads(row["reasons"]) if row else ["short_history"])
        years = p.get("years") or (json.loads(row["years"]) if row else [])
        computed = p.get("computed", row["computed"] if row else None)
        stages.append(StageRow(
            ticker, cik, p.get("fiscal_label") or (row["fiscal_label"] if row else "—"), years,
            p.get("total_note") or "", p.get("rev_cagr3", row["rev_cagr3"] if row else None),
            p.get("cagr_note") or "", computed, why, item["item_id"] if item else None,
            conf["confirmed"] if conf else None, conf["confirmed_at"] if conf else None, tag,
            bool(item) and computed == "mature" and why == ["first"],
        ))  # fmt: skip
    groups: dict[str | None, PeerGroup] = {}
    targets = peer_targets(engine, companies, models)
    for ticker, (cik, sic, why) in targets.items():
        if sic not in groups:
            desc = engine.execute(
                "SELECT sic_description FROM entity WHERE sic = ? AND "
                "sic_description IS NOT NULL LIMIT 1",
                (sic,),
            ).fetchone()
            listed = engine.execute("SELECT count(DISTINCT cik) FROM sic_listing WHERE sic = ?",
                                    (sic,)).fetchone()[0] if sic else 0  # fmt: skip
            ciks = [r[0] for r in engine.execute("SELECT DISTINCT cik FROM sic_listing WHERE "
                                                 "sic = ?", (sic,))] if sic else []  # fmt: skip
            active = len(peers.active_filers(engine, ciks, now.date()))
            browse = engine.execute("SELECT * FROM sic_browse WHERE sic = ? AND browsed = ?",
                                    (sic, BROWSE_FORM)).fetchall() if sic else []  # fmt: skip
            title = (f"SIC {sic}" + (f" — {desc[0]}" if desc else "")) if sic else \
                "No SIC shortlist (model tag or no SIC)"  # fmt: skip
            groups[sic] = PeerGroup(sic, title, listed, active, browse, [])
        item = _open_item(engine, "m04_peer", cik)
        tv = None
        s = peers.frame_revenue(engine, peers.frame_year(now.date())).get(cik) if sic else None
        if s:
            tv = s[0]
        groups[sic].targets.append(PeerTarget(
            ticker, cik, item["item_id"] if item else None, tv, peers.candidates(engine, cik),
            peers.confirmed_peers(engine, cik), why or "",
        ))  # fmt: skip
    ordered = sorted(groups.values(), key=lambda g: (g.sic is None, g.sic or ""))
    plain = [s.item_id for s in stages if s.plain_mature and s.item_id]
    return SetupView(stages, plain, ordered, models, peers.index_gaps(engine, now.date()),
                     queue.overflow(engine))  # fmt: skip


@dataclass
class Profile:
    stage_text: str
    flag_set: str
    computed_text: str
    tag_text: str
    peers_text: str
    peer_names: list[str]
    item_ids: list[int]


def company_profile(
    engine: sqlite3.Connection, models: models_mod.ModelFile, cik: str, ticker: str | None
) -> Profile:
    """The Profile block at the top of the Financials tab."""
    norm = normalize_cik(cik) or cik
    tag, how = models_mod.route(engine, models, norm, ticker)
    entry = models.any_for(norm, ticker)
    tag_text = (f"{entry.tag} ({entry.scope}) — {entry.reason}" if entry else "none") + (
        f"; routing now: {how}" if entry and tag is None else "")  # fmt: skip
    if models.error:
        tag_text = f"tag file rejected: {models.error}"
    conf = stage.confirmed(engine, norm)
    row = stage.latest_row(engine, norm)
    fs = stage.flag_set(conf["confirmed"] if conf else None, tag)
    if tag in models_mod.EXCLUDED:
        stage_text = f"not applicable ({tag})"
    elif conf:
        stage_text = (f"{stage.STAGE_NAMES[conf['confirmed']]} (confirmed "
                      f"{(conf['confirmed_at'] or '')[:10]})")  # fmt: skip
    else:
        stage_text = "unconfirmed"
    computed_text = "—"
    if row is not None:
        reasons = json.loads(row["reasons"])
        held = stage.STAGE_NAMES[row["computed"]] if row["computed"] else "none holds"
        computed_text = (f"{held} ({row['fiscal_label']})"
                         + (f"; review: {', '.join(stage.REASONS[c] for c in reasons)}"
                            if reasons else ""))  # fmt: skip
    conf_peers = peers.confirmed_peers(engine, norm)
    names = [r["name"] + ("" if r["cik"] else f" ({peers.NOT_SEC})") for r in conf_peers]
    if conf_peers:
        peers_text = f"{len(conf_peers)} confirmed"
    else:
        n = engine.execute("SELECT count(*) FROM peer_candidate WHERE target_cik = ? AND status = "
                           "'proposed'", (norm,)).fetchone()[0]  # fmt: skip
        peers_text = f"not confirmed ({n} proposed)" if n else "none proposed yet"
    items = [r[0] for r in engine.execute(
        "SELECT item_id FROM review_queue WHERE cik = ? AND kind IN ('m04_stage', 'm04_peer') "
        "AND resolved_at IS NULL ORDER BY item_id", (norm,))]  # fmt: skip
    return Profile(stage_text, fs.label, computed_text, tag_text, peers_text, names, items)
