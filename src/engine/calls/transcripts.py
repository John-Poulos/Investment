"""Call transcripts: plan, fetch, store, remind (M02 part 4; D-M02-6, -20, -21).

Which calls: for each watchlist and tracked company, the fiscal quarters of its
earnings 8-Ks (Item 2.02) from the last ~13 months, newest first. The fiscal label
comes from the 8-K's filing date and the company's fiscal year end (SEC
submissions): the last fiscal quarter that ended before the release. A fiscal year
is named by the calendar year it ends in (Microsoft FY2026 ends June 2026; NVIDIA
FY2027 ends January 2027), the convention Alpha Vantage uses (probe 2026-10-09).

Storage: the raw reply once (corpus doc_raw), rendered as text with one section per
speaker turn — 'call management', 'call analyst', 'call operator' or 'call other' —
so transcripts are searchable and readable with speakers (D-M02-21), and only
management turns are parsed. Accession `AV-<SYMBOL>-<YYYYQn>` (sources.py). The
call's date is taken as its release's filing date (the call is that day or the
next); without a matching release the transcript is stored but not parsed.

Retries: an empty reply is retried once a day; 30 days after the release without
a transcript, an `m02_ir_download` reminder is queued (lean fallback, D-M02-21).
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from engine.calls.alpha_vantage import AlphaVantageClient, Reply, parse_reply
from engine.guidance.sources import CALL_PREFIX
from engine.search.passages import fts_label, write_passages
from engine.sec.client import iso
from engine.sec.results import Failed, Ok
from engine.sec.submissions import earnings_releases
from engine.themes import proposals

RENDERER_VERSION = "av-1"
DOC_TYPE = "CALL-TRANSCRIPT"
FILENAME = "transcript.txt"
LOOKBACK_DAYS = 400  # ~4 quarters of releases (D-M02-20 backfill)
RESULTS_WINDOW_DAYS = 70  # results releases come within ~10 weeks of quarter end
REMIND_AFTER_DAYS = 30

_OPERATOR = re.compile(r"\boperator\b", re.IGNORECASE)
_ANALYST = re.compile(
    r"\banalyst\b|\bresearch\b|\bmanaging director\b|securities|capital markets|\bbank\b|"
    r"\b(?:goldman|morgan stanley|jp ?morgan|barclays|citi\w*|ubs|bernstein|jefferies|evercore|"
    r"wells fargo|bofa|bank of america|deutsche|mizuho|cowen|piper|raymond james|wolfe|melius|"
    r"redburn|rbc|oppenheimer|needham|keybanc|truist|baird|stifel|macquarie|hsbc|nomura|bmo|"
    r"cantor|loop capital|guggenheim|daiwa|susquehanna|morningstar)\b",
    re.IGNORECASE,
)
_OFFICER = re.compile(
    r"\b(?:chief|ceo|cfo|coo|cto|president|officer|vice president|vp|svp|evp|treasurer|"
    r"investor relations|ir|chair\w*|director|head|founder|executive|controller|"
    r"general counsel|secretary)\b",
    re.IGNORECASE,
)


def role_of(speaker: str, title: str) -> str:
    """management | analyst | operator | other. Unknown roles are never parsed."""
    if _OPERATOR.search(speaker) or _OPERATOR.search(title):
        return "operator"
    if _ANALYST.search(title):
        return "analyst"
    if _OFFICER.search(title):
        return "management"
    return "other"


# --- Fiscal quarters ---------------------------------------------------------


def _fye(fye: str | None) -> tuple[int, int] | None:
    """(month, day) of the fiscal year end; an end in the first week of a month
    (52/53-week years such as 'Jan 3') belongs to the month before."""
    if not fye or not re.fullmatch(r"\d{4}", fye):
        return None
    month, day = int(fye[:2]), int(fye[2:])
    if not 1 <= month <= 12:
        return None
    if day <= 7:
        month = 12 if month == 1 else month - 1
        day = 31
    return month, day


def fiscal_quarter(filed: date, fye: str | None) -> tuple[int, int] | None:
    """(fiscal year, quarter) of the last fiscal quarter that ended before `filed`."""
    last = last_quarter(filed, fye)
    return last[:2] if last else None


def last_quarter(filed: date, fye: str | None) -> tuple[int, int, date] | None:
    """(fiscal year, quarter, approximate end date) of the last quarter ended before `filed`."""
    f = _fye(fye)
    if f is None:
        return None
    m, d = f
    best: date | None = None
    for year in (filed.year - 1, filed.year):
        for k in range(4):
            month = (m - 3 * k - 1) % 12 + 1
            day = min(d, calendar.monthrange(year, month)[1])
            end = date(year, month, day)
            if end < filed and (best is None or end > best):
                best = end
    assert best is not None
    fy = best.year if best.month <= m else best.year + 1
    q = ((best.month - m - 1) % 12) // 3 + 1
    return fy, q, best


def av_label(fy: int, q: int) -> str:
    return f"{fy}Q{q}"


def ledger_label(av_quarter: str) -> str:
    return f"FY{av_quarter[:4]} Q{av_quarter[-1]}"


@dataclass(frozen=True)
class Due:
    symbol: str
    cik: str
    quarter: str  # Alpha Vantage label, e.g. 2026Q4
    release_accession: str
    release_filed: str


def company_releases(
    engine: sqlite3.Connection, cik: str, since: str | None = None
) -> dict[str, tuple[str, str]]:
    """Fiscal quarter (AV label) → (accession, filed) of its earnings 8-K.

    Several Item 2.02 8-Ks can fall in one quarter (Tesla files its deliveries report
    under 2.02 two days after quarter end, the results three weeks later): the latest
    original 8-K filed within RESULTS_WINDOW_DAYS of the quarter end is the results
    release; one filed later (an investor day) is used only when nothing else exists.
    """
    row = engine.execute("SELECT fiscal_year_end FROM entity WHERE cik = ?", (cik,)).fetchone()
    fye = row[0] if row else None
    groups: dict[str, list[tuple[str, str, str, date]]] = {}
    for f in earnings_releases(engine, cik, since=since):
        last = last_quarter(date.fromisoformat(f.filed[:10]), fye)
        if last is not None:
            groups.setdefault(av_label(*last[:2]), []).append(
                (f.filed[:10], f.accession, f.form, last[2])
            )
    out: dict[str, tuple[str, str]] = {}
    for quarter, fs in groups.items():
        fs.sort()
        end = fs[0][3]
        near = [x for x in fs if (date.fromisoformat(x[0]) - end).days <= RESULTS_WINDOW_DAYS]
        originals = [x for x in near if x[2] == "8-K"] or near
        filed, acc, _, _ = originals[-1] if originals else fs[0]
        out[quarter] = (acc, filed)
    return out


def plan(engine: sqlite3.Connection, companies: dict[str, str], today: date) -> list[Due]:
    """Transcripts to request now, newest release first. companies: symbol → cik."""
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    due: list[Due] = []
    seen: set[str] = set()  # one symbol per company (INFQ, not its warrants INFQ-WT)
    for symbol, cik in sorted(companies.items(), key=lambda x: "-" in x[0] or "." in x[0]):
        if cik in seen:
            continue
        seen.add(cik)
        for quarter, (acc, filed) in company_releases(engine, cik, since).items():
            st = engine.execute(
                "SELECT outcome, last_at FROM call_fetch WHERE symbol = ? AND quarter = ?",
                (symbol, quarter),
            ).fetchone()
            if st is not None:
                if st["outcome"] == "ok":
                    continue
                age = (today - date.fromisoformat(filed)).days
                if age > REMIND_AFTER_DAYS or st["last_at"][:10] >= today.isoformat():
                    continue  # retried once a day until the download reminder takes over
            due.append(Due(symbol, cik, quarter, acc, filed))
    return sorted(due, key=lambda d: (d.release_filed, d.symbol), reverse=True)


# --- Storage -------------------------------------------------------------------


@dataclass(frozen=True)
class Turn:
    start: int
    end: int
    role: str
    speaker: str
    title: str


def render(symbol: str, quarter: str, reply: Reply) -> tuple[str, list[Turn]]:
    """Transcript text, one block per speaker turn: 'Speaker — Title' then the words."""
    fy, q = quarter[:4], quarter[-1]
    text = f"{symbol} earnings call, fiscal {fy} Q{q} — transcript from Alpha Vantage\n\n"
    turns: list[Turn] = []
    for seg in reply.turns:
        speaker = " ".join(str(seg.get("speaker") or "").split()) or "Unknown speaker"
        title = " ".join(str(seg.get("title") or "").split())
        body = str(seg.get("content") or "").strip()
        start = len(text)
        text += (f"{speaker} — {title}" if title else speaker) + "\n" + body
        turns.append(Turn(start, len(text), role_of(speaker, title), speaker, title))
        text += "\n\n"
    return text, turns


def accession_for(symbol: str, quarter: str) -> str:
    return f"{CALL_PREFIX}{symbol.upper()}-{quarter}"


def store_transcript(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    *,
    cik: str,
    symbol: str,
    quarter: str,
    reply: Reply,
    release: tuple[str, str] | None,
    now: datetime,
) -> str:
    """Store (or re-render) one transcript; returns its accession."""
    symbol = symbol.upper()
    accession = accession_for(symbol, quarter)
    url = f"alphavantage:EARNINGS_CALL_TRANSCRIPT:{symbol}:{quarter}"
    text, turns = render(symbol, quarter, reply)
    sha = hashlib.sha256(reply.raw).hexdigest()
    corpus.execute("BEGIN")
    try:
        old = corpus.execute("SELECT doc_id FROM document WHERE url = ?", (url,)).fetchone()
        if old is not None:
            ids = [r[0] for r in corpus.execute(
                "SELECT section_id FROM section WHERE doc_id = ?", (old[0],))]  # fmt: skip
            for sid in ids:
                corpus.execute("DELETE FROM section_fts WHERE rowid = ?", (sid,))
            corpus.execute(
                "DELETE FROM passage_fts WHERE rowid IN "
                "(SELECT passage_id FROM passage WHERE doc_id = ?)",
                (old[0],),
            )
            corpus.execute("DELETE FROM document WHERE doc_id = ?", (old[0],))
        doc_id = corpus.execute(
            "INSERT INTO document (accession, cik, filename, doc_type, url, content_type, text, "
            "sha256, fetched_at, parser_version, encoding, raw_size, description) "
            "VALUES (?, ?, ?, ?, ?, 'application/json', ?, ?, ?, ?, 'utf-8', ?, ?)",
            (accession, cik, FILENAME, DOC_TYPE, url, text, sha, iso(now), RENDERER_VERSION,
             len(reply.raw), f"Earnings call transcript, fiscal {ledger_label(quarter)}"),
        ).lastrowid  # fmt: skip
        assert doc_id is not None
        for t in turns:
            label = f"call {t.role}"
            title = f"{t.speaker} — {t.title}" if t.title else t.speaker
            sid = corpus.execute(
                "INSERT INTO section (doc_id, label, start_offset, end_offset, title, "
                "splitter_version) VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, label, t.start, t.end, title, RENDERER_VERSION),
            ).lastrowid
            corpus.execute(
                "INSERT INTO section_fts (rowid, label, body) VALUES (?, ?, ?)",
                (sid, fts_label(label, title, DOC_TYPE, FILENAME), text[t.start : t.end]),
            )
        write_passages(corpus, doc_id)
        corpus.execute(
            "INSERT INTO doc_raw (doc_id, source, symbol, quarter, original_name, body, sha256, "
            "fetched_at) VALUES (?, 'alpha_vantage', ?, ?, NULL, ?, ?, ?)",
            (doc_id, symbol, quarter, reply.raw, sha, iso(now)),
        )
        corpus.execute("COMMIT")
    except Exception:
        corpus.execute("ROLLBACK")
        raise
    engine.execute(
        "INSERT INTO call_document (accession, filename, cik, symbol, quarter, source, doc_kind, "
        "release_accession, stated_on, added_at) VALUES (?, ?, ?, ?, ?, 'alpha_vantage', "
        "'transcript', ?, ?, ?) ON CONFLICT (accession, filename) DO UPDATE SET "
        "release_accession = excluded.release_accession, stated_on = excluded.stated_on",
        (accession, FILENAME, cik, symbol, ledger_label(quarter),
         release[0] if release else None, release[1] if release else None, iso(now)),
    )  # fmt: skip
    return accession


def record_fetch(
    engine: sqlite3.Connection,
    due: Due,
    outcome: str,
    detail: str,
    now: datetime,
) -> None:
    engine.execute(
        "INSERT INTO call_fetch (symbol, quarter, cik, release_accession, release_filed, outcome, "
        "attempts, first_at, last_at, detail) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?) "
        "ON CONFLICT (symbol, quarter) DO UPDATE SET outcome = excluded.outcome, "
        "attempts = attempts + 1, last_at = excluded.last_at, detail = excluded.detail, "
        "release_accession = excluded.release_accession, release_filed = excluded.release_filed",
        (due.symbol, due.quarter, due.cik, due.release_accession or None,
         due.release_filed or None, outcome, iso(now), iso(now), detail[:300]),
    )  # fmt: skip


# --- Run step ----------------------------------------------------------------------


@dataclass
class FetchReport:
    planned: int = 0
    stored: list[str] = field(default_factory=list)  # "MSFT 2026Q4 (52 turns)"
    empty: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    stopped: str | None = None  # budget stop, reported, never silent
    left: int = 0  # due but not requested this run
    reminders: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"transcripts planned: {self.planned}, stored: {len(self.stored)}, "
            f"empty (not available yet): {len(self.empty)}, failed: {len(self.failed)}"
        ]
        out += [f"  stored {s}" for s in self.stored]
        out += [f"  empty {s}" for s in self.empty]
        out += [f"  FAILED {s}" for s in self.failed]
        if self.stopped:
            out.append(f"  stopped: {self.stopped}; {self.left} left for the next run")
        out += [f"  download reminder queued: {r}" for r in self.reminders]
        return out


def fetch_due(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    client: AlphaVantageClient,
    companies: dict[str, str],
    now: datetime,
    *,
    limit: int | None = None,
) -> FetchReport:
    rep = FetchReport()
    due = plan(engine, companies, now.date())
    rep.planned = len(due)
    for i, d in enumerate(due):
        if limit is not None and i >= limit:
            rep.left = len(due) - i
            rep.stopped = rep.stopped or f"limit of {limit} requests for this run"
            break
        res = client.transcript(d.symbol, d.quarter)
        tag = f"{d.symbol} {d.quarter}"
        if isinstance(res, Failed) and res.throttled:
            rep.stopped, rep.left = res.reason, len(due) - i
            break
        if isinstance(res, Ok):
            if res.data.turns:
                store_transcript(engine, corpus, cik=d.cik, symbol=d.symbol, quarter=d.quarter,
                                 reply=res.data, release=(d.release_accession, d.release_filed),
                                 now=now)  # fmt: skip
                record_fetch(engine, d, "ok", f"{len(res.data.turns)} turns", now)
                rep.stored.append(f"{tag} ({len(res.data.turns)} turns)")
            else:
                record_fetch(engine, d, "empty", "empty transcript (not available yet)", now)
                rep.empty.append(tag)
        else:
            reason = res.reason if isinstance(res, Failed) else str(res)
            record_fetch(engine, d, "failed", reason, now)
            rep.failed.append(f"{tag}: {reason}")
    rep.reminders = queue_reminders(engine, now)
    return rep


def queue_reminders(engine: sqlite3.Connection, now: datetime) -> list[str]:
    """`m02_ir_download` for calls still without a transcript 30 days after the release."""
    cutoff = (now.date() - timedelta(days=REMIND_AFTER_DAYS)).isoformat()
    out = []
    for r in engine.execute(
        "SELECT f.*, f.symbol AS ticker FROM call_fetch f WHERE f.outcome != 'ok' "
        "AND f.reminder_queued = 0 AND f.release_filed IS NOT NULL AND f.release_filed < ? "
        "ORDER BY f.release_filed",
        (cutoff,),
    ).fetchall():
        if engine.execute(
            "SELECT 1 FROM call_document WHERE cik = ? AND quarter = ?",
            (r["cik"], ledger_label(r["quarter"])),
        ).fetchone():
            continue  # the owner already added a company document for this quarter
        quarter = ledger_label(r["quarter"])
        payload = {
            "ticker": r["ticker"] or r["symbol"],
            "symbol": r["symbol"],
            "quarter": quarter,
            "av_quarter": r["quarter"],
            "release_accession": r["release_accession"],
            "release_filed": r["release_filed"],
            "why": f"No Alpha Vantage transcript {REMIND_AFTER_DAYS} days after the earnings "
            f"release ({r['attempts']} tries).",
            "what": "The call transcript or prepared remarks (PDF) from the company's "
            "investor-relations site. Save it to Downloads, then press 'I downloaded it'.",
        }
        proposals.propose(engine, "m02_ir_download", f"{r['symbol']}:{r['quarter']}",
                          f"{payload['ticker']} {quarter}: call document to download",
                          payload, now, cik=r["cik"])  # fmt: skip
        engine.execute(
            "UPDATE call_fetch SET reminder_queued = 1 WHERE symbol = ? AND quarter = ?",
            (r["symbol"], r["quarter"]),
        )
        out.append(f"{payload['ticker']} {quarter}")
    return out


def relink(engine: sqlite3.Connection) -> set[tuple[str, str]]:
    """Point each stored transcript at its quarter's results release (a release can arrive
    after the transcript, e.g. a newly tracked company); returns the documents changed."""
    changed = set()
    for r in engine.execute(
        "SELECT accession, filename, cik, quarter, release_accession FROM call_document "
        "WHERE source = 'alpha_vantage'"
    ).fetchall():
        av_quarter = r["quarter"][2:6] + "Q" + r["quarter"][-1]
        rel = company_releases(engine, r["cik"]).get(av_quarter)
        if rel is not None and rel[0] != r["release_accession"]:
            engine.execute(
                "UPDATE call_document SET release_accession = ?, stated_on = ? "
                "WHERE accession = ? AND filename = ?",
                (rel[0], rel[1], r["accession"], r["filename"]),
            )
            changed.add((r["accession"], r["filename"]))
    return changed


# --- Probe import (D-M02-20: the probe's replies are imported, not re-fetched) ---------


def symbol_cik(engine: sqlite3.Connection, symbol: str) -> str | None:
    row = engine.execute(
        "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL LIMIT 1", (symbol.upper(),)
    ).fetchone()
    return row[0] if row else None


def import_files(
    engine: sqlite3.Connection, corpus: sqlite3.Connection, files: Iterable[Path], now: datetime
) -> list[str]:
    """Store saved replies named <SYMBOL>_<YYYYQn>.json (the probe's raw output)."""
    lines = []
    for f in sorted(files):
        m = re.fullmatch(r"([A-Z.]+)_(\d{4}Q[1-4])", f.stem)
        if not m:
            lines.append(f"skipped {f.name}: name is not SYMBOL_YYYYQn.json")
            continue
        symbol, quarter = m.groups()
        cik = symbol_cik(engine, symbol)
        if cik is None:
            lines.append(f"skipped {f.name}: {symbol} is not in the ticker map")
            continue
        raw = f.read_bytes()
        if b"apikey" in raw.lower():
            lines.append(f"skipped {f.name}: contains an API key")
            continue
        reply = parse_reply(raw)
        if isinstance(reply, str):
            lines.append(f"skipped {f.name}: {reply}")
            continue
        release = company_releases(engine, cik).get(quarter)
        due = Due(symbol, cik, quarter, release[0] if release else "",
                  release[1] if release else "")  # fmt: skip
        if reply.turns:
            store_transcript(engine, corpus, cik=cik, symbol=symbol, quarter=quarter,
                             reply=reply, release=release, now=now)  # fmt: skip
            record_fetch(engine, due, "ok", f"imported from {f.name}", now)
            lines.append(f"imported {symbol} {quarter}: {len(reply.turns)} turns, "
                         f"release {release[1] if release else 'not found'}")  # fmt: skip
        else:
            record_fetch(engine, due, "empty", f"empty in {f.name}", now)
            lines.append(f"imported {symbol} {quarter}: empty (not available yet)")
    return lines


def raw_json(corpus: sqlite3.Connection, accession: str) -> dict | None:
    row = corpus.execute(
        "SELECT r.body FROM doc_raw r JOIN document d ON d.doc_id = r.doc_id WHERE d.accession = ?",
        (accession,),
    ).fetchone()
    return json.loads(row[0]) if row else None
