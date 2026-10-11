"""Probe for M02 part 5b (financing links, D-M02-41…44). Owner runs it once:

    uv run python scripts/probe_financing.py

Local (no requests): which watchlist/tracked companies have 13F, 13D/13G and 8-K Item
3.02 filings in the stored index; XBRL tags for financing receivables, allowances,
equity-method and equity investments in stored facts; counts and sample sentences for the
text finders K1–K4, K6 over stored documents.
SEC (≤ ~40 requests): the latest two 13F-HR filings of each filer (plus its oldest when it
predates January 2023, the dollar-unit change) — index, cover page, information table; up
to six Schedule 13D/13G filings — index header (filer vs subject) and the XML fields.
Writes logs/probe_financing_<time>.txt.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calls.transcripts import symbol_cik  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.sec.documents import fetch_filing_index  # noqa: E402
from engine.sec.results import Ok  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.supply.aliases import Matcher, load  # noqa: E402
from engine.supply.find import _sentences_in  # noqa: E402
from engine.themes import tiers  # noqa: E402

FORMS_13F = ("13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A")
FORMS_13DG = (
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
    "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A",
)  # fmt: skip
TAG_PATTERNS = (
    "%FinancingReceivable%", "%AllowanceForCreditLoss%", "%AllowanceForDoubtful%",
    "%LoansAndLeasesReceivable%", "%NotesReceivable%", "%LoansReceivable%",
    "%EquityMethodInvestment%", "%GuaranteeObligations%", "%Guarantor%",
    "EquitySecuritiesFvNi%", "%EquitySecuritiesWithoutReadilyDeterminableFairValue%",
    "%NonmarketableEquit%", "%MarketableSecuritiesEquity%",
)  # fmt: skip
SEC_TTL = 3650 * 86400

_SEC = r"(?:shares|common stock|preferred stock|warrants?|convertible (?:notes?|preferred)|private placement|securities purchase agreement|equity investment)"  # noqa: E501
KINDS = {
    "K1 equity purchase": re.compile(
        rf"\b(?:invest\w*|purchas\w*|acqui\w*|bought|subscri\w*)\b.{{0,120}}\b{_SEC}\b"
        rf"|\b{_SEC}\b.{{0,80}}\b(?:to|by|with)\b",
        re.IGNORECASE,
    ),
    "K2 equity granted to customer": re.compile(
        r"\bwarrants?\b.{0,160}\b(?:customer|vest\w*|milestones?|purchases?|deploy\w*)\b",
        re.IGNORECASE,
    ),
    "K3 revenue backstop": re.compile(
        r"\b(?:unsold|unused|excess|residual) (?:\w+ ){0,2}capacity\b|\bbackstop\w*\b"
        r"|\bcapacity (?:purchase|commitment)s?\b|\bminimum (?:revenue|purchase|utilization)\b",
        re.IGNORECASE,
    ),
    "K4 customer financing": re.compile(
        r"\b(?:customer|vendor) financing\b|\bfinancing (?:to|for|provided to) (?:our )?customers\b"
        r"|\bfinancing receivables?\b|\bloans? to (?:a |our )?customers?\b"
        r"|\bguarantee\w* (?:of|for) (?:\w+ ){0,4}(?:debt|obligations|leases?|borrowings)\b",
        re.IGNORECASE,
    ),
    "K6 joint venture / equity method": re.compile(
        r"\bjoint ventures?\b|\bequity[- ]method (?:investees?|investments?)\b", re.IGNORECASE
    ),
}
SAMPLES_PER_KIND = 4


def companies(engine) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def local_filings(engine, comps: dict[str, str]) -> tuple[list[str], dict[str, list]]:
    lines = ["", "== Stored filings: 13F, 13D/13G, 8-K Item 3.02 (local) =="]
    found: dict[str, list] = {"13F": [], "13DG": []}
    forms = FORMS_13F + FORMS_13DG
    marks = ",".join("?" * len(forms))
    for t, cik in sorted(comps.items()):
        rows = engine.execute(
            f"SELECT f.accession, f.form, f.filed, f.cik AS first_cik, f.primary_doc FROM filing f "
            f"JOIN filing_cik c ON c.accession = f.accession WHERE c.cik = ? AND f.form IN "
            f"({marks}) ORDER BY f.filed DESC",
            (cik, *forms),
        ).fetchall()
        n302 = engine.execute(
            "SELECT count(*) FROM filing f JOIN filing_cik c ON c.accession = f.accession "
            "WHERE c.cik = ? AND f.form IN ('8-K', '8-K/A') AND (',' || f.items || ',') "
            "LIKE '%,3.02,%'",
            (cik,),
        ).fetchone()[0]
        by_form = Counter(r["form"] for r in rows)
        if not rows and not n302:
            continue
        span = f"{rows[-1]['filed']}…{rows[0]['filed']}" if rows else ""
        lines.append(f"  {t}: {dict(by_form)} {span}; 8-K Item 3.02: {n302}")
        for r in rows:
            kind = "13F" if r["form"] in FORMS_13F else "13DG"
            found[kind].append((t, cik, r))
    if len(lines) == 2:
        lines.append("  none")
    return lines, found


def local_tags(engine, comps: dict[str, str]) -> list[str]:
    lines = ["", "== XBRL tags in stored facts (local; latest value per company) =="]
    by_cik = {c: t for t, c in comps.items()}
    marks = ",".join("?" * len(by_cik))
    where = " OR ".join("tag LIKE ?" for _ in TAG_PATTERNS)
    rows = engine.execute(
        f"SELECT tag, cik, unit, period_end, value, form FROM fact WHERE cik IN ({marks}) AND "
        f"({where}) ORDER BY tag, cik, period_end DESC, filed DESC",
        (*by_cik, *TAG_PATTERNS),
    ).fetchall()
    latest: dict[str, dict[str, tuple]] = defaultdict(dict)
    count: Counter = Counter()
    for r in rows:
        count[r["tag"]] += 1
        latest[r["tag"]].setdefault(r["cik"], (r["period_end"], r["value"], r["unit"], r["form"]))
    for tag in sorted(latest):
        parts = [
            f"{by_cik[c]} {e} {_money(v)}{'' if u == 'USD' else ' ' + u}"
            for c, (e, v, u, _) in sorted(latest[tag].items(), key=lambda x: by_cik[x[0]])
        ]
        lines.append(f"  {tag} ({count[tag]} pts): " + "; ".join(parts))
    if not latest:
        lines.append("  none of the patterns found")
    return lines


def _money(v) -> str:
    try:
        x = float(v)
    except TypeError, ValueError:
        return str(v)
    return f"${x / 1e9:,.2f}B" if abs(x) >= 1e8 else f"${x / 1e6:,.1f}M"


def local_text(engine, corpus, comps: dict[str, str]) -> list[str]:
    lines = ["", "== Text finders K1–K4, K6 over stored documents (local) =="]
    matcher = Matcher(load(engine))
    by_cik = {c: t for t, c in comps.items()}
    counts: dict[str, Counter] = defaultdict(Counter)
    named: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, list[str]] = defaultdict(list)
    docs = 0
    marks = ",".join("?" * len(by_cik))
    for d in corpus.execute(
        f"SELECT doc_id, cik, accession, doc_type FROM document WHERE cik IN ({marks})",
        tuple(by_cik),
    ).fetchall():
        text = corpus.execute("SELECT text FROM document WHERE doc_id = ?", (d[0],)).fetchone()[0]
        docs += 1
        t = by_cik[d["cik"]]
        mine = {c.key for c in matcher.companies if c.cik == d["cik"]}
        for s, e in _sentences_in(text):
            sent = text[s:e]
            for kind, rx in KINDS.items():
                if not rx.search(sent):
                    continue
                counts[kind][t] += 1
                ms = matcher.find(text, s, e)
                others = sorted({m.company.name for m in ms if m.company.key not in mine})
                if others:
                    named[kind][t] += 1
                    if len(samples[kind]) < SAMPLES_PER_KIND:
                        q = " ".join(sent.split())[:320]
                        where = f"{t} {d['doc_type']} {d['accession']}"
                        samples[kind].append(f"{where} [{', '.join(others)}]: “{q}”")
    lines.append(f"  {docs} stored document(s) read")
    for kind in KINDS:
        tot = sum(counts[kind].values())
        nn = sum(named[kind].values())
        top = ", ".join(f"{t} {n}" for t, n in named[kind].most_common(8))
        lines.append(f"  {kind}: {tot} sentence(s); {nn} name another known company ({top})")
        lines += [f"      {s}" for s in samples[kind]]
    return lines


def _strip(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _leaves(root) -> list[tuple[str, str]]:
    return [(_strip(el.tag), (el.text or "").strip()) for el in root.iter() if len(el) == 0]


def _xml_docs(index) -> list:
    return [d for d in index if d.filename.lower().endswith(".xml") and "xsl" not in d.url.lower()]


def probe_13f(client, found: list) -> list[str]:
    lines = ["", "== 13F-HR (SEC) =="]
    if not found:
        return lines + ["  no stored 13F filings for watchlist/tracked companies"]
    by_filer: dict[str, list] = defaultdict(list)
    for t, cik, r in found:
        if r["form"].startswith("13F-HR"):
            by_filer[t].append((cik, r))
    for t, rows in by_filer.items():
        pick = rows[:2]
        oldest = rows[-1]
        if oldest[1]["filed"] < "2023-01-01" and oldest not in pick:
            pick.append(oldest)
        lines.append(f"  {t}: {len(rows)} 13F-HR filing(s), first {oldest[1]['filed']}")
        for cik, r in pick:
            idx = fetch_filing_index(client, cik, r["accession"])
            if not isinstance(idx, Ok):
                lines.append(f"    {r['accession']}: index {idx}")
                continue
            lines.append(f"    {r['form']} {r['accession']} filed {r['filed']}; documents:")
            lines += [f"      {d.doc_type} · {d.description} · {d.filename}" for d in idx.data]
            for d in _xml_docs(idx.data):
                res = client.get_bytes(d.url, ttl_s=SEC_TTL)
                if not isinstance(res, Ok):
                    lines.append(f"      {d.filename}: {res}")
                    continue
                try:
                    root = ET.fromstring(res.data)
                except ET.ParseError as exc:
                    lines.append(f"      {d.filename}: XML unreadable ({exc})")
                    continue
                if _strip(root.tag) == "informationTable":
                    lines += _info_table(root)
                else:
                    keep = ("periodOfReport", "reportCalendarOrQuarter", "tableEntryTotal",
                            "tableValueTotal", "isAmendment", "reportType", "name")  # fmt: skip
                    lines.append(
                        "      cover: "
                        + "; ".join(f"{k}={v}" for k, v in _leaves(root) if k in keep and v)
                    )
    return lines


def _info_table(root) -> list[str]:
    rows = []
    for it in root:
        f = {_strip(el.tag): (el.text or "").strip() for el in it.iter() if len(el) == 0}
        rows.append(f)
    total = sum(float(r.get("value") or 0) for r in rows)
    out = [f"      information table: {len(rows)} row(s), value total {total:,.0f} (as reported)"]
    keys = sorted({k for r in rows for k in r})
    out.append(f"      row fields: {', '.join(keys)}")
    for r in sorted(rows, key=lambda r: -float(r.get("value") or 0))[:12]:
        out.append(
            f"      {r.get('nameOfIssuer')} · {r.get('titleOfClass')} · {r.get('cusip')} · "
            f"value {r.get('value')} · {r.get('sshPrnamt')} {r.get('sshPrnamtType')}"
            + (f" · {r['putCall']}" if r.get("putCall") else "")
        )
    return out


_HEADER = re.compile(r'companyName">\s*([^<(]+?)\s*\((Subject|Filed by|Reporting|Filer)\)', re.I)
_KEEP_13DG = re.compile(
    r"issuer|cusip|percent|aggregate|amount|classOfSecurities|eventDate|dateOfEvent|"
    r"reportingPersonName|typeOfReportingPerson|soleVoting|sharedVoting",
    re.IGNORECASE,
)


def probe_13dg(client, found: list, limit: int = 6) -> list[str]:
    lines = ["", "== Schedule 13D/13G (SEC) =="]
    if not found:
        return lines + ["  no stored 13D/13G filings for watchlist/tracked companies"]
    lines.append(f"  stored: {len(found)} filing(s) listed under watchlist/tracked companies")
    # newest first, spread across companies
    seen: Counter = Counter()
    pick = []
    for t, cik, r in sorted(found, key=lambda x: x[2]["filed"], reverse=True):
        if seen[t] < 2 and len(pick) < limit:
            pick.append((t, cik, r))
            seen[t] += 1
    for t, cik, r in pick:
        lines.append(f"  listed under {t}: {r['form']} {r['accession']} filed {r['filed']}")
        idx = fetch_filing_index(client, cik, r["accession"])
        if not isinstance(idx, Ok):
            lines.append(f"    index: {idx}")
            continue
        page = client.get_text(idx.source_ref, ttl_s=SEC_TTL)
        if isinstance(page, Ok):
            roles = _HEADER.findall(page.data)
            lines.append("    header: " + "; ".join(f"{n} ({role})" for n, role in roles))
        lines += [f"    {d.doc_type} · {d.filename}" for d in idx.data]
        for d in _xml_docs(idx.data)[:1]:
            res = client.get_bytes(d.url, ttl_s=SEC_TTL)
            if not isinstance(res, Ok):
                lines.append(f"    {d.filename}: {res}")
                continue
            try:
                root = ET.fromstring(res.data)
            except ET.ParseError as exc:
                lines.append(f"    {d.filename}: XML unreadable ({exc})")
                continue
            vals = [(k, v) for k, v in _leaves(root) if v and _KEEP_13DG.search(k)][:18]
            fields = "; ".join(f"{k}={v}" for k, v in vals)
            lines.append(f"    {d.filename} <{_strip(root.tag)}>: {fields}")
    return lines


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 1
    import os

    os.chdir(ROOT)
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    now = datetime.now(UTC)
    comps = companies(engine)
    lines = [f"probe_financing {now:%Y-%m-%d %H:%M} UTC · {len(comps)} companies"]
    flines, found = local_filings(engine, comps)
    lines += flines
    lines += local_tags(engine, comps)
    lines += local_text(engine, corpus, comps)

    from engine.sec.client import SecClient, user_agent_from_env
    from engine.store.http import SqliteCache, SqliteFetchLog

    client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine))
    lines += probe_13f(client, found["13F"])
    lines += probe_13dg(client, found["13DG"])

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"probe_financing_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} lines; log written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
