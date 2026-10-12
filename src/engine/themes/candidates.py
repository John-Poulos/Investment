"""Candidate companies for active themes (D-M02-10, -14, -15, -50; M02 part 6).

Each pass counts every active theme phrase in the season's latest window (≤ 10 pages,
resumable). Companies with hits that are not on the watchlist or tracked are ranked per
theme — distinct theme phrases, then hits, then the newest filing — and the strongest
(≤ `COMPANY_CAP` per pass, themes in turn) have one hit document read: each mention is
tagged by section and whether a number, $, % or money word sits within ~10 words. A
substantive mention (10-K Item 1 or 7, 10-Q Part I Item 2, or quantified, outside
boilerplate) makes a candidate (`m02_candidate`, accept = tracked tier); mention-only
names sit in the watch tier, listed on the Themes page. First-mention flags and the float
come from flags.py.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from engine.sec.client import SecClient, iso
from engine.sec.documents import ARCHIVES, DOC_TTL_S, IndexDoc, store_document
from engine.sec.results import Failed, Ok
from engine.themes import flags as flagmod
from engine.themes import industries
from engine.themes.mining import BOILERPLATE
from engine.themes.seasonal import TEST_PAGES, Season, Throttled, count
from engine.themes.universe import FAMILIES

COMPANY_CAP = 25
# 10-K business and MD&A, 10-Q MD&A (10-Q Part I Item 1 is the financial statements)
SUBSTANTIVE = frozenset({"10-K Item 1", "10-K Item 7", "10-Q Part I Item 2"})
# no text a company wrote about its business: a number there is a filing detail
NOT_TEXT = frozenset({"cover", "signatures", "10-K Item 15", "10-K Item 16",
                      "10-Q Part II Item 6"})  # fmt: skip
_MONEY = re.compile(
    r"\$|%|\b\d[\d,.]*\b|\b(?:revenue|revenues|sales|capex|capital expenditures?|orders?|"
    r"backlog|bookings|million|billion|invest(?:ed|ment|ing)?)\b", re.I,
)  # fmt: skip
WINDOW_WORDS = 10


@dataclass
class CandidateReport:
    phrases_counted: int = 0
    companies_seen: int = 0
    read: int = 0
    candidates: int = 0
    watch: int = 0
    proposed: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"candidates: {self.phrases_counted} theme phrases counted, "
               f"{self.companies_seen} companies outside the tiers, {self.read} documents read "
               f"→ {self.candidates} candidates, {self.watch} watch tier; proposals "
               f"{self.proposed or '{}'}"]  # fmt: skip
        out += [f"  problem: {p}" for p in self.problems[:15]]
        return out


def count_theme_phrases(client: SecClient, engine: sqlite3.Connection, s: Season, now: datetime,
                        over: Callable[[], bool]) -> int:  # fmt: skip
    n = 0
    for r in engine.execute(
        "SELECT p.phrase FROM theme_phrase p JOIN theme t ON t.theme_id = p.theme_id "
        "WHERE t.status = 'active' AND p.status = 'active' ORDER BY p.phrase_id"
    ).fetchall():
        if over():
            break
        count(client, engine, s, r[0].strip('"'), s.family, s.latest, TEST_PAGES, now)
        n += 1
    return n


def _excluded(engine: sqlite3.Connection, core: set[str]) -> set[str]:
    return core | {
        r[0] for r in engine.execute("SELECT cik FROM tier_member WHERE status = 'active'")
    }


def hits_by_company(engine: sqlite3.Connection, s: Season, theme_id: int,
                    exclude: set[str]) -> dict[str, dict[str, Any]]:  # fmt: skip
    """cik → {phrases, hits, sic, name, latest} from stored EFTS hits in the latest window."""
    phrases = [r[0] for r in engine.execute("SELECT phrase FROM theme_phrase WHERE theme_id = ? "
                                            "AND status = 'active'", (theme_id,))]  # fmt: skip
    if not phrases:
        return {}
    forms = ",".join(FAMILIES[s.family])
    marks = ",".join("?" * len(phrases))
    out: dict[str, dict[str, Any]] = {}
    for h in engine.execute(
        f"SELECT DISTINCT q.phrase, h.cik, h.accession, h.filename, h.form, h.file_date, "
        f"h.entity_name, h.sics FROM fulltext_hit h JOIN fulltext_query q USING (query_id) "
        f"WHERE q.phrase IN ({marks}) AND q.forms = ? AND h.file_date BETWEEN ? AND ? "
        f"AND h.cik IS NOT NULL ORDER BY h.file_date DESC",
        (*phrases, forms, *s.latest),
    ):
        if h["cik"] in exclude:
            continue
        sic = (json.loads(h["sics"] or "[]") or [None])[0]
        if sic == industries.BLANK_CHECK:
            continue
        c = out.setdefault(
            h["cik"],
            {
                "phrases": set(),
                "hits": [],
                "sic": sic,
                "name": h["entity_name"],
                "latest": h["file_date"],
            },
        )
        c["phrases"].add(h["phrase"])
        c["hits"].append(dict(h))
    return out


def first_mention(engine: sqlite3.Connection, cik: str, theme_id: int) -> str | None:
    """Earliest stored hit of the theme's phrases for this company (any window stored)."""
    r = engine.execute(
        "SELECT min(h.file_date) FROM fulltext_hit h JOIN fulltext_query q USING (query_id) "
        "WHERE h.cik = ? AND q.phrase IN (SELECT phrase FROM theme_phrase WHERE theme_id = ?)",
        (cik, theme_id),
    ).fetchone()
    return r[0] if r else None


def _pattern(phrase: str) -> re.Pattern[str]:
    words = re.findall(r"[A-Za-z0-9]+", phrase)
    return re.compile(r"\b" + r"[\s\-]+".join(re.escape(w) for w in words) + r"\b", re.I)


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    section: str
    quantified: bool
    boilerplate: bool

    @property
    def substantive(self) -> bool:
        if self.boilerplate or self.section in NOT_TEXT:
            return False
        return self.section in SUBSTANTIVE or self.quantified


def mentions(corpus: sqlite3.Connection, doc_id: int, phrases: list[str]) -> list[Mention]:
    text = corpus.execute("SELECT text FROM document WHERE doc_id = ?", (doc_id,)).fetchone()[0]
    secs = corpus.execute("SELECT label, start_offset, end_offset FROM section WHERE doc_id = ? "
                          "ORDER BY start_offset", (doc_id,)).fetchall()  # fmt: skip
    out = []
    for ph in phrases:
        for m in _pattern(ph.strip('"')).finditer(text):
            label = next((s[0] for s in secs if s[1] <= m.start() < s[2]), "whole")
            para_a = text.rfind("\n", 0, m.start()) + 1
            para_b = text.find("\n", m.end())
            para_b = para_b if para_b != -1 else len(text)
            para = text[para_a:para_b]
            # ~10 words either side, inside the mention's own paragraph (one line per
            # paragraph in stored text), so a heading's item number does not count
            before = text[max(para_a, m.start() - 120) : m.start()].split()[-WINDOW_WORDS:]
            after = text[m.end() : min(para_b, m.end() + 120)].split()[:WINDOW_WORDS]
            near = " ".join(before + after)
            out.append(Mention(m.start(), m.end(), label, bool(_MONEY.search(near)),
                               bool(BOILERPLATE.search(para))))  # fmt: skip
    return out


def _read_hit(client: SecClient, corpus: sqlite3.Connection, cik: str, hit: dict[str, Any],
              now: datetime) -> int | None:  # fmt: skip
    url = f"{ARCHIVES}/{int(cik)}/{hit['accession'].replace('-', '')}/{hit['filename']}"
    row = corpus.execute("SELECT doc_id FROM document WHERE url = ?", (url,)).fetchone()
    if row is not None:
        return row[0]
    res = client.get_bytes(url, ttl_s=DOC_TTL_S)
    if isinstance(res, Failed) and res.throttled:
        raise Throttled(f"{url}: {res.reason}")
    if not isinstance(res, Ok):
        return None
    doc = IndexDoc(None, None, hit["filename"], url, hit["form"], None, False)
    return store_document(corpus, cik, hit["accession"], doc, res.data, now).doc_id


def _pick(by_theme: dict[int, dict[str, dict[str, Any]]], cap: int) -> list[tuple[int, str]]:
    """Themes in turn, each theme's strongest company first."""
    queues = {
        t: sorted(
            cs,
            key=lambda c: (-len(cs[c]["phrases"]), -len(cs[c]["hits"]), cs[c]["latest"] or ""),
            reverse=False,
        )  # fmt: skip
        for t, cs in by_theme.items()
    }
    out: list[tuple[int, str]] = []
    seen: set[str] = set()
    while len(out) < cap and any(queues.values()):
        for t in sorted(queues):
            while queues[t] and queues[t][0] in seen:
                queues[t].pop(0)
            if queues[t] and len(out) < cap:
                c = queues[t].pop(0)
                seen.add(c)
                out.append((t, c))
    return out


def run_candidates(
    client: SecClient | None,
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    s: Season,
    core: set[str],
    now: datetime,
    over: Callable[[], bool],
    cap: int = COMPANY_CAP,
) -> CandidateReport:
    from engine.themes.proposals import propose

    rep = CandidateReport()
    if client is not None:
        rep.phrases_counted = count_theme_phrases(client, engine, s, now, over)
        rep.problems += flagmod.ensure_floats(client, engine, now.date(), now)
    exclude = _excluded(engine, core)
    themes = {r[0]: (r[1], r[2]) for r in engine.execute(
        "SELECT theme_id, key, name FROM theme WHERE status = 'active'")}  # fmt: skip
    done = {(r[0], r[1]) for r in engine.execute(
        "SELECT cik, theme_id FROM seasonal_company WHERE season = ? AND tier != 'unread'",
        (s.key,))}  # fmt: skip
    by_theme = {t: {c: v for c, v in hits_by_company(engine, s, t, exclude).items()
                    if (c, t) not in done} for t in themes}  # fmt: skip
    rep.companies_seen = len({c for cs in by_theme.values() for c in cs})
    tickers = {r[0]: r[1] for r in engine.execute(
        "SELECT cik, ticker FROM ticker WHERE valid_to IS NULL ORDER BY ticker DESC")}  # fmt: skip
    for tid, cik in _pick(by_theme, cap if client is not None else 0):
        if over():
            break
        info = by_theme[tid][cik]
        hit = sorted(info["hits"], key=lambda h: (h["form"] not in ("10-K", "10-Q"),
                                                  h["file_date"] or ""))[0]  # fmt: skip
        assert client is not None
        doc_id = _read_hit(client, corpus, cik, hit, now)
        rep.read += 1
        first = first_mention(engine, cik, tid) or hit["file_date"]
        # flags concern first mentions (D-M02-15): an older mention keeps only its size label
        is_first = first >= s.latest[0]
        fl, size, problem = flagmod.company_flags(client if is_first else None, engine, cik,
                                                  date.fromisoformat(first))  # fmt: skip
        if not is_first:
            fl = []
        if problem:
            rep.problems.append(f"{cik}: {problem}")
        ms = mentions(corpus, doc_id, sorted(info["phrases"])) if doc_id else []
        best = next((m for m in ms if m.substantive), ms[0] if ms else None)
        tier = (
            "unread" if doc_id is None else ("candidate" if best and best.substantive else "watch")
        )
        quote = None
        if best is not None:
            text = corpus.execute(
                "SELECT substr(text, ?, ?) FROM document WHERE doc_id = ?",
                (max(1, best.start - 299), 700, doc_id),
            ).fetchone()[0]
            quote = " ".join(text.split())
        engine.execute(
            "INSERT OR REPLACE INTO seasonal_company (season, cik, theme_id, name, ticker, "
            "phrases, first_mention, tier, section, quantified, quote, accession, filename, "
            "quote_start, quote_end, flags, float_usd, float_as_of, float_ref, size_label, detail, "
            "discovered_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?)",
            (s.key, cik, tid, info["name"], tickers.get(cik), json.dumps(sorted(info["phrases"])),
             first, tier, best.section if best else None,
             int(best.quantified) if best else None, quote, hit["accession"], hit["filename"],
             best.start if best else None, best.end if best else None, json.dumps(fl),
             size.value, size.as_of, size.accession, size.label,
             None if doc_id else "hit document could not be read", iso(now), iso(now)),
        )  # fmt: skip
        if tier == "candidate":
            rep.candidates += 1
            key, name = themes[tid]
            first_note = ("first mention this season" if first >= s.latest[0]
                          else f"mentioned since {first}")  # fmt: skip
            payload = {
                "ticker": tickers.get(cik), "name": info["name"], "theme_key": key,
                "theme_name": name, "phrases": [p.strip('"') for p in sorted(info["phrases"])],
                "section": best.section if best else None,
                "quantified": bool(best and best.quantified), "quote": quote,
                "accession": hit["accession"], "filename": hit["filename"],
                "offsets": [best.start, best.end] if best else None, "flags": fl,
                "size": size.label, "float_as_of": size.as_of, "float_ref": size.accession,
                "first_mention": first, "first_note": first_note,
                "industry": industries.group_of(info["sic"]), "grade": "A", "money_flow": False,
                "companies": 1, "season": s.key,
                "why": f"{len(info['phrases'])} {name} phrase(s); {best.section if best else ''}"
                       f"{', quantified' if best and best.quantified else ''}; {first_note}"
                       + (f"; flags: {'; '.join(fl)}" if fl else ""),
            }  # fmt: skip
            label = tickers.get(cik) or info["name"] or cik
            res = propose(engine, "m02_candidate", cik, f"{label}: candidate for {name}",
                          payload, now, cik=cik)  # fmt: skip
            rep.proposed[res] = rep.proposed.get(res, 0) + 1
        elif tier == "watch":
            rep.watch += 1
    return rep
