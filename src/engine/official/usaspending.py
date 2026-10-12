"""USAspending: federal prime awards to watchlist/tracked companies (D-M02-13, D-M02-15).

API v2 (no key): `POST api.usaspending.gov/api/v2/search/spending_by_award/` with
{filters: {award_type_codes (one group per request: contracts A–D, grants 02–05),
recipient_search_text: [term], time_period: [{start_date, end_date,
date_type: "new_awards_only"}]}, fields, limit, page, sort, order} → {results: [{internal_id,
"Award ID", "Recipient Name", "Recipient UEI", recipient_id, "Award Amount",
"Base Obligation Date", "Start Date", "Last Modified Date", "Awarding Agency",
"Awarding Sub Agency", "Contract Award Type" | "Award Type", "Description",
generated_internal_id}], page_metadata: {page, hasNext}}. Recipient profile:
`GET /api/v2/recipient/{recipient_id}/` → {name, uei, recipient_level, parent_name,
parent_uei, …}.

Guards (D-M02-15): amounts are **obligations** ("Award Amount" = total obligated to date),
not cash paid; DoD data arrive with a 90-day delay, so each run asks again from 120 days
before the last success; awards are new awards (base date in the window). The recipient
search is fuzzy, so mapping a recipient to a company is conservative:
- 'name': the stated recipient name equals a known name of the company (SEC name or
  `config/aliases.toml`) after case, punctuation, a leading "The" and a legal suffix;
- 'parent': else the recipient profile's parent (name the same way, or the UEI of a
  recipient already mapped by name);
- 'none': else left unmapped and shown as such on the company page.
Per run: companies not checked for `RECHECK_DAYS`, ≤ `MAX_COMPANIES`; ≤ 3 search terms per
company; ≤ `MAX_PAGES` pages per term and group; ≤ `MAX_PROFILES` recipient profiles.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.news.fetch import Fetcher
from engine.official.common import Budget, snip, state_get, state_set, write
from engine.sec.client import iso
from engine.sec.results import Failed
from engine.supply import aliases

SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
RECIPIENT_URL = "https://api.usaspending.gov/api/v2/recipient/{}/"
GROUPS = {"contracts": ["A", "B", "C", "D"], "grants": ["02", "03", "04", "05"]}
TYPE_FIELD = {"contracts": "Contract Award Type", "grants": "Award Type"}
BASE_FIELDS = ["Award ID", "Recipient Name", "Recipient UEI", "recipient_id", "Award Amount",
               "Base Obligation Date", "Start Date", "Last Modified Date", "Awarding Agency",
               "Awarding Sub Agency", "Description", "generated_internal_id"]  # fmt: skip
FIRST_DAYS = 365
DELAY_DAYS = 120  # DoD reports with a 90-day delay; ask again over the last 120 days
EARLIEST = date(2007, 10, 1)  # the API's earliest search date
RECHECK_DAYS = 7
MAX_COMPANIES = 15
MAX_TERMS = 3
MAX_PAGES = 2
PAGE = 100
MAX_PROFILES = 20

_SUFFIX = re.compile(
    r"\b(?:inc|incorporated|corp|corporation|co|company|llc|l l c|ltd|limited|plc|lp|llp|"
    r"sa|ag|nv|bv|se)\b\.?",
    re.I,
)


def norm(name: str | None) -> str:
    """Upper-case words without punctuation, a leading "The" or legal suffixes at the end."""
    if not name:
        return ""
    words = re.findall(r"[A-Za-z0-9&]+", name.replace("'", ""))
    while words and words[0].lower() == "the":
        words = words[1:]
    while words and _SUFFIX.fullmatch(words[-1]):
        words = words[:-1]
    return " ".join(w.upper() for w in words)


@dataclass(frozen=True)
class Company:
    ticker: str
    cik: str
    names: tuple[str, ...]  # SEC name first, then aliases

    @property
    def keys(self) -> set[str]:
        return {k for k in (norm(n) for n in self.names) if k}

    def terms(self) -> list[str]:
        """Search terms: distinct normalised names, shortest covering ones only (a name
        containing a shorter one as whole words is covered), ≥ 4 characters, ≤ MAX_TERMS."""
        keys = sorted(self.keys, key=len)
        out: list[str] = []
        for k in keys:
            if len(k) < 4:
                continue
            if any(re.search(rf"(?<!\w){re.escape(o)}(?!\w)", k) for o in out):
                continue
            out.append(k)
        return out[:MAX_TERMS]


def companies_for(engine: sqlite3.Connection, tickers: dict[str, str]) -> list[Company]:
    """ticker → cik for the run; names from the SEC registry and config/aliases.toml."""
    by_cik: dict[str, list[str]] = {}
    for c in aliases.load(engine):
        if c.cik:
            by_cik.setdefault(c.cik, []).extend(c.names)
    out = []
    for t, cik in sorted(tickers.items()):
        r = engine.execute("SELECT name FROM entity WHERE cik = ?", (cik,)).fetchone()
        names = ([r["name"]] if r else []) + by_cik.get(cik, [])
        if names:
            out.append(Company(t, cik, tuple(dict.fromkeys(names))))
    return out


@dataclass(frozen=True)
class Award:
    key: str
    award_id: str
    group: str
    award_type: str | None
    recipient: str
    uei: str | None
    recipient_id: str | None
    amount: float | None
    base_date: str | None
    start_date: str | None
    last_modified: str | None
    agency: str | None
    sub_agency: str | None
    description: str | None


def body(term: str, group: str, start: date, end: date, page: int) -> dict:
    return {
        "filters": {
            "award_type_codes": GROUPS[group],
            "recipient_search_text": [term],
            "time_period": [
                {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "date_type": "new_awards_only",
                }
            ],  # fmt: skip
        },
        "fields": BASE_FIELDS + [TYPE_FIELD[group]],
        "limit": PAGE,
        "page": page,
        "sort": "Award Amount",
        "order": "desc",
    }


def parse(data: bytes, group: str) -> tuple[list[Award], bool] | str:
    """(awards, has next page) or an error text."""
    try:
        d = json.loads(data)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if not isinstance(d, dict) or not isinstance(d.get("results"), list):
        msg = d.get("message") or d.get("detail") if isinstance(d, dict) else None
        return f"error: {str(msg)[:200]}" if msg else "unexpected reply shape"
    out = []
    for r in d["results"]:
        if not isinstance(r, dict):
            continue
        key = r.get("generated_internal_id") or (
            f"{group}:{r['internal_id']}" if r.get("internal_id") is not None else None
        )
        name = " ".join(str(r.get("Recipient Name") or "").split())
        if not key or not name or not r.get("Award ID"):
            continue
        amt = r.get("Award Amount")
        out.append(
            Award(
                str(key), str(r["Award ID"]), group, r.get(TYPE_FIELD[group]) or None, name,
                r.get("Recipient UEI") or None, r.get("recipient_id") or None,
                float(amt) if isinstance(amt, int | float) else None,
                r.get("Base Obligation Date") or None, r.get("Start Date") or None,
                r.get("Last Modified Date") or None, r.get("Awarding Agency") or None,
                r.get("Awarding Sub Agency") or None, snip(r.get("Description")),
            )
        )  # fmt: skip
    meta = d.get("page_metadata") if isinstance(d.get("page_metadata"), dict) else {}
    return out, bool(meta.get("hasNext"))


def _store(engine, awards: list[Award], co: Company, term: str, now: datetime) -> int:
    new = 0
    with write(engine):
        for a in awards:
            new += engine.execute("SELECT 1 FROM usa_award WHERE award_key = ?",
                                  (a.key,)).fetchone() is None  # fmt: skip
            engine.execute(
                "INSERT INTO usa_award (award_key, award_id, award_group, award_type, "
                "recipient_name, recipient_uei, recipient_id, amount, base_date, start_date, "
                "last_modified, agency, sub_agency, description, searched_cik, search_term, "
                "first_seen_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?) ON CONFLICT (award_key) DO UPDATE SET amount = excluded.amount, "
                "last_modified = excluded.last_modified, award_type = excluded.award_type, "
                "description = excluded.description, updated_at = excluded.updated_at",
                (a.key, a.award_id, a.group, a.award_type, a.recipient, a.uei, a.recipient_id,
                 a.amount, a.base_date, a.start_date, a.last_modified, a.agency, a.sub_agency,
                 a.description, co.cik, term, iso(now), iso(now)),
            )  # fmt: skip
            if a.recipient_id:
                _map_by_name(engine, a, co, now)
    return new


def _map_by_name(engine, a: Award, co: Company, now: datetime) -> None:
    row = engine.execute("SELECT how FROM usa_recipient WHERE recipient_id = ?",
                         (a.recipient_id,)).fetchone()  # fmt: skip
    if row and row["how"] != "none":
        return
    hit = norm(a.recipient) in co.keys
    if row is None:
        engine.execute(
            "INSERT INTO usa_recipient (recipient_id, name, uei, cik, how, checked_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (a.recipient_id, a.recipient, a.uei, co.cik if hit else None,
             "name" if hit else "none", iso(now)),
        )  # fmt: skip
    elif hit:
        engine.execute("UPDATE usa_recipient SET cik = ?, how = 'name', checked_at = ? "
                       "WHERE recipient_id = ?", (co.cik, iso(now), a.recipient_id))  # fmt: skip


def map_parents(
    engine: sqlite3.Connection,
    fetcher: Fetcher,
    cos: list[Company],
    now: datetime,
    budget: Budget,
    limit: int = MAX_PROFILES,
) -> tuple[int, int, list[str]]:
    """Read profiles of unmapped recipients (never read before) and map by parent.
    Returns (profiles read, mapped by parent, failures)."""
    by_key = {k: c.cik for c in cos for k in c.keys}
    rows = engine.execute(
        "SELECT recipient_id FROM usa_recipient WHERE how = 'none' AND profile_at IS NULL "
        "ORDER BY checked_at LIMIT ?", (limit,)
    ).fetchall()  # fmt: skip
    read = mapped = 0
    fails: list[str] = []
    for r in rows:
        if budget.spent("usaspending"):
            break
        rid = r["recipient_id"]
        got = fetcher.get(RECIPIENT_URL.format(rid), lane="usaspending")
        if isinstance(got, Failed):
            fails.append(f"recipient {rid}: {got.reason}")
            if got.throttled:
                break
            continue
        try:
            p = json.loads(got.body)
        except ValueError:
            fails.append(f"recipient {rid}: unreadable JSON")
            continue
        if not isinstance(p, dict):
            fails.append(f"recipient {rid}: unexpected reply shape")
            continue
        read += 1
        pname, puei = p.get("parent_name") or None, p.get("parent_uei") or None
        cik = by_key.get(norm(pname)) if pname else None
        if cik is None and puei:
            hit = engine.execute(
                "SELECT cik FROM usa_recipient WHERE uei = ? AND how = 'name'", (puei,)
            ).fetchone()
            cik = hit["cik"] if hit else None
        with write(engine):
            engine.execute(
                "UPDATE usa_recipient SET level = ?, parent_name = ?, parent_uei = ?, cik = ?, "
                "how = ?, profile_at = ?, checked_at = ? WHERE recipient_id = ?",
                (p.get("recipient_level"), pname, puei, cik, "parent" if cik else "none",
                 iso(now), iso(now), rid),
            )  # fmt: skip
        mapped += cik is not None
    return read, mapped, fails


@dataclass
class UsaResult:
    companies: int = 0
    seen: int = 0
    new: int = 0
    profiles: int = 0
    by_parent: int = 0
    failures: list[str] = field(default_factory=list)
    stopped: str = ""
    left: int = 0  # companies due but not reached


def run(
    engine: sqlite3.Connection,
    fetcher: Fetcher,
    tickers: dict[str, str],
    now: datetime,
    budget: Budget,
    *,
    max_companies: int = MAX_COMPANIES,
) -> UsaResult:
    res = UsaResult()
    today = now.date()
    cos = companies_for(engine, tickers)
    due = []
    for c in cos:
        last = state_get(engine, f"official:usaspending:{c.cik}")
        if last is None or date.fromisoformat(last[:10]) <= today - timedelta(days=RECHECK_DAYS):
            due.append((last or "", c))
    due.sort(key=lambda x: x[0])  # never checked first, then oldest
    for i, (last, co) in enumerate(due):
        if i >= max_companies or budget.spent("usaspending"):
            res.left = len(due) - i
            res.stopped = ("time budget spent" if i < max_companies else
                           f"{max_companies} companies a run") + "; the rest next run"  # fmt: skip
            break
        start = (date.fromisoformat(last[:10]) - timedelta(days=DELAY_DAYS) if last
                 else today - timedelta(days=FIRST_DAYS))  # fmt: skip
        start = max(start, EARLIEST)
        ok, seen = True, 0
        for term in co.terms():
            for group in GROUPS:
                for page in range(1, MAX_PAGES + 1):
                    shown = f"{SEARCH_URL} {term} {group} p{page}"
                    got = fetcher.post_json(SEARCH_URL, body(term, group, start, today, page),
                                            lane="usaspending", logged_url=shown)  # fmt: skip
                    if isinstance(got, Failed):
                        res.failures.append(f"{co.ticker} {term} {group}: {got.reason}")
                        ok = False
                        break
                    parsed = parse(got.body, group)
                    if isinstance(parsed, str):
                        res.failures.append(f"{co.ticker} {term} {group}: {parsed}")
                        ok = False
                        break
                    awards, more = parsed
                    seen += len(awards)
                    res.new += _store(engine, awards, co, term, now)
                    if not more:
                        break
        res.seen += seen
        if ok:
            res.companies += 1
            note = f"{seen} award(s) since {start}, terms {', '.join(co.terms())}"
            with write(engine):
                state_set(engine, f"official:usaspending:{co.cik}", SEARCH_URL, now, note)
    read, mapped, fails = map_parents(engine, fetcher, cos, now, budget)
    res.profiles, res.by_parent = read, mapped
    res.failures += fails
    return res
