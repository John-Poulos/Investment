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
    ("insiders", "Insiders", True),
    ("events", "Events and filings", True),
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
    templates.env.globals["FORECAST_NOTE"] = FORECAST_NOTE
    templates.env.filters["money"] = mf_views.money  # M02 part 3
    templates.env.globals["payload_value"] = mf_views.payload_value
    templates.env.globals["fin_kinds"] = fin_views.KIND_LABELS  # M02 part 5b
    templates.env.globals["dso_band"] = fin_views.credit.band

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
        elif tab == "financials":
            ctx["tables"] = services.financials(engine, cik)
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
        ctx = frame(engine) | {"viewer": viewer, "d": d, "mf": mf}
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
    ) -> RedirectResponse:
        """Owner-only review actions (U2); each closes the item with who, when and note (U3)."""
        now = datetime.now(UTC)
        done = action
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
