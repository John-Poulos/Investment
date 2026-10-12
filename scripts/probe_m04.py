"""M04 design-review probe (docs/m04_review/PROBES.md). Owner runs it once; send the log back.

    uv run python scripts/probe_m04.py                     # every probe, about 5 minutes
    uv run python scripts/probe_m04.py --only S5,T2,L7     # some probes
    uv run python scripts/probe_m04.py --no-sec --no-tiingo  # local probes only
    uv run python scripts/probe_m04.py --list              # the probe table, no run

Combines the review gap checks (docs/m04_review/{R1..R6,BP}_gaps.md) into one run:
L = local, read-only queries of data/engine.db and data/corpus.db (0 requests);
S = SEC requests through the engine's SecClient (5/s pacing, SEC_USER_AGENT from .env,
typed results); T = Tiingo (supported-tickers file, no key; meta endpoint with the key).

Read-only: raw SEC responses are read from the http_cache when already there but never
written to it; nothing is written to document, fact, filing or price_bar. The only rows
written are fetch_log entries, one per request (the request log that Tiingo's budget
counts). Each probe prints a few lines; a failing probe prints its error and the run goes
on. Writes logs/probe_m04_<time>.txt as it goes (no redirect needed).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import traceback
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.sec.client import cache_key  # noqa: E402
from engine.sec.documents import (  # noqa: E402
    extract_text,
    filing_folder,
    html_to_text,
    parse_filing_index,
)
from engine.sec.results import Empty, Failed, NotFound, Ok  # noqa: E402

SEC_TTL = 3650 * 86400  # cache reads only; this probe never writes the cache
DATA = "https://data.sec.gov"
ARCH = "https://www.sec.gov/Archives/edgar/data"
TIINGO_ZIP = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
ANNUAL = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F")
# Delisted / recycled tickers for the M04 Part 8 episodes (R1 #6, R6 #3, BP #3).
DELISTED = (
    "BBBY", "BBBYQ", "RAD", "RADCQ", "JCP", "JCPNQ", "SHLD", "SHLDQ", "RSH", "RSHCQ",
    "FIT", "NVTA", "NVTAQ", "BTU", "BTUUQ", "CHK", "CHKAQ", "GPRO",
)  # fmt: skip
CIK = {"NVTA": 1501134, "GE": 40545, "GOOG_INC": 1288776, "RIVN": 1874178,
       "BBBY": 886158, "RAD": 84129, "SPCX": 1181412}  # fmt: skip


# --- context: lazy clients, memo, request counts ---------------------------------------


class ReadOnlyCache:
    """Reads the engine's http_cache; never writes it."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def get(self, key, now):
        return self._inner.get(key, now)

    def put(self, *args, **kwargs) -> None:
        return None


class CountingLog:
    def __init__(self, inner, ctx: Ctx) -> None:
        self._inner, self._ctx = inner, ctx

    def write(self, url, outcome, detail, status, from_cache, at) -> None:
        self._inner.write(url, outcome, detail, status, from_cache, at)
        if not from_cache:
            self._ctx.sec_sent += 1


class Ctx:
    def __init__(self, engine, corpus) -> None:
        self.engine, self.corpus = engine, corpus
        self.sec_sent = 0
        self.tiingo_sent = 0
        self._client = None
        self._tiingo = None
        self._memo: dict[str, Any] = {}

    @property
    def client(self):
        if self._client is None:
            from engine.sec.client import SecClient, user_agent_from_env
            from engine.store.http import SqliteCache, SqliteFetchLog

            self._client = SecClient(
                user_agent_from_env(),
                cache=ReadOnlyCache(SqliteCache(self.corpus)),
                log=CountingLog(SqliteFetchLog(self.engine), self),
            )
        return self._client

    @property
    def tiingo(self):
        if self._tiingo is None:
            from engine.prices.tiingo import TiingoClient, token_from_env

            self._tiingo = TiingoClient(token_from_env(), self.engine)
        return self._tiingo

    def sec_paused(self) -> float:
        return self._client.paused_for() if self._client is not None else 0.0

    def get(self, url: str, params: dict | None = None):
        key = cache_key(url, params)
        if key not in self._memo:
            self._memo[key] = self.client.get_bytes(url, params, ttl_s=SEC_TTL)
        return self._memo[key]

    def text(self, url: str):
        res = self.get(url)
        if not isinstance(res, Ok):
            return res
        return Ok(res.data.decode("utf-8", errors="replace"), source_ref=res.source_ref)

    def json(self, url: str):
        res = self.get(url)
        if not isinstance(res, Ok):
            return res
        try:
            return Ok(json.loads(res.data), source_ref=res.source_ref)
        except ValueError as exc:
            return Failed(f"invalid JSON: {exc}", url=url)


# --- small helpers ---------------------------------------------------------------------


def cik10(n: int | str) -> str:
    return f"{int(n):010d}"


def describe(res) -> str:
    if isinstance(res, NotFound):
        return f"not found (HTTP {res.status}) {res.url}"
    if isinstance(res, Failed):
        return f"failed: {res.reason}{' (throttled)' if res.throttled else ''}"
    if isinstance(res, Empty):
        return "empty: " + "; ".join(f"{p.path} {p.query}: {p.result}" for p in res.paths_checked)
    return "ok"


def usd(v) -> str:
    if v is None:
        return "missing"
    return f"{float(v) / 1e6:,.1f}M"


def days(start: str | None, end: str) -> int | None:
    if not start:
        return None
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def ticker_cik(ctx: Ctx, ticker: str) -> str | None:
    row = ctx.engine.execute(
        "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL LIMIT 1", (ticker.upper(),)
    ).fetchone()
    return row[0] if row else None


def watchlist(ctx: Ctx) -> dict[str, str]:
    from engine.refresh import load_config

    out = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if c := ticker_cik(ctx, t):
            out[t] = c
    return out


def _sentence(text: str, s: int, e: int, width: int) -> str:
    lo, hi = max(0, s - width), min(len(text), e + width)
    left = max(text.rfind(". ", lo, s), text.rfind("\n", lo, s))
    start = left + 1 if left >= 0 else lo
    ends = [x for x in (text.find(". ", e, hi), text.find("\n", e, hi)) if x >= 0]
    end = min(ends) + 1 if ends else hi
    return " ".join(text[start:end].split())


def snips(text: str, pattern: str, cap: int = 4, width: int = 300, indent: str = "    "):
    """Sentences (or table lines) around matches, with offsets; overlapping matches merged."""
    rx = re.compile(pattern, re.IGNORECASE)
    found = list(rx.finditer(text))
    out, last = [], -1
    for m in found:
        if m.start() <= last:
            continue
        sent = _sentence(text, m.start(), m.end(), width)
        last = m.end() + width // 2
        out.append(f"{indent}@{m.start()}: “{sent[: 2 * width]}”")
        if len(out) >= cap:
            break
    head = f"{indent[:-2]}/{pattern}/: {len(found)} match(es)"
    return [head, *out]


def doc_text(ctx: Ctx, url: str) -> tuple[str | None, str]:
    """Stored document text if the corpus has the URL, else fetched (not stored)."""
    row = ctx.corpus.execute("SELECT text FROM document WHERE url = ?", (url,)).fetchone()
    if row:
        return row[0], "stored in corpus"
    res = ctx.get(url)
    if not isinstance(res, Ok):
        return None, describe(res)
    text, _ = extract_text(res.data, url.rsplit("/", 1)[-1])
    return text, f"fetched {len(res.data) / 1e6:.1f} MB"


def index_page(ctx: Ctx, cik, acc: str) -> tuple[str | None, str]:
    folder = filing_folder(str(cik), acc)
    for name in (f"{acc}-index.htm", f"{acc}-index.html"):
        res = ctx.text(f"{folder}/{name}")
        if isinstance(res, Ok):
            return res.data, f"{folder}/{name}"
        if not isinstance(res, NotFound):
            return None, describe(res)
    return None, "filing index not found"


def index_docs(ctx: Ctx, cik, acc: str):
    html, where = index_page(ctx, cik, acc)
    if html is None:
        return None, where
    try:
        return parse_filing_index(html), where
    except ValueError as exc:
        return None, f"index unreadable: {exc}"


_XML_HREF = re.compile(r'href="([^"]+\.xml)"', re.IGNORECASE)
_NOT_INSTANCE = ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml", "filingsummary.xml")


def instance_href(html: str) -> str | None:
    """The XBRL instance in a filing index (pre-inline `x-2016.xml` or inline `_htm.xml`)."""
    for href in _XML_HREF.findall(html):
        low = href.lower()
        if low.endswith(_NOT_INSTANCE) or "xsl" in low:
            continue
        return href if href.startswith("http") else "https://www.sec.gov" + href
    return None


_XBRLI = "{http://www.xbrl.org/2003/instance}"


def instance_facts(data: bytes) -> list[tuple[str, str, str | None, str, float]]:
    """(prefix, tag, start, end, value) for numeric facts on contexts without dimensions."""
    prefixes: dict[str, str] = {}
    contexts: dict[str, tuple[str | None, str] | None] = {}
    raw: list[tuple[str, str, str, str]] = []
    for event, item in ET.iterparse(io.BytesIO(data), events=("start-ns", "end")):
        if event == "start-ns":
            prefixes.setdefault(item[1], item[0])
            continue
        el = item
        if el.tag == f"{_XBRLI}context":
            dims = el.find(f".//{_XBRLI}segment") is not None
            dims = dims or el.find(f".//{_XBRLI}scenario") is not None
            p = el.find(f"{_XBRLI}period")
            inst = p.findtext(f"{_XBRLI}instant") if p is not None else None
            s = p.findtext(f"{_XBRLI}startDate") if p is not None else None
            e = p.findtext(f"{_XBRLI}endDate") if p is not None else None
            per = (None, inst.strip()) if inst else ((s.strip(), e.strip()) if s and e else None)
            contexts[el.get("id", "")] = None if dims else per
            el.clear()
        elif el.get("contextRef") and el.get("unitRef") and el.tag.startswith("{"):
            if el.text and el.text.strip():
                uri, tag = el.tag[1:].split("}", 1)
                raw.append((uri, tag, el.get("contextRef", ""), el.text.strip()))
            el.clear()
    out, seen = [], set()
    for uri, tag, ref, txt in raw:
        per = contexts.get(ref)
        if per is None:
            continue
        try:
            value = float(txt.replace(",", ""))
        except ValueError:
            continue
        key = (uri, tag, per)
        if key in seen:
            continue
        seen.add(key)
        out.append((prefixes.get(uri, uri), tag, per[0], per[1], value))
    return out


def filing_summary(ctx: Ctx, cik, acc: str) -> tuple[list[dict] | None, str]:
    url = f"{filing_folder(str(cik), acc)}/FilingSummary.xml"
    res = ctx.get(url)
    if not isinstance(res, Ok):
        return None, describe(res)
    root = ET.fromstring(res.data)
    keys = ("Position", "ShortName", "LongName", "HtmlFileName", "XmlFileName", "MenuCategory")
    return [{k: (r.findtext(k) or "") for k in keys} for r in root.iter("Report")], url


def r_page_text(ctx: Ctx, cik, acc: str, report: dict) -> tuple[str | None, str]:
    name = report.get("HtmlFileName") or report.get("XmlFileName")
    if not name:
        return None, "report has no file name"
    url = f"{filing_folder(str(cik), acc)}/{name}"
    res = ctx.text(url)
    if not isinstance(res, Ok):
        return None, describe(res)
    if name.lower().endswith(".xml"):
        body = re.sub(r"</(Row|Column)>", "\n", res.data)
        body = re.sub(r"<[^>]+>", " ", body)
        return "\n".join(" ".join(x.split()) for x in body.splitlines() if x.strip()), url
    return html_to_text(res.data), url


def lines_with(text: str, pattern: str, cap: int = 12, width: int = 220) -> list[str]:
    rx = re.compile(pattern, re.IGNORECASE)
    out = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if line and rx.search(line):
            out.append(f"    {line[:width]}")
            if len(out) >= cap:
                break
    return out


def submissions(ctx: Ctx, cik, since: str | None = None):
    """(company name, filings) from submissions JSON, older pages only back to `since`."""
    from engine.sec.submissions import parse_filing_arrays

    res = ctx.json(f"{DATA}/submissions/CIK{cik10(cik)}.json")
    if not isinstance(res, Ok):
        return None, describe(res)
    data = res.data
    out = parse_filing_arrays(cik10(cik), data["filings"]["recent"])
    for page in data["filings"].get("files") or []:
        if not since or (page.get("filingTo") or "") < since:
            continue
        r2 = ctx.json(f"{DATA}/submissions/{page['name']}")
        if isinstance(r2, Ok):
            out += parse_filing_arrays(cik10(cik), r2.data)
    return data.get("name"), out


def find_filing(ctx: Ctx, cik, form: str, report_date: str):
    """(accession, primary_doc) from the stored index, else from submissions."""
    row = ctx.engine.execute(
        "SELECT accession, primary_doc FROM filing WHERE cik = ? AND form = ? AND report_date = ?"
        " ORDER BY filed LIMIT 1",
        (cik10(cik), form, report_date),
    ).fetchone()
    if row:
        return row[0], row[1], "stored index"
    _, filings = submissions(ctx, cik, since=report_date)
    if isinstance(filings, str):
        return None, None, filings
    for f in sorted(filings, key=lambda f: f.filed):
        if f.form == form and f.report_date == report_date:
            return f.accession, f.primary_doc, "submissions"
    return None, None, f"no {form} for period {report_date}"


def concept(ctx: Ctx, cik, taxonomy: str, tag: str):
    return ctx.json(f"{DATA}/api/xbrl/companyconcept/CIK{cik10(cik)}/{taxonomy}/{tag}.json")


def first_filed(rows: list[dict]) -> dict[tuple, dict]:
    """First-filed row per (start, end)."""
    out: dict[tuple, dict] = {}
    for r in sorted(rows, key=lambda r: r.get("filed") or ""):
        out.setdefault((r.get("start"), r["end"]), r)
    return out


def fy_series(ctx: Ctx, cik: str, tag: str, flow: bool, since: str = "2012-01-01"):
    """{period_end: value} first filed in an annual report; flows = 330–380-day periods."""
    q = ",".join("?" * len(ANNUAL))
    rows = ctx.engine.execute(
        f"SELECT period_start, period_end, value FROM fact WHERE cik = ? AND tag = ? AND "
        f"unit = 'USD' AND form IN ({q}) AND period_end >= ? ORDER BY period_end, filed",
        (cik, tag, *ANNUAL, since),
    ).fetchall()
    out: dict[str, float] = {}
    for s, e, v in rows:
        n = days(s, e)
        if (flow and n is not None and 330 <= n <= 380) or (not flow and s is None):
            out.setdefault(e, float(v))
    return out


def stored_docs(ctx: Ctx, cik: str, types: tuple[str, ...] | None = None) -> list:
    sql = "SELECT doc_id, accession, doc_type, filename, url FROM document WHERE cik = ?"
    args: list = [cik]
    if types:
        sql += f" AND doc_type IN ({','.join('?' * len(types))})"
        args += list(types)
    return ctx.corpus.execute(sql + " ORDER BY accession", args).fetchall()


def text_of(ctx: Ctx, doc_id: int) -> str:
    return ctx.corpus.execute("SELECT text FROM document WHERE doc_id = ?", (doc_id,)).fetchone()[0]


def filed_of(ctx: Ctx, acc: str) -> str:
    row = ctx.engine.execute(
        "SELECT form, filed, report_date FROM filing WHERE accession = ?", (acc,)
    ).fetchone()
    return f"{row[0]} filed {row[1]} period {row[2]}" if row else "not in stored index"


# --- local probes (0 requests) ---------------------------------------------------------


def l1_greenwald(ctx: Ctx) -> list[str]:
    out = ["  $M, first filed in an annual report, keyed by fiscal year-end year"]
    flows = (
        "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
        "Depreciation", "DepreciationDepletionAndAmortization",
    )  # fmt: skip
    for t in ("MU", "INTC", "MSFT"):
        cik = ticker_cik(ctx, t)
        if not cik:
            out.append(f"  {t}: no CIK in the ticker map")
            continue
        ppe = [
            r[0]
            for r in ctx.engine.execute(
                "SELECT DISTINCT tag FROM fact WHERE cik = ? AND tag LIKE "
                "'PropertyPlantAndEquipment%' AND period_start IS NULL AND unit = 'USD' AND "
                "(tag LIKE '%Gross%' OR tag LIKE '%Net' OR tag LIKE '%BeforeAccumulated%' "
                "OR tag LIKE '%AfterAccumulated%')",
                (cik,),
            )
        ]
        out.append(f"  {t} ({cik}):")
        for tag, flow in [(x, True) for x in flows] + [(x, False) for x in sorted(ppe)]:
            s = fy_series(ctx, cik, tag, flow)
            if s:
                vals = " · ".join(f"{e[:4]} {v / 1e6:,.0f}" for e, v in s.items())
                out.append(f"    {tag}: {vals}")
    return out


def l2_r2_tags(ctx: Ctx) -> list[str]:
    out = []
    nv, mr, ts, gf = (ticker_cik(ctx, t) for t in ("NVDA", "MRVL", "TSLA", "GFS"))

    def latest_fy_end(cik: str) -> str | None:
        q = ",".join("?" * len(ANNUAL))
        row = ctx.engine.execute(
            f"SELECT max(period_end) FROM fact WHERE cik = ? AND tag IN ('Assets') AND form IN "
            f"({q}) AND period_start IS NULL",
            (cik, *ANNUAL),
        ).fetchone()
        return row[0] if row else None

    if nv and (end := latest_fy_end(nv)):
        rows = ctx.engine.execute(
            "SELECT DISTINCT taxonomy, tag, value FROM fact WHERE cik = ? AND period_end = ? AND "
            "period_start IS NULL AND unit = 'USD' AND (abs(value - 51951e6) <= 520e6 OR "
            "abs(value - 10605e6) <= 106e6 OR abs(value - 62556e6) <= 630e6)",
            (nv, end),
        ).fetchall()
        out.append(f"  NVDA instants at {end} near 51,951M / 10,605M / 62.6B: {len(rows)}")
        out += [f"    {r[0]}:{r[1]} = {usd(r[2])}" for r in rows[:15]]
    if mr and (end := latest_fy_end(mr)):
        rows = ctx.engine.execute(
            "SELECT DISTINCT tag, period_start, value FROM fact WHERE cik = ? AND period_end = ?"
            " AND tag LIKE 'Proceeds%' AND unit = 'USD' AND period_start IS NOT NULL",
            (mr, end),
        ).fetchall()
        rows = [r for r in rows if 330 <= (days(r[1], end) or 0) <= 380]
        out.append(f"  MRVL Proceeds* for the year ending {end}: {len(rows)}")
        out += [f"    {r[0]} = {usd(r[2])}" for r in rows[:20]]
    if ts:
        for end in ("2022-12-31", "2023-12-31"):
            rows = ctx.engine.execute(
                "SELECT DISTINCT tag, period_start, value FROM fact WHERE cik = ? AND "
                "period_end = ? AND unit = 'USD' AND (tag LIKE 'LongTermDebt%' OR "
                "tag LIKE 'Proceeds%')",
                (ts, end),
            ).fetchall()
            keep = [r for r in rows if r[1] is None or 330 <= (days(r[1], end) or 0) <= 380]
            out.append(f"  TSLA LongTermDebt* / Proceeds* at {end}: {len(keep)}")
            out += [
                f"    {r[0]} {'(year)' if r[1] else '(instant)'} = {usd(r[2])}" for r in keep[:20]
            ]
    if gf:
        tax = ctx.engine.execute(
            "SELECT taxonomy, count(*), min(period_end), max(period_end) FROM fact WHERE cik = ? "
            "GROUP BY taxonomy",
            (gf,),
        ).fetchall()
        out.append(
            "  GFS facts by taxonomy: " + "; ".join(f"{a} {b} ({c}..{d})" for a, b, c, d in tax)
        )
        forms = ctx.engine.execute(
            "SELECT form, count(*), max(filed) FROM fact WHERE cik = ? GROUP BY form", (gf,)
        ).fetchall()
        out.append("  GFS facts by form: " + "; ".join(f"{a} {b} (last {c})" for a, b, c in forms))
        end = latest_fy_end(gf)
        rx = re.compile(
            r"Revenue|CostOfSales|Receivable|PropertyPlantAndEquipment|Depreciation|"
            r"SellingGeneral|Borrowings|OperatingActivities|CurrentAssets|CurrentLiabilities|"
            r"^Assets$|^Liabilities$|ProfitLoss|RetainedEarnings"
        )
        if end:
            rows = ctx.engine.execute(
                "SELECT DISTINCT taxonomy, tag, period_start, value FROM fact WHERE cik = ? AND "
                "period_end = ? AND unit = 'USD' ORDER BY taxonomy, tag",
                (gf, end),
            ).fetchall()
            keep = [r for r in rows if rx.search(r[1])]
            out.append(f"  GFS M/F-score input tags at {end}: {len(keep)} of {len(rows)} tags")
            out += [
                f"    {r[0]}:{r[1]} {'(dur)' if r[2] else '(inst)'} = {usd(r[3])}"
                for r in keep[:30]
            ]
    return out


def l3_spcx_filings(ctx: Ctx) -> list[str]:
    cik = ticker_cik(ctx, "SPCX") or cik10(CIK["SPCX"])
    rows = ctx.engine.execute(
        "SELECT form, filed, report_date, accession FROM filing WHERE cik = ? AND (form LIKE "
        "'10-K%' OR form LIKE '10-Q%' OR form LIKE '424B%' OR form LIKE 'S-1%') ORDER BY filed",
        (cik,),
    ).fetchall()
    n10k = sum(1 for r in rows if r[0].startswith("10-K"))
    out = [f"  SPCX ({cik}): {n10k} 10-K/10-K/A in the stored index; periodic + 424B + S-1:"]
    out += [f"    {r[0]} filed {r[1]} period {r[2]} {r[3]}" for r in rows[-15:]]
    return out


def l4_spcx_conversion(ctx: Ctx) -> list[str]:
    cik = ticker_cik(ctx, "SPCX") or cik10(CIK["SPCX"])
    out = []
    for d in stored_docs(ctx, cik, ("10-Q", "10-Q/A", "10-K")):
        text = text_of(ctx, d["doc_id"])
        out.append(f"  {d['doc_type']} {d['accession']} ({filed_of(ctx, d['accession'])}):")
        out += snips(text, r"conversion of|convertible preferred|6,728", cap=8, width=260)
    rows = ctx.engine.execute(
        "SELECT tag, period_start, period_end, value, form, accession FROM fact WHERE cik = ? AND "
        "(tag LIKE '%Conversion%' OR tag LIKE 'ConversionOfStock%') ORDER BY period_end DESC",
        (cik,),
    ).fetchall()
    out.append(f"  SPCX conversion-related facts (non-dimensional): {len(rows)}")
    out += [f"    {r[0]} {r[1]}..{r[2]} = {float(r[3]):,.0f} {r[4]} {r[5]}" for r in rows[:12]]
    return out or ["  no stored SPCX 10-Q/10-K text"]


def l5_infq_frames(ctx: Ctx) -> list[str]:
    cik = ticker_cik(ctx, "INFQ")
    if not cik:
        return ["  INFQ not in the ticker map"]
    out = []
    for d in stored_docs(ctx, cik):
        text = text_of(ctx, d["doc_id"])
        if re.search(r"46,186|39,808", text):
            out.append(f"  {d['doc_type']} {d['accession']} ({filed_of(ctx, d['accession'])}):")
            out += snips(text, r"46,186|39,808", cap=4, width=300)
    if not out:
        out.append("  '46,186' / '39,808' in no stored INFQ document")
    rows = ctx.engine.execute(
        "SELECT period_start, period_end, value, accession, form, fp, frame FROM fact WHERE "
        "cik = ? AND tag = 'WeightedAverageNumberOfSharesOutstandingBasic' ORDER BY period_end, "
        "filed",
        (cik,),
    ).fetchall()
    out.append(f"  INFQ WeightedAverageNumberOfSharesOutstandingBasic: {len(rows)} fact(s)")
    out += [
        f"    {r[0]}..{r[1]} {float(r[2]):,.0f} {r[4]} fp={r[5]} frame={r[6]} {r[3]}" for r in rows
    ][:20]
    return out


def l6_mstr_notes(ctx: Ctx) -> list[str]:
    cik = ticker_cik(ctx, "MSTR")
    if not cik:
        return ["  MSTR not in the ticker map"]
    docs = stored_docs(ctx, cik, ("10-Q", "10-Q/A"))
    if not docs:
        return ["  no stored MSTR 10-Q"]
    d = max(docs, key=lambda d: filed_of(ctx, d["accession"]))
    text = text_of(ctx, d["doc_id"])
    out = [f"  {d['doc_type']} {d['accession']} ({filed_of(ctx, d['accession'])}):"]
    out += lines_with(text, r"(convertible (senior )?notes|notes due 20\d\d).{0,80}\d", cap=14)
    out.append("  ATM / at-the-market lines:")
    out += lines_with(text, r"\bATM\b|at-the-market", cap=12, width=260)
    out.append("  STRK / STRF / STRD / STRC lines:")
    out += lines_with(text, r"\bSTR[KFDC]\b.{0,120}\d", cap=8)
    return out


Z_TAGS = {
    "CA": ("AssetsCurrent", "CurrentAssets"),
    "CL": ("LiabilitiesCurrent", "CurrentLiabilities"),
    "TA": ("Assets",),
    "TL": ("Liabilities",),
    "RE": ("RetainedEarningsAccumulatedDeficit", "RetainedEarnings"),
    "EBIT": ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities"),
    "S": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "Revenue",
          "SalesRevenueNet"),
    "EQ": ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
           "StockholdersEquity", "Equity"),
}  # fmt: skip
FLOW_KEYS = ("EBIT", "S")


def _z_inputs(ctx: Ctx, cik: str) -> tuple[str | None, str | None, dict[str, float | None]]:
    q = ",".join("?" * len(ANNUAL))
    row = ctx.engine.execute(
        f"SELECT period_end, accession FROM fact WHERE cik = ? AND tag = 'Assets' AND form IN "
        f"({q}) AND period_start IS NULL ORDER BY period_end DESC, filed LIMIT 1",
        (cik, *ANNUAL),
    ).fetchone()
    if not row:
        return None, None, {}
    end, acc = row
    vals: dict[str, float | None] = {}
    for key, tags in Z_TAGS.items():
        vals[key] = None
        for tag in tags:
            rows = ctx.engine.execute(
                "SELECT period_start, value FROM fact WHERE cik = ? AND tag = ? AND period_end = ?"
                " AND unit = 'USD' ORDER BY filed",
                (cik, tag, end),
            ).fetchall()
            for s, v in rows:
                n = days(s, end)
                if (key in FLOW_KEYS and n and 330 <= n <= 380) or (
                    key not in FLOW_KEYS and s is None
                ):
                    vals[key] = float(v)
                    break
            if vals[key] is not None:
                break
    return end, acc, vals


def l7_altman_z(ctx: Ctx) -> list[str]:
    out = [
        "  Manufacturer Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5 (latest 10-K/20-F;"
        " MVE = close on/before the balance-sheet date × dei shares of that report)"
    ]
    skipped = []
    for t, cik in watchlist(ctx).items():
        row = ctx.engine.execute("SELECT sic FROM entity WHERE cik = ?", (cik,)).fetchone()
        sic = row[0] if row else None
        if not sic or not sic.isdigit() or not 2000 <= int(sic) <= 3999:
            skipped.append(f"{t} {sic}")
            continue
        end, acc, v = _z_inputs(ctx, cik)
        if not end:
            out.append(f"  {t} SIC {sic}: no annual balance sheet in stored facts")
            continue
        tl_note = ""
        if v["TL"] is None and v["TA"] is not None and v["EQ"] is not None:
            v["TL"], tl_note = v["TA"] - v["EQ"], " (TL = TA − equity)"
        sh = ctx.engine.execute(
            "SELECT period_end, value FROM fact WHERE cik = ? AND tag = "
            "'EntityCommonStockSharesOutstanding' AND accession = ?",
            (cik, acc),
        ).fetchall()
        shares = sum(float(r[1]) for r in sh) if sh else None
        px = ctx.engine.execute(
            "SELECT date, close FROM price_bar WHERE symbol = ? AND date <= ? ORDER BY date DESC "
            "LIMIT 1",
            (t, end),
        ).fetchone()
        mve = float(px[1]) * shares if px and shares else None
        z = None
        need = ("CA", "CL", "TA", "TL", "RE", "EBIT", "S")
        if all(v[k] is not None for k in need) and mve is not None and v["TA"] and v["TL"]:
            ta = v["TA"]
            x = ((v["CA"] - v["CL"]) / ta, v["RE"] / ta, v["EBIT"] / ta, mve / v["TL"], v["S"] / ta)
            z = 1.2 * x[0] + 1.4 * x[1] + 3.3 * x[2] + 0.6 * x[3] + 1.0 * x[4]
            xs = " ".join(f"X{i + 1}={xi:.3f}" for i, xi in enumerate(x))
        else:
            xs = "inputs missing: " + ", ".join(
                [k for k in need if v[k] is None] + ([] if mve is not None else ["MVE"])
            )
        pxs = f"close {px[1]} on {px[0]}" if px else "no stored close"
        shs = f"{shares:,.0f} shares ({len(sh)} value(s))" if shares else "no dei shares"
        out.append(f"  {t} SIC {sic} BS {end} {acc}: {pxs}; {shs}{tl_note}")
        out.append(
            "    "
            + " ".join(f"{k} {usd(v[k])}" for k in need)
            + f" MVE {usd(mve)} → {xs}"
            + (f"; Z = {z:.2f}" if z is not None else "")
        )
    out.append("  not SIC 2000–3999: " + ", ".join(skipped))
    return out


def l8_events(ctx: Ctx) -> list[str]:
    since = "2023-10-01"
    rows = ctx.engine.execute(
        "SELECT item, COUNT(*), COUNT(DISTINCT cik) FROM event WHERE item IN ('1.01','1.02',"
        "'2.03') AND filed >= ? GROUP BY item",
        (since,),
    ).fetchall()
    out = [
        f"  since {since}: " + "; ".join(f"Item {a}: {b} events, {c} companies" for a, b, c in rows)
    ]
    co = ctx.engine.execute(
        "SELECT e.accession, e.cik, e.filed, en.name FROM event e LEFT JOIN entity en ON "
        "en.cik = e.cik WHERE e.item = '1.02' AND e.filed >= ? AND e.accession IN (SELECT "
        "accession FROM event WHERE item = '2.03') ORDER BY e.filed",
        (since,),
    ).fetchall()
    out.append(f"  1.02 accessions that also carry 2.03: {len(co)}")
    out += [f"    {r[2]} {r[3] or r[1]} {r[0]}" for r in co[:12]]
    return out


def l9_prices(ctx: Ctx) -> list[str]:
    mu_dates = ("2021-09-02", "2021-12-02", "2022-03-03", "2022-06-02", "2022-09-01",
                "2022-12-01", "2023-03-02", "2023-06-01", "2023-08-31", "2022-01-14",
                "2022-09-26", "2022-10-07", "2023-10-06")  # fmt: skip
    q = ",".join("?" * len(mu_dates))
    rows = ctx.engine.execute(
        f"SELECT symbol, date, close FROM price_bar WHERE (symbol = 'MU' AND date IN ({q})) OR "
        f"(symbol = 'NVDA' AND date = '2023-01-27') ORDER BY symbol, date",
        mu_dates,
    ).fetchall()
    out = ["  raw closes: " + " · ".join(f"{r[0]} {r[1]} {r[2]}" for r in rows)]
    missing = sorted(set(mu_dates) - {r[1] for r in rows if r[0] == "MU"})
    if missing:
        out.append(f"  MU dates with no bar: {', '.join(missing)}")
    mm = ctx.engine.execute(
        "SELECT max(close), min(close) FROM price_bar WHERE symbol = 'MU' AND date BETWEEN "
        "'2021-09-01' AND '2022-12-31'"
    ).fetchone()
    out.append(f"  MU 2021-09-01..2022-12-31 max {mm[0]} min {mm[1]} (pack: 97.36 / 48.88)")
    mu = ticker_cik(ctx, "MU")
    if mu:
        inv = ctx.engine.execute(
            "SELECT period_end, value, form, filed FROM fact WHERE cik = ? AND tag = 'InventoryNet'"
            " AND period_end BETWEEN '2022-08-25' AND '2023-03-05' ORDER BY period_end, filed",
            (mu,),
        ).fetchall()
        out.append(
            "  MU InventoryNet: " + " · ".join(f"{r[0]} {usd(r[1])} ({r[2]} {r[3]})" for r in inv)
        )
    return out


def l10_storage(ctx: Ctx) -> list[str]:
    import statistics as st

    out = []
    for conn in (ctx.engine, ctx.corpus):
        p = Path(conn.execute("PRAGMA database_list").fetchone()[2])
        name = p.name
        wal = p.with_name(name + "-wal")
        size = p.stat().st_size / 1e6 if p.exists() else 0
        ws = wal.stat().st_size / 1e6 if wal.exists() else 0
        out.append(f"  {name}: {size:,.1f} MB (+ WAL {ws:,.1f} MB)")
    total = ctx.engine.execute("SELECT count(*) FROM fact").fetchone()[0]
    out.append(f"  fact rows {total:,}; by company:")
    rows = ctx.engine.execute(
        "SELECT f.cik, en.name, count(*) FROM fact f LEFT JOIN entity en ON en.cik = f.cik "
        "GROUP BY f.cik ORDER BY 3 DESC"
    ).fetchall()
    out.append("    " + " · ".join(f"{(r[1] or r[0])[:18]} {r[2]:,}" for r in rows))
    periodic = {
        a.replace("-", "")
        for (a,) in ctx.engine.execute(
            "SELECT accession FROM filing WHERE form IN ('10-K','10-Q','10-K/A','10-Q/A','20-F')"
        )
    }
    sizes: dict[str, list[int]] = defaultdict(list)
    for url, n in ctx.corpus.execute(
        "SELECT url, length(body) FROM http_cache WHERE outcome = 'ok'"
    ):
        k = (
            "companyfacts" if "companyfacts" in url
            else "efts" if "efts" in url
            else "frames" if "/frames/" in url
            else "10-K/10-Q files" if any(p in periodic for p in url.split("/"))
            else "other"
        )  # fmt: skip
        sizes[k].append(n)
    for k, v in sizes.items():
        out.append(
            f"  http_cache {k}: {len(v)} files; median {st.median(v) / 1e6:.2f} MB; max "
            f"{max(v) / 1e6:.2f} MB; total {sum(v) / 1e6:,.1f} MB"
        )
    rows = ctx.engine.execute(
        "SELECT f.filed, en.name, f.accession FROM filing f LEFT JOIN entity en ON en.cik = f.cik"
        " WHERE f.form = '10-K' AND f.filed BETWEEN '2023-01-01' AND '2023-12-31' ORDER BY f.filed"
    ).fetchall()
    out.append(f"  10-Ks filed in 2023 (dei error-correction flag not yet required): {len(rows)}")
    out += [f"    {r[0]} {r[1]} {r[2]}" for r in rows]
    return out


# --- SEC probes ------------------------------------------------------------------------


def s1_browse_sic(ctx: Ctx) -> list[str]:
    url = "https://www.sec.gov/cgi-bin/browse-edgar"
    ciks: dict[str, str] = {}
    pages = 0
    for start in range(0, 2000, 100):
        params = {"action": "getcompany", "SIC": "3674", "type": "10-K", "owner": "include",
                  "count": "100", "start": str(start)}  # fmt: skip
        res = ctx.get(url, params)
        pages += 1
        if not isinstance(res, Ok):
            return [f"  page {pages}: {describe(res)}"]
        html = res.data.decode("utf-8", errors="replace")
        rows = re.findall(r"CIK=(\d{10})[^>]*>\s*\d{10}\s*</a>\s*</td>\s*<td[^>]*>([^<]+)", html)
        for c, name in rows:
            ciks.setdefault(c, " ".join(name.split()))
        if not rows and start == 0:
            from engine.sec.client import body_snippet

            return [f"  page 1: no company rows parsed; page text: {body_snippet(res.data, 400)}"]
        if len(rows) < 100:
            break
    out = [f"  {pages} page(s), {len(ciks)} companies listed under SIC 3674"]
    cover = ctx.engine.execute(
        "SELECT min(year * 10 + quarter), max(year * 10 + quarter) FROM form_index"
    ).fetchone()
    since = date(date.today().year - 1, date.today().month, 1).isoformat()
    active = {
        r[0]
        for r in ctx.engine.execute(
            "SELECT DISTINCT cik FROM form_filing WHERE family = '10-K' AND filed >= ?", (since,)
        )
    }
    act = sorted(c for c in ciks if c in active)
    out.append(
        f"  stored form indexes cover {cover[0]}..{cover[1]} (yyyyq); filed a 10-K since "
        f"{since}: {len(act)}"
    )
    out.append("    " + "; ".join(ciks[c][:28] for c in act[:40]))
    watch = set(watchlist(ctx).values())
    out.append(f"  watchlist companies in the list: {len(watch & set(ciks))}")
    return out


def s2_invitae(ctx: Ctx) -> list[str]:
    out = []
    for tag in ("EntityCommonStockSharesOutstanding", "EntityPublicFloat"):
        res = concept(ctx, CIK["NVTA"], "dei", tag)
        if not isinstance(res, Ok):
            out.append(f"  dei:{tag}: {describe(res)}")
            continue
        rows = [r for u in res.data.get("units", {}).values() for r in u]
        rows = [r for r in rows if r["end"] >= "2021-06-30"]
        out.append(
            f"  dei:{tag}: "
            + " · ".join(f"{r['end']} {r['val']:,} ({r['form']} {r['filed']})" for r in rows)
        )
    series: dict[tuple, dict[str, Any]] = defaultdict(dict)
    for tag in ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "CostOfRevenue"):
        res = concept(ctx, CIK["NVTA"], "us-gaap", tag)
        if not isinstance(res, Ok):
            out.append(f"  us-gaap:{tag}: {describe(res)}")
            continue
        rows = res.data.get("units", {}).get("USD", [])
        for (s, e), r in first_filed(rows).items():
            n = days(s, e)
            if s and "2017-10-01" <= e <= "2023-12-31" and n and (80 <= n <= 100 or n >= 350):
                series[(s, e)][tag] = (r["val"], r["form"], r["filed"])
    out.append("  period: revenue (ExclAssessedTax | Revenues) · CostOfRevenue, $M, first filed")
    for s, e in sorted(series, key=lambda k: (k[1], k[0])):
        d = series[(s, e)]
        kind = "FY" if (days(s, e) or 0) >= 350 else "Q "

        def cell(tag: str, d=d) -> str:
            return f"{d[tag][0] / 1e6:,.1f}" if tag in d else "—"

        src = next(iter(d.values()))
        out.append(
            f"    {kind} {s}..{e}: rev "
            f"{cell('RevenueFromContractWithCustomerExcludingAssessedTax')} | "
            f"{cell('Revenues')} · cost {cell('CostOfRevenue')} ({src[1]} {src[2]})"
        )
    return out


def s3_covers(ctx: Ctx) -> list[str]:
    out = []
    cik = ticker_cik(ctx, "SPCX") or cik10(CIK["SPCX"])
    row = ctx.engine.execute(
        "SELECT accession, report_date FROM filing WHERE cik = ? AND form = '10-Q' ORDER BY filed "
        "DESC LIMIT 1",
        (cik,),
    ).fetchone()
    targets = []
    if row:
        targets.append(("SPCX latest 10-Q", cik, row[0], row[1]))
    else:
        out.append("  SPCX: no 10-Q in the stored index")
    acc, _, where = find_filing(ctx, CIK["GOOG_INC"], "10-Q", "2009-06-30")
    if acc:
        targets.append(("Google Inc. Q2 2009 10-Q", CIK["GOOG_INC"], acc, "2009-06-30"))
    else:
        out.append(f"  Google Inc. Q2 2009 10-Q: {where}")
    for label, c, a, period in targets:
        reports, where = filing_summary(ctx, c, a)
        if reports is None:
            out.append(f"  {label} {a}: FilingSummary {where}")
            continue
        rx = re.compile(r"cover|document and entity", re.I)
        cover = next((r for r in reports if rx.search(r["ShortName"])), None)
        cover = cover or (reports[0] if reports else None)
        if cover is None:
            out.append(f"  {label} {a}: no reports in FilingSummary")
            continue
        text, where = r_page_text(ctx, c, a, cover)
        out.append(f"  {label} {a} (period {period}) · {cover['ShortName']} · {where}")
        if text is None:
            continue
        out += lines_with(text, r"shares outstanding|class [abc]|common stock|public float", 14)
    return out


def _instance_for(ctx: Ctx, cik, acc: str):
    html, where = index_page(ctx, cik, acc)
    if html is None:
        return None, where
    href = instance_href(html)
    if not href:
        return None, f"no XBRL instance listed in {where}"
    res = ctx.get(href)
    if not isinstance(res, Ok):
        return None, f"{href}: {describe(res)}"
    return instance_facts(res.data), f"{href} ({len(res.data) / 1e6:.1f} MB)"


def s4_nvda_capex(ctx: Ctx) -> list[str]:
    cik = ticker_cik(ctx, "NVDA") or cik10(1045810)
    out = []
    rx = re.compile(r"Purchase|PaymentsToAcquire|PropertyAndEquipment|CapitalExpend", re.I)
    for period in ("2021-01-31", "2013-01-27"):
        acc, _, where = find_filing(ctx, cik, "10-K", period)
        if not acc:
            out.append(f"  FY ending {period}: {where}")
            continue
        facts, where = _instance_for(ctx, cik, acc)
        out.append(f"  FY ending {period} 10-K {acc}: {where}")
        if facts is None:
            continue
        keep = [f for f in facts if f[3] == period and f[2] and 330 <= (days(f[2], f[3]) or 0)
                <= 380 and rx.search(f[1])]  # fmt: skip
        out += [f"    {p}:{t} {s}..{e} = {usd(v)}" for p, t, s, e, v in keep[:15]]
        if not keep:
            out.append("    no matching investing tags for that fiscal year")
    return out


def s5_ge(ctx: Ctx) -> list[str]:
    out = []
    acc17 = "0000040545-18-000014"
    docs, where = index_docs(ctx, CIK["GE"], acc17)
    if docs is None:
        out.append(f"  FY2017 10-K {acc17}: {where}")
    else:
        parts = [d for d in docs if (d.doc_type or "").upper() in ("10-K", "EX-13")]
        out.append(f"  FY2017 10-K {acc17}: documents " + ", ".join(
            f"{d.doc_type} {d.filename}" for d in parts))  # fmt: skip
        for d in parts:
            text, note = doc_text(ctx, d.url)
            out.append(f"   {d.doc_type} {d.filename}: {note}")
            if text is None:
                continue
            out += snips(text, r"contract assets \(note", cap=3, width=200)
            out += snips(text, r"contract assets[^\n]{0,40}28,861", cap=2, width=200)
            out += snips(text, r"estimated profitability", cap=3, width=300)
            out += snips(text, r"increased earnings by \$2\.1 billion", cap=2, width=300)
            if "28,861" in text:
                break
    acc16 = "0000040545-17-000010"
    facts, where = _instance_for(ctx, CIK["GE"], acc16)
    out.append(f"  FY2016 10-K {acc16} instance: {where}")
    if facts is not None:
        hits = [f for f in facts if f[3] == "2015-12-31" and f[2] is None
                and abs(f[4] - 21156e6) <= 0.5e6]  # fmt: skip
        out.append(f"    instants at 2015-12-31 equal to 21,156M: {len(hits)}")
        for p, t, _, _, _ in hits:
            later = [f for f in facts if f[1] == t and f[3] == "2016-12-31" and f[2] is None]
            nxt = f"; 2016-12-31 = {usd(later[0][4])}" if later else ""
            out.append(f"    {p}:{t}{nxt}")
    return out


SPCX_424B4 = f"{ARCH}/1181412/000162828026042639/spaceexplorationtechnologi.htm"


def s6_spcx_lockup(ctx: Ctx) -> list[str]:
    text, note = doc_text(ctx, SPCX_424B4)
    out = [f"  424B4 2026-06-12: {note}"]
    if text is None:
        return out
    heads = [m.start() for m in re.finditer(r"(?im)^\s*(lock-up agreements|shares eligible for "
                                            r"future sale)\s*$", text)]  # fmt: skip
    out.append(f"  headings 'Lock-Up Agreements' / 'Shares Eligible for Future Sale' at {heads}")
    out += snips(text, r"lock-up", cap=24, width=420)
    return out


def s7_upc(ctx: Ctx) -> list[str]:
    from engine.sec.fulltext import search_page

    phrase = "exchangeable for shares of Class A common stock"
    names: Counter = Counter()
    total = None
    for offset in (0, 100, 200):
        res = search_page(ctx.client, phrase, forms=("10-K",), start="2026-01-01",
                          end="2026-04-30", offset=offset, allow_fallback=False)  # fmt: skip
        if not isinstance(res, Ok):
            return [f"  EFTS offset {offset}: {describe(res)}"]
        total = res.data.total
        names.update(h.entity_name or h.cik or "?" for h in res.data.hits)
        if offset + 100 >= total:
            break
    out = [f"  EFTS “{phrase}”, 10-K 2026-01..04: {total} docs, {len(names)} filers"]
    out.append("    " + "; ".join(n[:30] for n, _ in names.most_common(40)))
    for t in ("RYAN", "BROS", "FLNC"):
        cik = ticker_cik(ctx, t)
        if not cik:
            out.append(f"  {t}: not in the ticker map")
            continue
        res = concept(
            ctx, cik, "us-gaap", "MinorityInterestOwnershipPercentageByNoncontrollingOwners"
        )
        if not isinstance(res, Ok):
            out.append(f"  {t} ({cik}) NCI ownership %: {describe(res)}")
            continue
        rows = [r for u in res.data.get("units", {}).values() for r in u]
        rows = sorted(rows, key=lambda r: (r["end"], r["filed"]))[-4:]
        out.append(
            f"  {t} ({cik}) NCI ownership %: "
            + " · ".join(f"{r['end']} {r['val']} ({r['form']})" for r in rows)
        )
    return out


def s8_blank_check(ctx: Ctx) -> list[str]:
    from engine.sec.fulltext import search_page

    phrase = "blank check company"
    hits = []
    total, offset = None, 0
    while offset < 2000:
        res = search_page(ctx.client, phrase, forms=("10-K",), start="2026-01-01",
                          end="2026-04-30", offset=offset, allow_fallback=False)  # fmt: skip
        if not isinstance(res, Ok):
            return [f"  EFTS offset {offset}: {describe(res)}"]
        total = res.data.total
        hits += res.data.hits
        offset += 100
        if offset >= total or not res.data.hits:
            break
    by_cik: dict[str, tuple[str, tuple]] = {}
    for h in hits:
        if h.cik:
            by_cik.setdefault(h.cik, (h.entity_name or "", h.sics))
    sic6770 = {c for c, (_, s) in by_cik.items() if "6770" in s}
    nosic = sum(1 for _, s in by_cik.values() if not s)
    sics = Counter(s[0] if s else "none" for _, s in by_cik.values())
    out = [
        f"  EFTS “{phrase}”, 10-K 2026-01..04: {total} docs read {len(hits)}, {len(by_cik)} filers;"
        f" SIC 6770 {len(sic6770)}, no SIC {nosic}; top SICs {sics.most_common(6)}"
    ]
    frames = ctx.engine.execute(
        "SELECT taxonomy, tag, frame, count(*) FROM frame_value WHERE frame LIKE 'CY2025%' "
        "GROUP BY taxonomy, tag, frame ORDER BY tag, frame"
    ).fetchall()
    for tax, tag, frame, n in frames:
        rows = ctx.engine.execute(
            "SELECT cik, entity_name, value FROM frame_value WHERE taxonomy = ? AND tag = ? AND "
            "frame = ?",
            (tax, tag, frame),
        ).fetchall()
        inside = [r for r in rows if r[0] in sic6770]
        big = [r for r in inside if tag == "EntityPublicFloat" and float(r[2]) >= 75e6]
        out.append(
            f"  frame {tax}:{tag} {frame}: {n} companies, {len(inside)} SIC-6770"
            + (f", {len(big)} with float ≥ $75M" if tag == "EntityPublicFloat" else "")
            + (" e.g. " + "; ".join((r[1] or r[0])[:26] for r in inside[:5]) if inside else "")
        )
    if not frames:
        out.append("  no stored CY2025 frames to intersect")
    return out


_FEE_TITLE = re.compile(
    r"(?:\d+(?:\.\d+)?%\s+)?(?:Senior\s+)?(?:Floating Rate\s+)?Notes due \d{4}|Class [ABC] "
    r"Common Stock|Common Stock|Depositary Shares|Preferred Stock|Debt Securities|Warrants",
    re.IGNORECASE,
)


def s9_424b(ctx: Ctx) -> list[str]:
    out = []
    summary: Counter = Counter()
    for t in ("GOOG", "AMZN"):
        cik = ticker_cik(ctx, t)
        if not cik:
            out.append(f"  {t}: not in the ticker map")
            continue
        rows = ctx.engine.execute(
            "SELECT accession, form, filed FROM filing WHERE cik = ? AND form LIKE '424B%' AND "
            "filed >= '2023-10-12' ORDER BY filed",
            (cik,),
        ).fetchall()
        out.append(f"  {t}: {len(rows)} 424B filing(s) since 2023-10-12 in the stored index")
        for acc, form, filed in rows:
            docs, where = index_docs(ctx, cik, acc)
            if docs is None:
                out.append(f"    {form} {filed} {acc}: {where}")
                summary["index failed"] += 1
                continue
            fee = next((d for d in docs if (d.doc_type or "").upper().startswith(("EX-FILING",
                        "EX-107")) or "fee" in d.filename.lower()), None)  # fmt: skip
            if fee is None:
                out.append(f"    {form} {filed} {acc}: no fee exhibit")
                summary["no fee exhibit"] += 1
                continue
            text, note = doc_text(ctx, fee.url)
            if text is None:
                out.append(f"    {form} {filed} {acc}: fee exhibit {note}")
                summary["fee exhibit failed"] += 1
                continue
            kinds = sorted(k for k in ("Debt", "Equity", "Other") if re.search(rf"\b{k}\b", text))
            titles = list(dict.fromkeys(m.group(0) for m in _FEE_TITLE.finditer(text)))[:3]
            summary["+".join(kinds) or "no type"] += 1
            out.append(f"    {form} {filed} {acc}: {'/'.join(kinds) or '?'} · {'; '.join(titles)}")
    out.append(f"  summary: {dict(summary)}")
    return out


SURVIVAL_DOCS = (
    ("Fisker FY2023 10-K", f"{ARCH}/1720990/000172099024000045/fsr-20231231.htm",
     r"raises substantial doubt|there is substantial doubt|forbearance agreement"),
    ("Invitae Q2 2023 10-Q", f"{ARCH}/1501134/000150113423000068/nvta-20230630.htm",
     r"substantial doubt"),
    ("Invitae Q3 2023 10-Q", f"{ARCH}/1501134/000150113423000104/nvta-20230930.htm",
     r"substantial doubt"),
    ("Proterra FY2022 10-K", f"{ARCH}/1820630/000162828023008519/ptra-20221231.htm",
     r"covenant default|waiver"),
    ("Microvast FY2025 10-K", f"{ARCH}/1760689/000162828026018264/mvst-20251231.htm",
     r"alleviate substantial doubt|critical audit matter"),
    ("Riot FY2025 10-K", f"{ARCH}/1167419/000110465926022322/riot-20251231x10k.htm",
     r"could raise substantial doubt"),
    ("UTI Q3 FY2025 10-Q", f"{ARCH}/1261654/000126165425000019/uti-20250630.htm",
     r"obtained a waiver|in compliance"),
    ("Albemarle EX-10.1 (Q3 2024 10-Q)",
     f"{ARCH}/915913/000091591324000158/exhibit1010930202410-q.htm",
     r"Covenant Relief Period[^.]{0,300}(repurchase|dividend|Restricted Payment)"),
)  # fmt: skip


def s10_survival_text(ctx: Ctx) -> list[str]:
    out = []
    for label, url, pattern in SURVIVAL_DOCS:
        text, note = doc_text(ctx, url)
        out.append(f"  {label}: {note}")
        if text is not None:
            out += snips(text, pattern, cap=4, width=320)
    ba = ticker_cik(ctx, "BA")
    acc, doc, where = find_filing(ctx, ba, "10-K", "2023-12-31") if ba else (None, None, "no BA")
    if acc and doc:
        text, note = doc_text(ctx, f"{filing_folder(ba, acc)}/{doc}")
        out.append(f"  Boeing FY2023 10-K {acc}: {note}")
        if text is not None:
            out += snips(text, r"in compliance with (the )?covenants|were in compliance", 3, 320)
    else:
        out.append(f"  Boeing FY2023 10-K: {where}")
    return out


def s11_boeing_revolvers(ctx: Ctx) -> list[str]:
    ba = ticker_cik(ctx, "BA")
    if not ba:
        return ["  BA not in the ticker map"]
    out = []
    for form, period in (("10-K", "2019-12-31"), ("10-Q", "2024-06-30")):
        acc, doc, where = find_filing(ctx, ba, form, period)
        if not acc or not doc:
            out.append(f"  {form} {period}: {where}")
            continue
        text, note = doc_text(ctx, f"{filing_folder(ba, acc)}/{doc}")
        out.append(f"  {form} {period} {acc}: {note}")
        if text is not None:
            out += snips(text, r"(revolving credit|credit (agreement|facilit))[^.]{0,250}"
                               r"(expir|matur|terminat|due)", cap=5, width=320)  # fmt: skip
    return out


def s12_infq_doubt(ctx: Ctx) -> list[str]:
    cik = ticker_cik(ctx, "INFQ") or cik10(2007825)
    acc10k = "0001193125-26-134544"
    out = [f"  FY2025 10-K {acc10k}: {filed_of(ctx, acc10k)}"]
    closes = ctx.engine.execute(
        "SELECT filed, report_date, accession, items FROM filing WHERE cik = ? AND form LIKE "
        "'8-K%' AND (',' || items || ',') LIKE '%,2.01,%' ORDER BY filed",
        (cik,),
    ).fetchall()
    out.append(
        "  8-K Item 2.01 (de-SPAC close): "
        + (" · ".join(f"filed {r[0]} event {r[1]} {r[2]} [{r[3]}]" for r in closes) or "none")
    )
    seen = False
    for d in stored_docs(ctx, cik):
        text = text_of(ctx, d["doc_id"])
        if d["accession"] == acc10k:
            seen = True
        if re.search(r"substantial doubt", text, re.I):
            out.append(f"  stored {d['doc_type']} {d['accession']} {d['filename']}:")
            out += snips(text, r"substantial doubt", cap=4, width=320)
    if not seen:
        text, note = doc_text(ctx, f"{ARCH}/2007825/000119312526134544/d94946d10k.htm")
        out.append(f"  10-K not stored; {note}")
        if text is not None:
            out += snips(text, r"substantial doubt", cap=6, width=320)
    return out


def s13_nvta_per_unit(ctx: Ctx) -> list[str]:
    text, note = doc_text(ctx, f"{ARCH}/1501134/000150113423000024/nvta-20221231.htm")
    out = [f"  Invitae FY2022 10-K 0001501134-23-000024: {note}"]
    if text is not None:
        out += snips(text, r"(revenue|cost) per (test|sample|unit)|per (billable )?(test|sample)"
                           r"[^.]{0,40}\$", cap=6, width=300)  # fmt: skip
    return out


def s14_rivian_disagg(ctx: Ctx) -> list[str]:
    acc = "0001874178-26-000008"
    reports, where = filing_summary(ctx, CIK["RIVN"], acc)
    if reports is None:
        return [f"  Rivian FY2025 10-K {acc}: FilingSummary {where}"]
    cands = [r for r in reports if re.search(r"revenue", r["LongName"], re.I)
             and re.search(r"detail", r["LongName"], re.I)]  # fmt: skip
    out = [f"  Rivian FY2025 10-K {acc}: {len(cands)} revenue detail report(s): "
           + "; ".join(r["ShortName"][:60] for r in cands[:6])]  # fmt: skip
    pick = next((r for r in cands if re.search(r"disaggregat", r["LongName"], re.I)),
                cands[0] if cands else None)  # fmt: skip
    if pick is None:
        return out
    text, where = r_page_text(ctx, CIK["RIVN"], acc, pick)
    out.append(f"  {pick['ShortName']} · {where}")
    if text is not None:
        out += lines_with(text, r"credit|vehicle|EV|software|services|total|revenue", cap=16)
    return out


def s15_102_cofiled(ctx: Ctx) -> list[str]:
    out = []
    tsla_acc = "0001628280-26-063820"
    row = ctx.engine.execute("SELECT filed, items FROM filing WHERE accession = ?", (tsla_acc,))
    row = row.fetchone()
    out.append(f"  TSLA 8-K {tsla_acc}: " + (f"filed {row[0]} items {row[1]}" if row else
                                             "not in the stored index"))  # fmt: skip
    text, note = doc_text(ctx, f"{ARCH}/1318605/000162828026063820/tsla-20260929.htm")
    out.append(f"    {note}")
    if text is not None:
        out += snips(text, r"Item 1\.0[12]|Item 2\.03|terminat", cap=6, width=300)
    name, filings = submissions(ctx, CIK["RIVN"])
    if isinstance(filings, str):
        return [*out, f"  Rivian submissions: {filings}"]
    hits = [f for f in filings if f.form.startswith("8-K") and f.filed == "2025-06-12"]
    out.append(f"  {name} 8-K filed 2025-06-12: {len(hits)}")
    for f in hits:
        out.append(f"    {f.form} {f.accession} items {','.join(f.items)} doc {f.primary_doc}")
        if f.primary_doc:
            text, note = doc_text(ctx, f"{filing_folder(cik10(CIK['RIVN']), f.accession)}/"
                                       f"{f.primary_doc}")  # fmt: skip
            out.append(f"    {note}")
            if text is not None:
                out += snips(text, r"Item 1\.02|terminat|redeem|satisf\w* and discharg", 5, 300)
    return out


def s16_nvta_releases(ctx: Ctx) -> list[str]:
    name, filings = submissions(ctx, CIK["NVTA"], since="2020-01-01")
    if isinstance(filings, str):
        return [f"  Invitae submissions: {filings}"]
    rel = sorted(
        (f for f in filings if f.form == "8-K" and "2.02" in f.items
         and "2020-01-01" <= f.filed <= "2022-11-30"),
        key=lambda f: f.filed,
    )  # fmt: skip
    out = [f"  {name}: {len(rel)} earnings 8-K(s) 2020-01..2022-11"]
    for f in rel:
        docs, where = index_docs(ctx, CIK["NVTA"], f.accession)
        if docs is None:
            out.append(f"    {f.filed} {f.accession}: {where}")
            continue
        ex = next((d for d in docs if (d.doc_type or "").upper() == "EX-99.1"), None)
        if ex is None:
            out.append(f"    {f.filed} {f.accession}: no EX-99.1")
            continue
        text, note = doc_text(ctx, ex.url)
        if text is None:
            out.append(f"    {f.filed} {f.accession}: {note}")
            continue
        found = lines_with(text, r"non-gaap gross (profit|margin).{0,200}\d", cap=3, width=240)
        out.append(f"    {f.filed} {f.accession}: {len(found)} line(s)")
        out += found
    return out


def s17_distress_revenue(ctx: Ctx) -> list[str]:
    out = []
    tags = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet")
    for t in ("BBBY", "RAD"):
        fy: dict[str, dict[str, Any]] = defaultdict(dict)
        for tag in tags:
            res = concept(ctx, CIK[t], "us-gaap", tag)
            if not isinstance(res, Ok):
                out.append(f"  {t} us-gaap:{tag}: {describe(res)}")
                continue
            rows = [r for r in res.data.get("units", {}).get("USD", []) if r.get("form") in ANNUAL]
            for (s, e), r in first_filed(rows).items():
                if s and (days(s, e) or 0) >= 350:
                    fy[e][tag] = r
        out.append(f"  {t} (CIK {CIK[t]}) annual revenue, $M first filed (tag initials):")
        for e in sorted(fy)[-8:]:
            cells = " · ".join(
                f"{''.join(c for c in tag if c.isupper())} {r['val'] / 1e6:,.0f} ({r['filed']})"
                for tag, r in fy[e].items()
            )
            out.append(f"    FY ending {e}: {cells}")
        name, filings = submissions(ctx, CIK[t])
        if isinstance(filings, str):
            out.append(f"  {t} submissions: {filings}")
            continue
        k = [f for f in filings if f.form in ("10-K", "10-K/A")]
        last = max(k, key=lambda f: f.filed) if k else None
        b = [f for f in filings if f.form.startswith("8-K") and "1.03" in f.items]
        out.append(
            f"  {name}: last 10-K "
            + (f"{last.filed} (period {last.report_date}) {last.accession}" if last else "none")
            + "; 8-K Item 1.03: "
            + (", ".join(f"{f.filed} {f.accession}" for f in b) or "none in recent filings")
        )
    ba = ticker_cik(ctx, "BA")
    if ba:
        for tag in tags:
            s = fy_series(ctx, ba, tag, flow=True, since="2018-01-01")
            s = {e: v for e, v in s.items() if e <= "2020-12-31"}
            if s:
                out.append(
                    f"  BA {tag} (stored): " + " · ".join(f"{e} {usd(v)}" for e, v in s.items())
                )
    return out


# --- Tiingo probes ---------------------------------------------------------------------


def t1_supported_tickers(ctx: Ctx) -> list[str]:
    req = urllib.request.Request(TIINGO_ZIP, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = zf.namelist()[0]
    rows = list(csv.reader(io.StringIO(zf.read(name).decode("utf-8", errors="replace"))))
    head, body = rows[0], rows[1:]
    out = [f"  {name}: {len(raw) / 1e6:.1f} MB zipped, {len(body):,} rows; columns {head}"]
    want = set(DELISTED)
    found: dict[str, list[list[str]]] = defaultdict(list)
    for r in body:
        if r and r[0].upper() in want:
            found[r[0].upper()].append(r)
    for s in DELISTED:
        rs = found.get(s, [])
        out.append(f"    {s}: " + (" | ".join(",".join(r[1:]) for r in rs[:3]) or "not listed"))
    return out


def _tiingo_meta(ctx: Ctx, symbol: str):
    """GET /tiingo/daily/<symbol> (name, exchange, start/end dates) with the engine client's
    key header, spacing, budget check and fetch_log entry; nothing else is stored."""
    from engine.prices.tiingo import BASE

    t = ctx.tiingo
    url = f"{BASE}/{symbol.upper()}"
    problem = t.budget_problem(symbol)
    if problem:
        return Failed(problem, url=url, throttled=True)
    headers = {"Authorization": f"Token {t._token}", "Content-Type": "application/json"}
    t._pace()
    ctx.tiingo_sent += 1
    try:
        status, body = t._transport(url, {}, headers)
    except Exception as exc:  # network error = failure, never "not covered"
        t._log(url, "failed", None, f"{type(exc).__name__}: {exc}")
        return Failed(f"{type(exc).__name__}: {exc}", url=url)
    detail = body[:200].decode("utf-8", "replace")
    if status == 200:
        try:
            data = json.loads(body)
        except ValueError as exc:
            t._log(url, "failed", status, f"unreadable JSON: {exc}")
            return Failed(f"unreadable JSON: {exc}", url=url, status=status)
        t._log(url, "ok", status, "meta")
        return Ok(data, source_ref=f"tiingo-meta:{symbol.upper()}")
    if status == 404:
        t._log(url, "not_found", status, detail)
        return NotFound(url, status)
    t._log(url, "throttled" if status == 429 else "failed", status, detail)
    return Failed(f"HTTP {status}: {detail}", url=url, status=status, throttled=status == 429)


def t2_tiingo_meta(ctx: Ctx) -> list[str]:
    out = ["  meta: name · exchange · startDate..endDate (a recent endDate on a delisted"
           " name means the ticker was recycled)"]  # fmt: skip
    for s in DELISTED:
        res = _tiingo_meta(ctx, s)
        if isinstance(res, Ok):
            d = res.data
            out.append(f"    {s}: {d.get('name')} · {d.get('exchangeCode')} · "
                       f"{d.get('startDate')}..{d.get('endDate')}")  # fmt: skip
        else:
            out.append(f"    {s}: {describe(res)}")
            if isinstance(res, Failed) and res.throttled:
                return [*out, "  stopped: Tiingo budget or throttle; run --only T2 later"]
    res = ctx.tiingo.daily("NVTA", date(2023, 6, 26), date(2023, 7, 3))
    if not (isinstance(res, Failed) and res.throttled and res.status is None):
        ctx.tiingo_sent += 1
    if isinstance(res, Ok):
        out.append("  NVTA closes (not stored): " + " · ".join(
            f"{b['date'][:10]} {b['close']}" for b in res.data))  # fmt: skip
    else:
        out.append(f"  NVTA closes 2023-06-26..07-03: {describe(res)}")
    return out


# --- registry and runner ---------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    id: str
    kind: str  # local | sec | tiingo
    rounds: str
    title: str
    requests: str
    fn: Callable[[Ctx], list[str]]


PROBES: tuple[Probe, ...] = (
    Probe(
        "L1",
        "local",
        "R1 #1",
        "Greenwald inputs: PP&E net/gross, revenue, capex",
        "0",
        l1_greenwald,
    ),
    Probe(
        "L2",
        "local",
        "R2 #6",
        "NVDA/MRVL/TSLA/GFS tag listings for M- and F-score",
        "0",
        l2_r2_tags,
    ),
    Probe("L3", "local", "R2 #8c", "SPCX filings: any 10-K yet", "0", l3_spcx_filings),
    Probe(
        "L4", "local", "R3 #2", "SPCX preferred-to-common conversion count", "0", l4_spcx_conversion
    ),
    Probe(
        "L5", "local", "R3 #5", "INFQ CY2025/CY2024 weighted-share frame pair", "0", l5_infq_frames
    ),
    Probe("L6", "local", "R3 #6", "MSTR convertible notes and ATM programs", "0", l6_mstr_notes),
    Probe(
        "L7", "local", "R4 #4", "Manufacturer Z for SIC 2000–3999 watchlist names", "0", l7_altman_z
    ),
    Probe(
        "L8",
        "local",
        "R5 #13",
        "8-K 1.01/1.02/2.03 volumes; 1.02 co-filed with 2.03",
        "0",
        l8_events,
    ),
    Probe(
        "L9",
        "local",
        "R6 #4, #15",
        "MU/NVDA stored closes; MU inventory 2022-12-01",
        "0",
        l9_prices,
    ),
    Probe(
        "L10", "local", "BP #1, #4, #7, #8", "DB sizes, cache sizes, 2023 10-Ks", "0", l10_storage
    ),
    Probe("S1", "sec", "R1 #3", "Browse-by-SIC 3674 list; active filers", "2–10", s1_browse_sic),
    Probe(
        "S2",
        "sec",
        "R1 #7, R5 #8, R6 #5",
        "Invitae dei shares/float; quarterly revenue, cost",
        "5",
        s2_invitae,
    ),
    Probe(
        "S3",
        "sec",
        "R1 #8, #11",
        "Cover R pages: SPCX latest 10-Q; Google Inc. Q2 2009",
        "4–6",
        s3_covers,
    ),
    Probe(
        "S4", "sec", "R1 #9", "NVIDIA capex tag FY2021 and FY2013 instances", "4–6", s4_nvda_capex
    ),
    Probe(
        "S5",
        "sec",
        "R1 #10, R2 #4, #5, BP #6",
        "GE contract assets label; 2015 tag; sentences",
        "4–5",
        s5_ge,
    ),
    Probe(
        "S6", "sec", "R3 #1", "SPCX 424B4 lock-up schedule (one file > 10 MB)", "1", s6_spcx_lockup
    ),
    Probe("S7", "sec", "R3 #7", "Up-C: EFTS phrase; RYAN/BROS/FLNC NCI %", "4–6", s7_upc),
    Probe(
        "S8",
        "sec",
        "R3 #8",
        "Blank checks (EFTS SIC 6770) vs stored CY2025 frames",
        "5–20",
        s8_blank_check,
    ),
    Probe("S9", "sec", "R3 #9", "GOOG/AMZN 424B fee exhibits: debt or equity", "about 80", s9_424b),
    Probe(
        "S10",
        "sec",
        "R4 #1, #3",
        "Survival text fixtures (8 docs) + Boeing FY2023 10-K",
        "9",
        s10_survival_text,
    ),
    Probe(
        "S11",
        "sec",
        "R4 #11 (P4)",
        "Boeing revolver maturities FY2019 / Q2 2024",
        "0–2",
        s11_boeing_revolvers,
    ),
    Probe(
        "S12",
        "sec",
        "R4 #2",
        "INFQ 'substantial doubt' class; de-SPAC close date",
        "0–1",
        s12_infq_doubt,
    ),
    Probe("S13", "sec", "R5 #11", "Invitae FY2022 per-unit sentences", "1", s13_nvta_per_unit),
    Probe(
        "S14",
        "sec",
        "R5 #11",
        "Rivian FY2025 revenue disaggregation (credits)",
        "2",
        s14_rivian_disagg,
    ),
    Probe(
        "S15",
        "sec",
        "R5 #10",
        "8-K 1.02 co-filed with 2.03: TSLA 2026-09-29, RIVN 2025-06-12",
        "2–3",
        s15_102_cofiled,
    ),
    Probe(
        "S16",
        "sec",
        "R5 #6 (optional)",
        "Invitae EX-99.1 non-GAAP gross profit 2020–22",
        "about 25",
        s16_nvta_releases,
    ),
    Probe(
        "S17",
        "sec",
        "R6 #5",
        "BBBY/Rite Aid annual revenue, last 10-K, 8-K 1.03; BA local",
        "8",
        s17_distress_revenue,
    ),
    Probe(
        "T1",
        "tiingo",
        "R1 #6, R6 #3, BP #3",
        "Tiingo supported_tickers.zip (no key)",
        "1 file",
        t1_supported_tickers,
    ),
    Probe(
        "T2",
        "tiingo",
        "R1 #6, #7, R6 #3, BP #3",
        "Tiingo meta for 18 delisted symbols; NVTA",
        "19 Tiingo",
        t2_tiingo_meta,
    ),
)


def parse_only(text: str | None, probes: tuple[Probe, ...] = PROBES) -> list[str]:
    """'s5, T2' → ['S5', 'T2']; unknown IDs raise ValueError naming the valid ones."""
    if not text:
        return []
    ids = [x.strip().upper() for x in text.split(",") if x.strip()]
    valid = {p.id for p in probes}
    bad = [x for x in ids if x not in valid]
    if bad:
        raise ValueError(f"unknown probe(s) {', '.join(bad)}; valid: {', '.join(sorted(valid))}")
    return list(dict.fromkeys(ids))


def select(
    probes: tuple[Probe, ...], only: list[str], *, no_sec: bool = False, no_tiingo: bool = False
) -> list[Probe]:
    chosen = [p for p in probes if not only or p.id in only]
    return [
        p
        for p in chosen
        if not (no_sec and p.kind == "sec") and not (no_tiingo and p.kind == "tiingo")
    ]


def run_one(ctx: Ctx, p: Probe) -> list[str]:
    t0, s0, ti0 = time.monotonic(), ctx.sec_sent, ctx.tiingo_sent
    lines = ["", f"== {p.id} · {p.title} · {p.rounds} =="]
    if p.kind == "sec" and (wait := ctx.sec_paused()) > 0:
        return [*lines, f"  skipped: SEC throttle breaker open for {wait:.0f}s more"]
    try:
        lines += p.fn(ctx)
    except Exception as exc:
        last = traceback.extract_tb(exc.__traceback__)[-1]
        lines.append(f"  ERROR {type(exc).__name__}: {exc} (at {last.name}, line {last.lineno})")
    lines.append(
        f"  -- {ctx.sec_sent - s0} SEC request(s), {ctx.tiingo_sent - ti0} Tiingo, "
        f"{time.monotonic() - t0:.0f} s"
    )
    return lines


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="M04 design-review probe (read-only)")
    ap.add_argument("--only", help="comma-separated probe IDs, e.g. S5,T2,L7")
    ap.add_argument("--no-sec", action="store_true", help="skip SEC probes")
    ap.add_argument("--no-tiingo", action="store_true", help="skip Tiingo probes")
    ap.add_argument("--list", action="store_true", help="print the probe table and exit")
    return ap


def table(probes: tuple[Probe, ...] = PROBES) -> list[str]:
    return [f"{p.id:<4} {p.kind:<6} {p.requests:<10} {p.rounds:<26} {p.title}" for p in probes]


def _run(args: argparse.Namespace, chosen: list[Probe]) -> int:
    import os

    from engine.store.db import open_db

    os.chdir(ROOT)
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    ctx = Ctx(engine, corpus)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"probe_m04_{datetime.now():%Y%m%d-%H%M%S}.txt"
    t0 = time.monotonic()
    head = [f"probe_m04 {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · probes "
            f"{', '.join(p.id for p in chosen)}"]  # fmt: skip
    with log.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(head) + "\n")
        print(head[0], flush=True)
        for p in chosen:
            lines = run_one(ctx, p)
            fh.write("\n".join(lines) + "\n")
            fh.flush()
            print("\n".join(lines), flush=True)
        tail = (
            f"\nDone: {ctx.sec_sent} SEC request(s), {ctx.tiingo_sent} Tiingo request(s), "
            f"{time.monotonic() - t0:.0f} s"
        )
        fh.write(tail + "\n")
    print(tail)
    print(f"log written to: {log}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.list:
        print("\n".join(table()))
        return 0
    try:
        only = parse_only(args.only)
    except ValueError as exc:
        print(exc)
        return 2
    chosen = select(PROBES, only, no_sec=args.no_sec, no_tiingo=args.no_tiingo)
    if not chosen:
        print("no probes selected")
        return 2
    from engine.store.lock import run_script

    return run_script(ROOT, "probe_m04", lambda: _run(args, chosen))


if __name__ == "__main__":
    sys.exit(main())
