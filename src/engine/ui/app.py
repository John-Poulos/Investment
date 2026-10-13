"""FastAPI app for the local UI (M00_UI.md, D29).

Pages are rendered on the server from Jinja2 templates; every page resolves
its viewer through `current_viewer` (U1) and reads data only through
`services` (U4). Step 1 of the build: layout, side panel and the tabs whose
data is already stored. Prices/chart, Guidance + Analyze and the review queue
follow in later steps.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from engine import review
from engine.calls import ir_inbox
from engine.financials import units_view as m04_units_view
from engine.financials import views as m04_views
from engine.financing import links as fin_links
from engine.financing import views as fin_views
from engine.guidance import labels
from engine.guidance.sources import FORECAST_NOTE, is_sec, source_label
from engine.llm import call_check, guidance_reasons
from engine.llm.provider import GeminiProvider, estimate_tokens, load_settings
from engine.llm.runs import cached_call
from engine.llm.runs import run as llm_run
from engine.moneyflow import allocation as mf_allocation
from engine.moneyflow import views as mf_views
from engine.news import views as news_views
from engine.official import views as off_views
from engine.prices import store as prices
from engine.prices.tiingo import MissingKey, TiingoClient, token_from_env
from engine.store.db import connect, migrate
from engine.supply import gold as supply_gold
from engine.themes import proposals, tiers
from engine.themes import views as themes
from engine.ui import services
from engine.ui.settings import UiSettings
from engine.ui.viewer import Viewer, current_viewer, require_owner

HERE = Path(__file__).parent
EXPECTED_OUTPUT_TOKENS = 1500  # allowance for the cost estimate (reply + thinking)


@dataclass(frozen=True)
class Correction:
    """Optional corrected value sent with 'wrong' or 'missed' (fields fix_*, D-M02-24)."""

    metric: str = ""
    basis: str = "unspecified"
    period: str = ""
    unit: str = "USD"
    low: str = ""
    high: str = ""
    scale: str = "1"

    def manual(self) -> review.ManualGuidance | None:
        if not self.low.strip():
            return None
        return review.ManualGuidance(self.metric, self.basis, self.period, self.unit,
                                     self.low, self.high, self.scale)  # fmt: skip


def correction_form(
    fix_metric: Annotated[str, Form()] = "",
    fix_basis: Annotated[str, Form()] = "unspecified",
    fix_period: Annotated[str, Form()] = "",
    fix_unit: Annotated[str, Form()] = "USD",
    fix_low: Annotated[str, Form()] = "",
    fix_high: Annotated[str, Form()] = "",
    fix_scale: Annotated[str, Form()] = "1",
) -> Correction:
    return Correction(fix_metric, fix_basis, fix_period, fix_unit, fix_low, fix_high, fix_scale)


TABS = (
    ("overview", "Overview", True),
    ("guidance", "Guidance", True),
    ("money", "Money flow", True),  # M02 part 3
    ("financials", "Financials", True),
    ("m04", "M04", True),  # M04 Part 8a: Cycle vs Decline (D-UI-31)
    ("insiders", "Insiders", True),
    ("events", "Events and filings", True),
    ("news", "News", True),  # M02 part 7a
    ("search", "Search", True),
    ("themes", "Themes", True),  # M02 part 1
    ("ask", "Ask", False),  # reserved (D-SRCH-18)
)
NOT_BUILT = {
    "ask": "Reserved for grounded Q&A, to be decided after the fixed analyses prove themselves.",
}


def fmt_number(value: object, unit: str = "currency") -> str:
    """Display a stored value; None stays '—' (missing is never zero)."""
    if value is None:
        return "—"
    d = Decimal(str(value))
    if unit == "per_share":
        return f"{d:,.2f}"
    if unit == "shares_exact":
        return f"{d:,.0f}"
    if unit == "shares":
        return f"{d / 10**6:,.1f}M"
    a = abs(d)
    if a >= 10**9:
        return f"{d / 10**9:,.2f}B"
    if a >= 10**6:
        return f"{d / 10**6:,.1f}M"
    return f"{d:,.0f}"


def _db(request: Request, name: str) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.data_dir / f"{name}.db", check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def engine_db(request: Request) -> Iterator[sqlite3.Connection]:
    yield from _db(request, "engine")


def corpus_db(request: Request) -> Iterator[sqlite3.Connection]:
    yield from _db(request, "corpus")


Engine = Annotated[sqlite3.Connection, Depends(engine_db)]
Corpus = Annotated[sqlite3.Connection, Depends(corpus_db)]
ViewerDep = Annotated[Viewer, Depends(current_viewer)]
OwnerDep = Annotated[Viewer, Depends(require_owner)]


def create_app(settings: UiSettings) -> FastAPI:
    app = FastAPI(title="Investment engine", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["num"] = fmt_number
    templates.env.globals["source_label"] = source_label  # D-M02-21 labels
    templates.env.globals["is_sec"] = is_sec
    templates.env.globals["sec_filing_url"] = services.filing_index_url  # M04 Part 1a
    templates.env.globals["FORECAST_NOTE"] = FORECAST_NOTE
    templates.env.filters["money"] = mf_views.money  # M02 part 3
    templates.env.filters["usd"] = off_views.usd  # M02 part 7b
    templates.env.globals["AWARD_NOTE"] = off_views.AWARD_NOTE
    templates.env.globals["payload_value"] = mf_views.payload_value
    templates.env.filters["mark_phrase"] = themes.mark_phrase  # M02 part 6 samples
    templates.env.globals["fin_kinds"] = fin_views.KIND_LABELS  # M02 part 5b
    templates.env.globals["dso_band"] = fin_views.credit.band
    templates.env.globals["news_channel"] = lambda c: news_views.CHANNEL_LABELS.get(c, c)

    for db in ("engine", "corpus"):  # bring schemas up to date once, at start
        conn = connect(settings.data_dir / f"{db}.db")
        migrate(conn, db)
        conn.close()

    app.state.settings = settings

    def frame(engine: sqlite3.Connection) -> dict:
        tickers = services.watchlist_tickers(settings.watchlist)
        listed, tracked = services.tiered(engine, services.watchlist(engine, tickers))
        return {"status": services.status(engine), "watchlist": listed, "tracked": tracked}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/")
    def home(engine: Engine, viewer: ViewerDep) -> RedirectResponse:
        listed = services.watchlist(engine, services.watchlist_tickers(settings.watchlist))
        first = next((c.ticker for c in listed if c.cik), None)
        if first is None:
            raise HTTPException(404, "No watchlist company is resolved yet.")
        return RedirectResponse(f"/c/{first}", status_code=307)

    @app.get("/c/{ticker}", response_class=HTMLResponse)
    def company_page(
        request: Request,
        ticker: str,
        engine: Engine,
        corpus: Corpus,
        viewer: ViewerDep,
        tab: str = "overview",
        q: Annotated[str, Query(max_length=300)] = "",
        bar: str = "D",
        msg: str = "",
        detail: str = "",
        only: str = "",
    ):
        ticker = ticker.upper()
        bar = "W" if bar.upper() == "W" else "D"
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        if tab not in {t for t, _, _ in TABS}:
            tab = "overview"
        ctx = frame(engine) | {
            "viewer": viewer,
            "ticker": ticker,
            "cik": cik,
            "company": services.company(engine, cik),
            "tabs": TABS,
            "tab": tab,
            "not_built": NOT_BUILT.get(tab),
            "earnings_dates": services.earnings_dates(engine, cik),
            "q": q,
            "bar": bar,
            "msg": msg,
            "detail": detail,
            "price_state": services.price_state(engine, ticker),
        }
        if tab == "overview":
            ctx["filings"] = services.filings(engine, cik, limit=10)
            ctx["events"] = services.events(engine, cik, limit=8)
            ctx["readable"] = services.stored_accessions(
                corpus, [f["accession"] for f in ctx["filings"]]
            )
        elif tab == "guidance":
            ctx["guidance"] = services.guidance_view(engine, cik)
            ctx["analyze"] = analyze_estimate(engine, corpus, cik)
        elif tab == "money":
            ctx["mf"] = mf_views.company_view(engine, cik, datetime.now(UTC).date(), corpus)
            ctx["fin"] = fin_views.company_view(engine, cik, datetime.now(UTC).date())
            ctx["awards"] = off_views.company_awards(engine, cik, datetime.now(UTC).date())
        elif tab == "financials":
            ctx["tables"] = services.financials(engine, cik)
            ctx["m04"] = m04_views.company_view(
                engine, cik, datetime.now(UTC).date(), corpus, ticker
            )
            from engine.financials.flags_view import flags_view  # M04 Part 3

            ctx["m04_flags"] = flags_view(engine, corpus, cik, datetime.now(UTC).date())
            ctx["m04_units"] = m04_units_view.company_view(engine, cik, ticker)  # Part 7a
            from engine.financials.quality_view import company_view as quality_view  # Part 6

            ctx["m04_quality"] = quality_view(engine, corpus, cik, ticker)
            from engine.financials import gate_view as m04_gate_view  # Part 4a

            ctx["m04_gate"] = m04_gate_view.company_view(
                engine, cik, ticker, datetime.now(UTC).date(), m04_companies(engine)
            )
        elif tab == "m04":  # M04 Part 8a (D-UI-31)
            from engine.financials import cvd_view

            ctx["m04_cvd"] = cvd_view.company_view(
                engine, cik, ticker, datetime.now(UTC).date(), m04_companies(engine)
            )
            ctx["questions"], ctx["readings"] = cvd_view.QUESTIONS, cvd_view.READING
            ctx["links"] = cvd_view.LINKS
        elif tab == "insiders":
            ctx["txns"] = services.insider_txns(engine, cik)
        elif tab == "events":
            ctx["events"] = services.events(engine, cik)
            ctx["filings"] = services.filings(engine, cik)
            ctx["readable"] = services.stored_accessions(
                corpus,
                list(
                    {f["accession"] for f in ctx["filings"]}
                    | {e["accession"] for e in ctx["events"]}
                ),
            )
        elif tab == "news":
            ctx["news"] = news_views.company_view(
                engine, cik, ticker=ticker, themed_only=only == "themed"
            )
        elif tab == "themes":
            ctx["ct"] = themes.company_themes(engine, cik, ticker)
            ctx["member"] = tiers.member(engine, cik)
            ctx["is_core"] = cik in core_ciks(engine)
            ctx["readable"] = services.stored_accessions(
                corpus, [m["accession"] for m in ctx["ct"].mentions]
            )
        elif tab == "search" and q.strip():
            ctx["result"] = services.company_search(corpus, cik, q.strip())
        return templates.TemplateResponse(request, "company.html", ctx)

    def analyze_estimate(engine, corpus, cik) -> dict:
        """What an Analyze run would send and cost (no call is made)."""
        prep = guidance_reasons.prepare(engine, corpus, cik)
        req = prep.request
        if req is None:
            return {"possible": False, "changes": len(prep.changes)}
        llm = load_settings()
        est_in = estimate_tokens(req.system + req.user)
        return {
            "possible": True,
            "asked": len(prep.asked),
            "passages": len(prep.passages),
            "tokens": est_in,
            "cost": llm.cost(est_in, EXPECTED_OUTPUT_TOKENS),
            "model": llm.model,
            "cached": cached_call(engine, req, llm.model) is not None,
            "prep": prep,
        }

    @app.get("/c/{ticker}/analyze/guidance-reasons", response_class=HTMLResponse)
    def analyze_page(
        request: Request, ticker: str, engine: Engine, corpus: Corpus, viewer: ViewerDep
    ):
        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        ctx = frame(engine) | {
            "viewer": viewer,
            "ticker": ticker,
            "company": services.company(engine, cik),
            "est": analyze_estimate(engine, corpus, cik),
            "describe": guidance_reasons.describe,
        }
        return templates.TemplateResponse(request, "analyze.html", ctx)

    @app.post("/c/{ticker}/analyze/guidance-reasons")
    def analyze_run(
        ticker: str,
        engine: Engine,
        corpus: Corpus,
        owner: OwnerDep,
        rerun: str = "0",
    ) -> RedirectResponse:
        """Owner-confirmed Gemini call (D-SRCH-18): stored result reused unless rerun."""
        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        req = guidance_reasons.prepare(engine, corpus, cik).request
        if req is None:
            return RedirectResponse(f"/c/{ticker}?tab=guidance&msg=nothing-to-ask", 303)
        try:
            provider = settings.llm_factory() if settings.llm_factory else GeminiProvider()
            res = llm_run(engine, provider, load_settings(), req, datetime.now(UTC),
                          rerun=rerun == "1")  # fmt: skip
        except Exception as e:  # key missing, network, unreadable reply: say so, store nothing new
            detail = quote(f"{type(e).__name__}: {e}"[:200])
            return RedirectResponse(f"/c/{ticker}?tab=guidance&msg=llm-error&detail={detail}", 303)
        msg = "stored-result" if res.cached else "analyzed"
        return RedirectResponse(f"/c/{ticker}?tab=guidance&msg={msg}", 303)

    def core_ciks(engine: sqlite3.Connection) -> set[str]:
        listed = services.watchlist(engine, services.watchlist_tickers(settings.watchlist))
        return {c.cik for c in listed if c.cik}

    @app.post("/c/{ticker}/tier/{action}")
    def tier_action(
        ticker: str,
        action: str,
        engine: Engine,
        owner: OwnerDep,
        reason: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Owner-only tier changes (U2; D-M02-11): track, promote, demote, remove."""
        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        now = datetime.now(UTC)
        try:
            if action == "track":
                tiers.add_tracked(engine, cik, ticker, reason=reason.strip() or "owner",
                                  theme_key=None, by=owner.id, now=now,
                                  core=core_ciks(engine))  # fmt: skip
            elif action == "promote":
                tiers.promote(engine, cik, owner.id, now)
            elif action == "demote":
                tiers.demote(engine, cik, owner.id, now)
            elif action == "remove":
                tiers.remove(engine, cik, owner.id, now)
            else:
                raise HTTPException(404, f"Unknown action {action}.")
        except tiers.TierError as e:
            return RedirectResponse(f"/c/{ticker}?tab=themes&msg={quote(str(e))}", 303)
        return RedirectResponse(f"/c/{ticker}?tab=themes&msg={quote(action + ': done')}", 303)

    def pick_family(engine: sqlite3.Connection, family: str) -> tuple[str, list[str]]:
        fams = themes.families_with_data(engine)
        return (family if family in fams else fams[0]), fams

    @app.get("/themes", response_class=HTMLResponse)
    def themes_page(request: Request, engine: Engine, viewer: ViewerDep, family: str = "10-K"):
        family, fams = pick_family(engine, family)
        ctx = frame(engine) | {
            "viewer": viewer,
            "family": family,
            "families": fams,
            "themes": themes.theme_list(engine, family),
            "overflow": proposals.overflow(engine),
            "through": themes.data_through(engine),
            "seasonal": themes.seasonal_view(engine),
            "crowded": themes.crowded_themes(engine),
        }
        return templates.TemplateResponse(request, "themes.html", ctx)

    @app.get("/themes/{key}", response_class=HTMLResponse)
    def theme_page(
        request: Request, key: str, engine: Engine, viewer: ViewerDep, family: str = "10-K"
    ):
        family, _ = pick_family(engine, family)
        d = themes.theme_detail(engine, key, family)
        if d is None:
            raise HTTPException(404, f"Unknown theme {key}.")
        row = engine.execute("SELECT theme_id FROM theme WHERE key = ?", (key,)).fetchone()
        mf = mf_views.theme_view(engine, row["theme_id"], key, datetime.now(UTC).date())
        news = news_views.theme_view(engine, row["theme_id"], datetime.now(UTC).date())
        official = off_views.theme_view(engine, row["theme_id"], datetime.now(UTC).date())
        ctx = frame(engine) | {"viewer": viewer, "d": d, "mf": mf, "news": news,
                               "official": official,
                               "crowd": themes.theme_crowding(engine, row["theme_id"])}  # fmt: skip
        return templates.TemplateResponse(request, "theme.html", ctx)

    @app.get("/themes/{key}/filers", response_class=HTMLResponse)
    def theme_filers_page(
        request: Request,
        key: str,
        engine: Engine,
        corpus: Corpus,
        viewer: ViewerDep,
        phrase: Annotated[str, Query(max_length=200)],
        start: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        end: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
        family: str = "10-K",
    ):
        family, _ = pick_family(engine, family)
        row = engine.execute("SELECT name FROM theme WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise HTTPException(404, f"Unknown theme {key}.")
        filers, partial = themes.phrase_filers(engine, phrase, family, start, end)
        ctx = frame(engine) | {
            "viewer": viewer, "key": key, "name": row["name"], "family": family,
            "phrase": phrase, "start": start, "end": end, "filers": filers,
            "partial": partial,
            "readable": services.stored_accessions(corpus, [f.accession for f in filers]),
        }  # fmt: skip
        return templates.TemplateResponse(request, "theme_filers.html", ctx)

    @app.get("/runs", response_class=HTMLResponse)
    def runs_page(request: Request, engine: Engine, viewer: ViewerDep):
        now = datetime.now(UTC).isoformat(timespec="seconds")
        ctx = frame(engine) | {"viewer": viewer, "rc": services.runs_and_costs(engine, now),
                               "accuracy": labels.accuracy(engine),
                               "tag_maps": mf_allocation.mapping_list(engine),
                               "gold": supply_gold.accuracy(engine),
                               "gold_size": supply_gold.size(engine),
                               "gold_trial": supply_gold.trial_line(engine),
                               "fin_wrong": fin_links.wrong_list(engine)}  # fmt: skip
        return templates.TemplateResponse(request, "runs.html", ctx)

    @app.get("/m02/labels", response_class=HTMLResponse)
    def label_page(request: Request, engine: Engine, owner: OwnerDep, pos: int = 0,
                   error: str = ""):  # fmt: skip
        """Blind labelling of the supplier-link precision set (D-M02-35)."""
        card = supply_gold.card(engine, pos or None)
        ctx = frame(engine) | {"viewer": owner, "card": card, "error": error,
                               "acc": supply_gold.accuracy(engine),
                               "size": supply_gold.size(engine)}  # fmt: skip
        return templates.TemplateResponse(request, "labels.html", ctx)

    @app.post("/m02/labels/{gold_id}")
    def label_submit(
        gold_id: int,
        engine: Engine,
        owner: OwnerDep,
        gold_type: Annotated[str, Form()] = "",
        direction: Annotated[str, Form()] = "",
        pos: Annotated[int, Form()] = 0,
    ) -> RedirectResponse:
        try:
            supply_gold.label(engine, gold_id, gold_type, direction or None, owner.id,
                              datetime.now(UTC))  # fmt: skip
        except ValueError as e:
            return RedirectResponse(f"/m02/labels?pos={pos}&error={quote(str(e))}", 303)
        return RedirectResponse("/m02/labels", 303)

    @app.post("/fin/holding/{holding_id}/wrong")
    def fin_wrong(holding_id: int, engine: Engine, owner: OwnerDep,
                  back: Annotated[str, Form()] = "/") -> RedirectResponse:  # fmt: skip
        """'wrong?' on a 13F/13D/13G record: removed and kept out of later runs (D-M02-42).
        Undo on the Runs page."""
        fin_links.wrong_holding(engine, holding_id, owner.id, datetime.now(UTC))
        return RedirectResponse(back if back.startswith("/") else "/", 303)

    @app.post("/fin/suppress/undo")
    def fin_wrong_undo(engine: Engine, owner: OwnerDep,
                       key: Annotated[str, Form()]) -> RedirectResponse:  # fmt: skip
        fin_links.undo_wrong(engine, key)
        return RedirectResponse("/runs#fin-wrong", 303)

    @app.post("/money/tag-map/{map_id}/undo")
    def tag_map_undo(map_id: int, engine: Engine, owner: OwnerDep) -> RedirectResponse:
        """Undo a cash-flow tag mapping (D-M02-31 (5)); its review item reopens."""
        mf_allocation.unmap(engine, map_id, owner.id, datetime.now(UTC))
        return RedirectResponse("/runs#tag-maps", 303)

    # --- guidance accuracy (D-M02-24) ------------------------------------------------

    @app.get("/c/{ticker}/guidance/{guidance_id}/wrong", response_class=HTMLResponse)
    def wrong_form(request: Request, ticker: str, guidance_id: int, engine: Engine,
                   owner: OwnerDep, error: str = ""):  # fmt: skip
        row = engine.execute("SELECT * FROM guidance WHERE guidance_id = ?",
                             (guidance_id,)).fetchone()  # fmt: skip
        if row is None:
            raise HTTPException(404, "That guidance row is no longer stored.")
        ctx = frame(engine) | {"viewer": owner, "ticker": ticker.upper(), "row": row,
                               "stored": labels.describe_row(row), "reasons": labels.REASONS,
                               "metrics": services.METRIC_ORDER,
                               "error": error}  # fmt: skip
        return templates.TemplateResponse(request, "guidance_wrong.html", ctx)

    @app.post("/c/{ticker}/guidance/{guidance_id}/wrong")
    def wrong_submit(
        ticker: str,
        guidance_id: int,
        engine: Engine,
        corpus: Corpus,
        owner: OwnerDep,
        fix: Annotated[Correction, Depends(correction_form)],
        reason: Annotated[str, Form()] = "",
        note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        ticker = ticker.upper()
        if reason == "no_error":
            try:
                review.confirm_row(engine, guidance_id, note, owner.id, datetime.now(UTC))
            except review.ReviewError as e:
                return RedirectResponse(
                    f"/c/{ticker}/guidance/{guidance_id}/wrong?error={quote(str(e))}", 303
                )
            return RedirectResponse(f"/c/{ticker}?tab=guidance&msg=labelled-right", 303)
        try:
            warnings = review.mark_wrong(engine, guidance_id, reason, note, owner.id,
                                         datetime.now(UTC), corpus=corpus,
                                         correction=fix.manual())  # fmt: skip
        except review.ReviewError as e:
            return RedirectResponse(
                f"/c/{ticker}/guidance/{guidance_id}/wrong?error={quote(str(e))}", 303
            )
        detail = quote("; ".join(warnings))
        return RedirectResponse(f"/c/{ticker}?tab=guidance&msg=labelled-wrong&detail={detail}", 303)

    @app.post("/labels/{label_id}/undo")
    def label_undo(label_id: int, engine: Engine, corpus: Corpus, owner: OwnerDep,
                   back: str = "/runs") -> RedirectResponse:  # fmt: skip
        """Take back a label (D-M02-24): correction removed, item reopened, row restored."""
        try:
            done = review.undo_label(engine, corpus, label_id, owner.id, datetime.now(UTC))
        except review.ReviewError as e:
            done = str(e)
        target = back if back.startswith("/") and not back.startswith("//") else "/runs"
        sep = "&" if "?" in target else "?"
        return RedirectResponse(f"{target}{sep}msg=undone&detail={quote(done)}", 303)

    @app.get("/c/{ticker}/calls/check", response_class=HTMLResponse)
    def call_check_page(request: Request, ticker: str, acc: str, file: str, engine: Engine,
                        corpus: Corpus, viewer: ViewerDep):  # fmt: skip
        prep = call_check.prepare(engine, corpus, acc, file)
        if prep is None:
            raise HTTPException(404, "That call document is not stored.")
        llm = load_settings()
        est = None
        if prep.request is not None:
            tokens = estimate_tokens(prep.request.system + prep.request.user)
            est = {"tokens": tokens, "cost": llm.cost(tokens, EXPECTED_OUTPUT_TOKENS),
                   "model": llm.model,
                   "cached": cached_call(engine, prep.request, llm.model) is not None}  # fmt: skip
        ctx = frame(engine) | {"viewer": viewer, "ticker": ticker.upper(), "prep": prep,
                               "est": est}  # fmt: skip
        return templates.TemplateResponse(request, "call_check.html", ctx)

    @app.post("/c/{ticker}/calls/check")
    def call_check_run(ticker: str, acc: str, file: str, engine: Engine, corpus: Corpus,
                       owner: OwnerDep, rerun: str = "0") -> RedirectResponse:  # fmt: skip
        """Owner-triggered Gemini cross-check of one call (D-M02-24); cost shown first."""
        ticker = ticker.upper()
        prep = call_check.prepare(engine, corpus, acc, file)
        if prep is None or prep.request is None:
            raise HTTPException(404, "Nothing to check in that call document.")
        now = datetime.now(UTC)
        try:
            provider = settings.llm_factory() if settings.llm_factory else GeminiProvider()
            res = llm_run(engine, provider, load_settings(), prep.request, now,
                          rerun=rerun == "1")  # fmt: skip
        except Exception as e:  # key missing, network, unreadable reply: say so, store nothing
            detail = quote(f"{type(e).__name__}: {e}"[:200])
            return RedirectResponse(f"/c/{ticker}?tab=guidance&msg=llm-error&detail={detail}", 303)
        text = corpus.execute("SELECT text FROM document WHERE accession = ? AND filename = ?",
                              (acc, file)).fetchone()[0]  # fmt: skip
        queued = call_check.queue_missed(engine, prep, res, text, now)
        msg = quote(f"Gemini check of {acc}: {len(res.observations)} statements read, "
                    f"{queued} sentence(s) the code missed sent to the review queue")  # fmt: skip
        return RedirectResponse(f"/c/{ticker}?tab=guidance&msg=checked&detail={msg}", 303)

    @app.get("/review", response_class=HTMLResponse)
    def review_page(
        request: Request,
        engine: Engine,
        viewer: ViewerDep,
        kind: str | None = None,
        ticker: str | None = None,
        show: str = "open",
        msg: str = "",
    ):
        cik = services.resolve_ticker(engine, ticker) if ticker else None
        listed = review.items(engine, open_only=show != "resolved", kind=kind or None, cik=cik)
        ctx = frame(engine) | {
            "viewer": viewer,
            "items": listed,
            "counts": review.counts(engine),
            "labels": review.KIND_LABELS,
            "kind": kind or "",
            "ticker": (ticker or "").upper(),
            "show": show,
            "msg": msg,
        }
        return templates.TemplateResponse(request, "review.html", ctx)

    @app.get("/review/{item_id}", response_class=HTMLResponse)
    def review_item_page(
        request: Request,
        item_id: int,
        engine: Engine,
        corpus: Corpus,
        viewer: ViewerDep,
        error: str = "",
    ):
        it = review.get(engine, item_id)
        if it is None:
            raise HTTPException(404, "No such review item.")
        p = it.payload
        context = None
        offsets = p.get("offsets") or p.get("other_offsets")
        if "accession" in p and offsets:
            context = services.source(corpus, p["accession"], p["filename"], *offsets)
        ctx = frame(engine) | {
            "viewer": viewer,
            "it": it,
            "context": context,
            "metrics": services.METRIC_ORDER,
            "reasons": labels.REASONS,
            "error": error,
            "pickup": None,
        }
        return templates.TemplateResponse(request, "review_item.html", ctx)

    @app.get("/review/{item_id}/pickup", response_class=HTMLResponse)
    def review_pickup(
        request: Request, item_id: int, engine: Engine, owner: OwnerDep, error: str = ""
    ):
        """'I downloaded it': show the newest PDF in Downloads before storing it (D-M02-21)."""
        it = review.get(engine, item_id)
        if it is None or it.kind != "m02_ir_download":
            raise HTTPException(404, "No such download item.")
        found = ir_inbox.newest_pdf(settings.downloads_dir)
        ctx = frame(engine) | {
            "viewer": owner, "it": it, "context": None, "metrics": services.METRIC_ORDER,
            "reasons": labels.REASONS,
            "error": error or ("" if found else f"No PDF found in {settings.downloads_dir}."),
            "pickup": found, "doc_kinds": tuple(ir_inbox.DOC_KINDS),
        }  # fmt: skip
        return templates.TemplateResponse(request, "review_item.html", ctx)

    @app.post("/review/{item_id}/ingest")
    def review_ingest(
        item_id: int,
        engine: Engine,
        corpus: Corpus,
        owner: OwnerDep,
        name: Annotated[str, Form()],
        doc_kind: Annotated[str, Form()] = "transcript",
        note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Store the confirmed PDF, scan it, and close the download item."""
        it = review.get(engine, item_id)
        if it is None or it.kind != "m02_ir_download" or it.resolved_at:
            raise HTTPException(404, "No open download item.")
        found = ir_inbox.newest_pdf(settings.downloads_dir)
        if found is None or found.name != name:
            msg = "The newest PDF in Downloads changed; check the file again."
            return RedirectResponse(f"/review/{item_id}/pickup?error={quote(msg)}", 303)
        p = it.payload
        try:
            accession, scan = ir_inbox.ingest_pdf(
                engine, corpus, path=found.path, cik=it.cik or "", symbol=p["symbol"],
                av_quarter=p["av_quarter"], doc_kind=doc_kind,
                release_accession=p.get("release_accession"),
                release_filed=p.get("release_filed"), now=datetime.now(UTC),
            )  # fmt: skip
        except ir_inbox.InboxError as e:
            return RedirectResponse(f"/review/{item_id}?error={quote(str(e))}", 303)
        stored = f"stored {found.name} as {accession}: {scan.items} guidance rows, " \
                 f"{scan.unparsed} sentences to review"  # fmt: skip
        review.m02_action(engine, item_id, "downloaded", (note + " " if note else "") + stored,
                          owner.id, datetime.now(UTC))  # fmt: skip
        return RedirectResponse(f"/review?msg={quote(f'Item {item_id}: {stored}')}", 303)

    @app.post("/review/{item_id}/{action}")
    def review_action(
        item_id: int,
        action: str,
        engine: Engine,
        corpus: Corpus,
        owner: OwnerDep,
        fix: Annotated[Correction, Depends(correction_form)],
        note: Annotated[str, Form()] = "",
        metric: Annotated[str, Form()] = "",
        basis: Annotated[str, Form()] = "unspecified",
        period: Annotated[str, Form()] = "",
        unit: Annotated[str, Form()] = "USD",
        low: Annotated[str, Form()] = "",
        high: Annotated[str, Form()] = "",
        scale: Annotated[str, Form()] = "1",
        reason: Annotated[str, Form()] = "",
        target: Annotated[str, Form()] = "",
        keep: Annotated[list[str] | None, Form()] = None,
        back: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Owner-only review actions (U2); each closes the item with who, when and note (U3)."""
        now = datetime.now(UTC)
        done = action
        if (it0 := review.get(engine, item_id)) and it0.kind.startswith("m04_"):
            to = back if back.startswith("/") and not back.startswith("//") else "/review"
            sep = "&" if "?" in to else "?"
            try:
                done = review.m04_action(engine, item_id, action, note, owner.id, now,
                                         target=target, keep=tuple(keep or ()))  # fmt: skip
            except review.ReviewError as e:
                if to != "/review":
                    return RedirectResponse(f"{to}{sep}error={quote(str(e))}", 303)
                return RedirectResponse(f"/review/{item_id}?error={quote(str(e))}", 303)
            return RedirectResponse(f"{to}{sep}msg={quote(f'Item {item_id}: {done}')}", 303)
        try:
            if action == "enter":
                warnings = review.enter_guidance(
                    engine, corpus, item_id,
                    review.ManualGuidance(metric, basis, period, unit, low, high, scale),
                    note, owner.id, now,
                )  # fmt: skip
                if warnings:
                    done = "entered-with-warnings: " + "; ".join(warnings)
            elif action == "keep_other":
                review.keep_other(engine, corpus, item_id, note, owner.id, now)
            elif action == "reopen":
                done = review.reopen(engine, item_id, owner.id, now, corpus)
            elif action in review.LABEL_ACTIONS:
                warnings = review.label_action(engine, item_id, action, reason, note, owner.id,
                                               now, corpus=corpus,
                                               correction=fix.manual())  # fmt: skip
                if warnings:
                    done = f"{action}; correction stored with warnings: " + "; ".join(warnings)
            elif action == "approve":
                review.approve_ticker_hold(engine, item_id, note, owner.id, now)
            elif (it := review.get(engine, item_id)) and it.kind.startswith("m02_"):
                review.m02_action(engine, item_id, action, note, owner.id, now,
                                  core_ciks(engine), target)  # fmt: skip
            else:
                review.resolve(engine, item_id, action, note, owner.id, now)
        except review.ReviewError as e:
            return RedirectResponse(f"/review/{item_id}?error={quote(str(e))}", 303)
        return RedirectResponse(f"/review?msg={quote(f'Item {item_id}: {done}')}", 303)

    # --- M04 setup (Part 1c; D-M04-4, -7, -8, -12, -71) ---------------------------------

    def m04_companies(engine: sqlite3.Connection) -> dict[str, str]:
        listed = services.watchlist(engine, services.watchlist_tickers(settings.watchlist))
        out = {c.ticker: c.cik for c in listed if c.cik}
        for m in tiers.members(engine, "promoted"):
            out.setdefault(m.ticker, m.cik)
        return out

    @app.get("/m04/setup", response_class=HTMLResponse)
    def m04_setup_page(request: Request, engine: Engine, viewer: ViewerDep, msg: str = "",
                       error: str = ""):  # fmt: skip
        """Stage confirmations, peer shortlists and model tags (owner's mock-up)."""
        from engine.financials import models as m04_models
        from engine.financials import profile as m04_profile
        from engine.financials import stage as m04_stage

        view = m04_profile.setup_view(engine, m04_companies(engine), m04_models.load_safe(),
                                      datetime.now(UTC))  # fmt: skip
        ctx = frame(engine) | {"viewer": viewer, "v": view, "msg": msg, "error": error,
                               "stage_names": m04_stage.STAGE_NAMES,
                               "reasons": m04_stage.REASONS, "routing": m04_models.ROUTING,
                               "not_sec": m04_peers_not_sec()}  # fmt: skip
        return templates.TemplateResponse(request, "m04_setup.html", ctx)

    def m04_peers_not_sec() -> str:
        from engine.financials.peers import NOT_SEC

        return NOT_SEC

    @app.post("/m04/stage/confirm-all")
    def m04_confirm_all(
        engine: Engine, owner: OwnerDep, items: Annotated[list[int] | None, Form()] = None
    ) -> RedirectResponse:
        """'Confirm all N' for the plain-mature group: each item closed through the review
        machinery as computed (mature)."""
        done, errors = 0, []
        for item_id in items or []:
            try:
                review.m04_action(engine, item_id, "confirm", "confirm all (plain mature)",
                                  owner.id, datetime.now(UTC))  # fmt: skip
                done += 1
            except review.ReviewError as e:
                errors.append(f"item {item_id}: {e}")
        msg = f"{done} stage(s) confirmed as mature" + (f"; {'; '.join(errors)}" if errors else "")
        return RedirectResponse(f"/m04/setup?msg={quote(msg)}#stages", 303)

    @app.post("/m04/stage/{ticker}/override")
    def m04_override(ticker: str, engine: Engine, owner: OwnerDep,
                     stage: Annotated[str, Form()], note: Annotated[str, Form()] = ""
                     ) -> RedirectResponse:  # fmt: skip
        """Owner override with no item open (D-M04-12): recorded as a resolved item."""
        cik = services.resolve_ticker(engine, ticker.upper())
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        try:
            done = review.m04_override(engine, cik, ticker.upper(), stage, note, owner.id,
                                       datetime.now(UTC))  # fmt: skip
        except review.ReviewError as e:
            return RedirectResponse(f"/m04/setup?error={quote(str(e))}#stages", 303)
        return RedirectResponse(f"/m04/setup?msg={quote(f'{ticker.upper()}: {done}')}#stages", 303)

    @app.post("/m04/peers/{ticker}/edit")
    def m04_peer_edit(ticker: str, engine: Engine, owner: OwnerDep,
                      note: Annotated[str, Form()] = "") -> RedirectResponse:  # fmt: skip
        """'Edit peers' on a confirmed set (M04 Part 2): reopens it as a new `m04_peer`
        item (setup, outside the cap), kept in the review history."""
        cik = services.resolve_ticker(engine, ticker.upper())
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        try:
            item_id = review.m04_peer_reopen(engine, cik, ticker.upper(), note, owner.id,
                                             datetime.now(UTC))  # fmt: skip
        except review.ReviewError as e:
            return RedirectResponse(f"/m04/setup?error={quote(str(e))}#peers", 303)
        msg = f"{ticker.upper()}: peer set reopened (item {item_id})"
        return RedirectResponse(f"/m04/setup?msg={quote(msg)}#peer-{item_id}", 303)

    @app.post("/m04/peer/{item_id}/add")
    def m04_peer_add(item_id: int, engine: Engine, owner: OwnerDep,
                     peer: Annotated[str, Form()] = "",
                     not_sec: Annotated[str, Form()] = "") -> RedirectResponse:  # fmt: skip
        """Add a product-market peer (any SIC) or a non-SEC peer by name to an open
        `m04_peer` item; the item's Confirm stores the set."""
        from engine.financials import peers as m04_peers

        it = review.get(engine, item_id)
        if it is None or it.kind != "m04_peer" or it.resolved_at or not it.cik:
            raise HTTPException(404, "No open peer item.")
        now = datetime.now(UTC)
        engine.execute("BEGIN")
        try:
            c = m04_peers.add_peer(engine, it.cik, peer, bool(not_sec), now)
            engine.execute("COMMIT")
        except m04_peers.PeerError as e:
            engine.execute("ROLLBACK")
            return RedirectResponse(f"/m04/setup?error={quote(str(e))}#peer-{item_id}", 303)
        except Exception:
            engine.execute("ROLLBACK")
            raise
        msg = f"{it.ticker or it.cik}: {c.name} added" + (f" ({m04_peers.NOT_SEC})" if not c.cik
                                                           else "")  # fmt: skip
        return RedirectResponse(f"/m04/setup?msg={quote(msg)}#peer-{item_id}", 303)

    # --- M04 survival gate (Part 4a; D-UI-28, D-M04-86) ---------------------------------

    def m04_gate_back(ticker: str, msg: str) -> RedirectResponse:
        return RedirectResponse(f"/c/{ticker}?tab=financials&msg={quote(msg)}#gate", 303)

    def m04_gate_recompute(engine: sqlite3.Connection, ticker: str, cik: str) -> str:
        from engine.financials import gate_step, profile

        cg = gate_step.company_gate(
            engine, ticker, cik, datetime.now(UTC),
            queue_items=cik in profile.full_scope(engine, m04_companies(engine)).values(),
        )  # fmt: skip
        return f"gate recomputed: {cg.gate.state}, runway {cg.gate.runway_text()}"

    @app.post("/m04/gate/{ticker}/credit-line")
    def m04_credit_line_add(
        ticker: str, engine: Engine, owner: OwnerDep,
        facility: Annotated[str, Form()] = "", amount: Annotated[str, Form()] = "",
        maturity: Annotated[str, Form()] = "", as_of: Annotated[str, Form()] = "",
        source: Annotated[str, Form()] = "", note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:  # fmt: skip
        """ "Add confirmed credit line" (D-M04-86): the owner is the confirmer; the gate
        recomputes at once."""
        from engine.financials import gate_view as m04_gate_view

        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        try:
            lid = m04_gate_view.add_credit_line(
                engine, cik, facility, amount, maturity, as_of, source, owner.id,
                datetime.now(UTC), note,
            )  # fmt: skip
        except m04_gate_view.CreditLineError as e:
            return m04_gate_back(ticker, f"Credit line not added: {e}")
        return m04_gate_back(ticker, f"Credit line {lid} added; "
                             + m04_gate_recompute(engine, ticker, cik))  # fmt: skip

    @app.post("/m04/gate/{ticker}/credit-line/{line_id}/withdraw")
    def m04_credit_line_withdraw(ticker: str, line_id: int, engine: Engine,
                                 owner: OwnerDep) -> RedirectResponse:  # fmt: skip
        from engine.financials import gate_view as m04_gate_view

        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        ok = m04_gate_view.withdraw_credit_line(engine, cik, line_id, owner.id, datetime.now(UTC))
        msg = (
            f"Credit line {line_id} withdrawn"
            if ok
            else f"Credit line {line_id}: nothing to withdraw"
        )
        return m04_gate_back(ticker, msg + "; " + m04_gate_recompute(engine, ticker, cik))

    @app.post("/m04/gate/{ticker}/recompute")
    def m04_gate_recompute_route(ticker: str, engine: Engine, owner: OwnerDep) -> RedirectResponse:
        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        return m04_gate_back(ticker, m04_gate_recompute(engine, ticker, cik))

    # --- M04 CvD (Part 8a; D-UI-31, D-M04-68) ----------------------------------------------

    @app.get("/m04", response_class=HTMLResponse)
    def m04_cvd_page(request: Request, engine: Engine, viewer: ViewerDep):
        """The watchlist summary: one CvD line per company from the last local pass."""
        from engine.financials import cvd_step

        items = [r[0] for r in engine.execute(
            "SELECT item_id FROM review_queue WHERE kind = 'm04_cvd' AND resolved_at IS NULL "
            "ORDER BY item_id")]  # fmt: skip
        view = {"everyone": cvd_step.stored_lines(engine, m04_companies(engine))}
        ctx = frame(engine) | {"viewer": viewer, "v": view, "items": items}
        return templates.TemplateResponse(request, "m04_cvd.html", ctx)

    def m04_cvd_back(ticker: str, msg: str = "", error: str = "") -> RedirectResponse:
        q = f"&msg={quote(msg)}" if msg else f"&detail={quote(error)}"
        return RedirectResponse(f"/c/{ticker}?tab=m04{q}#share", 303)

    def m04_cvd_recompute(engine: sqlite3.Connection, ticker: str, cik: str) -> str:
        from engine.financials import cvd_step, profile

        scope = set(profile.full_scope(engine, m04_companies(engine)).values())
        cc = cvd_step.company_cvd(engine, ticker, cik, datetime.now(UTC),
                                  queue_items=cik in scope)  # fmt: skip
        return f"CvD recomputed: {cc.c.state or cc.c.excluded or cc.c.missing}"

    @app.post("/m04/share/{ticker}")
    def m04_share_add(
        ticker: str,
        engine: Engine,
        owner: OwnerDep,
        period_end: Annotated[str, Form()] = "",
        share_pct: Annotated[str, Form()] = "",
        market: Annotated[str, Form()] = "",
        source: Annotated[str, Form()] = "",
        market_size: Annotated[str, Form()] = "",
        source_url: Annotated[str, Form()] = "",
        kind: Annotated[str, Form()] = "third_party",
        note: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        from engine.financials import cvd_view, market_share

        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        form = {"period_end": period_end, "share_pct": share_pct, "market": market,
                "source": source, "market_size": market_size, "source_url": source_url,
                "kind": kind, "note": note}  # fmt: skip
        try:
            sid = cvd_view.add_share(engine, cik, form, owner.id, datetime.now(UTC))
        except market_share.ShareError as e:
            return m04_cvd_back(ticker, error=str(e))
        return m04_cvd_back(
            ticker, f"market share {sid} added; {m04_cvd_recompute(engine, ticker, cik)}"
        )

    @app.post("/m04/share/{ticker}/{share_id}/withdraw")
    def m04_share_withdraw(ticker: str, share_id: int, engine: Engine,
                           owner: OwnerDep) -> RedirectResponse:  # fmt: skip
        from engine.financials import cvd_view

        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        ok = cvd_view.withdraw_share(engine, cik, share_id, owner.id, datetime.now(UTC))
        if not ok:
            return m04_cvd_back(ticker, error=f"market share {share_id}: nothing to withdraw")
        return m04_cvd_back(ticker, f"market share {share_id} withdrawn; "
                            f"{m04_cvd_recompute(engine, ticker, cik)}")  # fmt: skip

    @app.get("/api/bars/{ticker}")
    def bars_api(ticker: str, engine: Engine, viewer: ViewerDep, bar: str = "D") -> JSONResponse:
        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        events = services.earnings_dates(engine, cik) if cik else []
        b = prices.bars(engine, ticker, "W" if bar.upper() == "W" else "D",
                        datetime.now(UTC).date(), events)  # fmt: skip
        return JSONResponse(
            {
                "symbol": b.symbol,
                "bar": b.bar,
                "bars": b.bars,
                "last_date": b.last_date,
                "stale": b.stale,
                "markers": b.markers,
            }  # fmt: skip
        )

    @app.post("/c/{ticker}/prices")
    def fetch_prices(ticker: str, engine: Engine, owner: OwnerDep) -> RedirectResponse:
        """One Tiingo request for this symbol (owner only, U2): peers on demand (D-UI-3)."""
        ticker = ticker.upper()
        cik = services.resolve_ticker(engine, ticker)
        if cik is None:
            raise HTTPException(404, f"Unknown ticker {ticker}.")
        try:
            client = settings.tiingo_factory(engine) if settings.tiingo_factory else TiingoClient(
                token_from_env(), engine, min_interval_s=0)  # fmt: skip
        except MissingKey:
            return RedirectResponse(f"/c/{ticker}?msg=no-key", status_code=303)
        u = prices.update_symbol(engine, client, ticker, cik, datetime.now(UTC))
        return RedirectResponse(f"/c/{ticker}?msg={u.outcome}", status_code=303)

    @app.get("/doc/{accession}", response_class=HTMLResponse)
    def doc_page(
        request: Request,
        accession: str,
        engine: Engine,
        corpus: Corpus,
        viewer: ViewerDep,
        file: str | None = None,
        section: int | None = None,
        start: int | None = None,
        end: int | None = None,
    ):
        view = services.reader(corpus, accession, file, section, start, end)
        if view is None:
            raise HTTPException(404, "That filing has no stored documents.")
        row = engine.execute(
            "SELECT f.form, f.filed, t.ticker FROM filing f LEFT JOIN ticker t ON t.cik = f.cik "
            "AND t.valid_to IS NULL WHERE f.accession = ? LIMIT 1",
            (accession,),
        ).fetchone()
        call = engine.execute(
            "SELECT d.quarter, d.stated_on, t.ticker FROM call_document d LEFT JOIN ticker t "
            "ON t.cik = d.cik AND t.valid_to IS NULL WHERE d.accession = ? LIMIT 1",
            (accession,),
        ).fetchone()
        ctx = frame(engine) | {
            "viewer": viewer,
            "view": view,
            "form": row["form"] if row else (f"Call {call['quarter']}" if call else None),
            "filed": row["filed"] if row else (call["stated_on"] if call else None),
            "ticker": row["ticker"] if row else (call["ticker"] if call else None),
            "sec_url": services.filing_index_url(view.cik, accession) if is_sec(accession)
            else None,
        }  # fmt: skip
        return templates.TemplateResponse(request, "doc.html", ctx)

    @app.get("/source/{accession}/{filename}", response_class=HTMLResponse)
    def source_page(
        request: Request,
        accession: str,
        filename: str,
        engine: Engine,
        corpus: Corpus,
        viewer: ViewerDep,
        start: int = 0,
        end: int = 0,
        sha: str | None = None,
    ):
        view = services.source(corpus, accession, filename, start, end, sha)
        if view is None:
            raise HTTPException(404, "That document is not stored.")
        ctx = frame(engine) | {"viewer": viewer, "view": view}
        return templates.TemplateResponse(request, "source.html", ctx)

    return app
