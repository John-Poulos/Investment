"""Congress.gov: bills whose title or summary contains a theme phrase (D-M02-13).

API v3 (free api.data.gov key `CONGRESS_API_KEY`, 5,000 requests/hour): the key goes in the
`X-Api-Key` header (api.data.gov's header); if the API refuses it there (HTTP 403), once in
the `api_key` query parameter — never logged (masked, logged URLs carry no key).
The API has no text search, so the engine lists the current Congress's bills and summaries
and matches phrases itself:
- `GET /v3/bill/{congress}?format=json&limit=250&offset=&sort=updateDate+desc
  [&fromDateTime=YYYY-MM-DDT00:00:00Z]` → {bills: [{congress, type, number, title,
  latestAction: {actionDate, text}, updateDate, url, originChamber}], pagination: {count, next}};
- `GET /v3/summaries/{congress}?…` → {summaries: [{bill: {congress, type, number, title, url},
  text (HTML), actionDate, actionDesc, updateDate, versionCode}], pagination};
- `GET /v3/bill/{congress}/{type}/{number}?format=json` → {bill: {…, latestAction, laws}} for a
  bill first found through its summary (≤ `MAX_DETAILS` a run).

Status: "enacted" when the latest action says it became law (or `laws` is present), else
"introduced" — most bills never pass (D-M02-15); only enacted ones would be events.
First run lists the whole current Congress (≈ 60 + 40 requests); later runs ask from the
last complete listing − 1 day. A listing stopped by the time budget resumes at its offset.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from engine.news.fetch import Fetcher, Reply
from engine.news.match import phrase_pattern
from engine.official.common import (
    Budget,
    Phrase,
    link_theme,
    snip,
    state_detail,
    state_get,
    state_set,
    write,
)
from engine.sec.client import iso
from engine.sec.results import Failed

BASE = "https://api.congress.gov/v3"
PAGE = 250
MAX_DETAILS = 20
_LAW = re.compile(r"\bBecame (?:Public|Private) Law\b", re.I)
_PAGE_TYPES = {
    "HR": "house-bill",
    "S": "senate-bill",
    "HJRES": "house-joint-resolution",
    "SJRES": "senate-joint-resolution",
    "HCONRES": "house-concurrent-resolution",
    "SCONRES": "senate-concurrent-resolution",
    "HRES": "house-resolution",
    "SRES": "senate-resolution",
}


def current_congress(today: date) -> int:
    return (today.year - 1789) // 2 + 1


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def bill_id(congress: int, bill_type: str, number: str) -> str:
    return f"{congress}-{bill_type.lower()}-{number}"


def page_url(congress: int, bill_type: str, number: str) -> str | None:
    kind = _PAGE_TYPES.get(bill_type.upper())
    if not kind:
        return None
    return f"https://www.congress.gov/bill/{ordinal(congress)}-congress/{kind}/{number}"


def status_of(latest_action: str | None, laws: list | None = None) -> str:
    return "enacted" if laws or (latest_action and _LAW.search(latest_action)) else "introduced"


@dataclass(frozen=True)
class Bill:
    congress: int
    bill_type: str
    number: str
    title: str
    action_date: str | None
    action: str | None
    update_date: str | None
    laws: tuple = ()

    @property
    def id(self) -> str:
        return bill_id(self.congress, self.bill_type, self.number)

    @property
    def status(self) -> str:
        return status_of(self.action, list(self.laws))


def _bill(d: dict) -> Bill | None:
    try:
        congress, bill_type, number = int(d["congress"]), str(d["type"]), str(d["number"])
    except KeyError, TypeError, ValueError:
        return None
    title = " ".join(str(d.get("title") or "").split())
    if not title:
        return None
    la = d.get("latestAction") if isinstance(d.get("latestAction"), dict) else {}
    laws = d.get("laws") if isinstance(d.get("laws"), list) else []
    return Bill(congress, bill_type, number, title, la.get("actionDate"), la.get("text"),
                d.get("updateDate"), tuple(laws))  # fmt: skip


def parse_list(body: bytes, key: str) -> tuple[list[dict], str | None, int | None] | str:
    """(items, next url, total count) or an error text."""
    try:
        data = json.loads(body)
    except ValueError as e:
        return f"unreadable JSON: {e}"
    if not isinstance(data, dict):
        return "unexpected reply shape"
    if data.get("error"):
        return f"error: {str(data['error'])[:200]}"
    items = data.get(key)
    if not isinstance(items, list):
        return f"no '{key}' list in the reply"
    pg = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    return [i for i in items if isinstance(i, dict)], pg.get("next"), pg.get("count")


class Api:
    """Key handling: header first; one fallback to the query parameter on HTTP 403."""

    def __init__(self, fetcher: Fetcher, key: str) -> None:
        self.fetcher, self.key, self.in_query = fetcher, key, False

    def get(self, path: str, params: dict[str, str]) -> Reply | Failed:
        url = f"{BASE}{path}"
        shown = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        p = {"format": "json"} | params
        if self.in_query:
            return self.fetcher.get(url, lane="congress", params=p | {"api_key": self.key},
                                    logged_url=shown)  # fmt: skip
        got = self.fetcher.get(url, lane="congress", params=p, headers={"X-Api-Key": self.key},
                               logged_url=shown)  # fmt: skip
        if isinstance(got, Failed) and got.status == 403:
            self.in_query = True
            return self.get(path, params)
        return got


@dataclass
class CongressResult:
    listed: int = 0  # bills and summaries read
    matched: int = 0
    new: int = 0
    enacted_new: int = 0  # stored bills that became law this run
    failures: list[str] = field(default_factory=list)
    stopped: str = ""


class _Matcher:
    def __init__(self, phrases: list[Phrase]) -> None:
        self.items = [(p, phrase_pattern(p.phrase)) for p in phrases]

    def find(self, text: str) -> dict[int, Phrase]:
        out: dict[int, Phrase] = {}
        for p, rx in self.items:
            if p.theme_id not in out and rx.search(text):
                out[p.theme_id] = p
        return out


def _upsert(engine, b: Bill, summary: str | None, now: datetime, res: CongressResult) -> None:
    old = engine.execute("SELECT status FROM congress_bill WHERE bill_id = ?", (b.id,)).fetchone()
    if old is None:
        engine.execute(
            "INSERT INTO congress_bill (bill_id, congress, bill_type, number, title, summary, "
            "latest_action_date, latest_action, status, url, update_date, first_seen_at, "
            "updated_at, enacted_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (b.id, b.congress, b.bill_type.upper(), b.number, b.title, summary, b.action_date,
             b.action, b.status, page_url(b.congress, b.bill_type, b.number), b.update_date,
             iso(now), iso(now), iso(now) if b.status == "enacted" else None),
        )  # fmt: skip
        res.new += 1
        return
    if old["status"] != "enacted" and b.status == "enacted":
        res.enacted_new += 1
        engine.execute("UPDATE congress_bill SET enacted_seen_at = ? WHERE bill_id = ?",
                       (iso(now), b.id))  # fmt: skip
    engine.execute(
        "UPDATE congress_bill SET title = ?, latest_action_date = coalesce(?, latest_action_date), "
        "latest_action = coalesce(?, latest_action), status = CASE WHEN status = 'enacted' "
        "THEN 'enacted' ELSE ? END, update_date = coalesce(?, update_date), "
        "summary = coalesce(?, summary), updated_at = ? WHERE bill_id = ?",
        (b.title, b.action_date, b.action, b.status, b.update_date, summary, iso(now), b.id),
    )


def _listing(api, engine, path, key, name, since, budget, res, handle, now) -> bool:
    """Page through one listing; True when it reached the end. Progress is kept in
    refresh_state detail (offset) so a budget stop resumes there."""
    progress = state_detail(engine, name + ":offset")
    offset = int(progress) if progress and progress.isdigit() else 0
    while True:
        if budget.spent("congress"):
            res.stopped = "time budget spent; the listing resumes next run"
            return False
        params = {"limit": str(PAGE), "offset": str(offset), "sort": "updateDate desc"}
        if since:
            params["fromDateTime"] = f"{since.isoformat()}T00:00:00Z"
        got = api.get(path, params)
        if isinstance(got, Failed):
            res.failures.append(f"{path} offset {offset}: {got.reason}")
            return False
        parsed = parse_list(got.body, key)
        if isinstance(parsed, str):
            res.failures.append(f"{path} offset {offset}: {parsed}")
            return False
        items, nxt, _total = parsed
        res.listed += len(items)
        with write(engine):
            for it in items:
                handle(it)
            offset += len(items)
            state_set(engine, name + ":offset", BASE, now, str(offset))
        if not nxt or not items:
            with write(engine):
                engine.execute("DELETE FROM refresh_state WHERE name = ?", (name + ":offset",))
            return True


def run(
    engine: sqlite3.Connection,
    fetcher: Fetcher,
    key: str | None,
    phrases: list[Phrase],
    now: datetime,
    budget: Budget,
) -> CongressResult:
    res = CongressResult()
    if not key:
        res.stopped = "skipped — CONGRESS_API_KEY is not set in .env"
        return res
    api = Api(fetcher, key)
    matcher = _Matcher(phrases)
    congress = current_congress(now.date())

    def on_bill(d: dict) -> None:
        b = _bill(d)
        if b is None:
            return
        found = matcher.find(b.title)
        known = engine.execute("SELECT 1 FROM congress_bill WHERE bill_id = ?",
                               (b.id,)).fetchone()  # fmt: skip
        if found or known:
            _upsert(engine, b, None, now, res)
        for tid, p in found.items():
            res.matched += 1
            link_theme(engine, "congress", b.id, tid, p.phrase, now)

    def on_summary(d: dict) -> None:
        bd = d.get("bill") if isinstance(d.get("bill"), dict) else None
        b = _bill(bd) if bd else None
        if b is None:
            return
        text = snip(d.get("text"))
        found = matcher.find(d.get("text") or "") if text else {}
        known = engine.execute("SELECT 1 FROM congress_bill WHERE bill_id = ?",
                               (b.id,)).fetchone()  # fmt: skip
        if not known and not found:
            return
        # a summary carries the bill's stage ("Public Law" …), not its latest action
        stage = str(d.get("actionDesc") or "")
        laws = ("summary",) if "public law" in stage.lower() else ()
        _upsert(engine, Bill(b.congress, b.bill_type, b.number, b.title, None, None, None, laws),
                text, now, res)  # fmt: skip
        for tid, p in found.items():
            res.matched += 1
            link_theme(engine, "congress", b.id, tid, p.phrase, now)

    for path, key_name, handler, label in (
        (f"/bill/{congress}", "bills", on_bill, "bills"),
        (f"/summaries/{congress}", "summaries", on_summary, "summaries"),
    ):
        name = f"official:congress:{label}:{congress}"
        last = state_get(engine, name)
        since = date.fromisoformat(last[:10]) - timedelta(days=1) if last else None
        if last and last[:10] == now.date().isoformat():
            continue  # once a day
        if _listing(api, engine, path, key_name, name, since, budget, res, handler, now):
            with write(engine):
                state_set(engine, name, BASE, now, f"{label} listed")
    # bills first found through a summary: read their latest action (≤ MAX_DETAILS a run)
    missing = engine.execute(
        "SELECT congress, bill_type, number FROM congress_bill WHERE latest_action IS NULL "
        "ORDER BY first_seen_at DESC LIMIT ?", (MAX_DETAILS,)
    ).fetchall()  # fmt: skip
    for m in missing:
        if budget.spent("congress"):
            res.stopped = "time budget spent; latest actions wait for the next run"
            break
        got = api.get(f"/bill/{m['congress']}/{m['bill_type'].lower()}/{m['number']}", {})
        if isinstance(got, Failed):
            res.failures.append(f"bill {m['bill_type']} {m['number']}: {got.reason}")
            continue
        try:
            detail = json.loads(got.body).get("bill")
        except ValueError, AttributeError:
            detail = None
        b = _bill(detail) if isinstance(detail, dict) else None
        if b is None:
            res.failures.append(f"bill {m['bill_type']} {m['number']}: unreadable detail")
            continue
        with write(engine):
            _upsert(engine, b, None, now, res)
    return res
