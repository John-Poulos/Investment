"""Part-6 probe (M02 seasonal pass, D-M02-8, -49…51). Owner runs it; send the log back.

    uv run python scripts/probe_seasonal.py            # local checks + ~30 SEC requests
    uv run python scripts/probe_seasonal.py --no-sec   # local checks only

Local (no network): corpus composition by period; prototype phrase mining (last 12
months vs the 12 before) with run time; industry spread of the seed phrases' stored
part-1 hits under the D-M02-49 cut-offs. Network: Ken French's Siccodes12.zip (one
small file, read in memory, compared with engine/themes/industries.py); SEC (≈ 30
requests at 5/s): fund-registration forms for two phrases (crowding), public-float
frames for four 2025 quarter-ends, page 1 of the top 10 mined phrases in both windows
(screen pace and counts). Writes logs/probe_seasonal_<timestamp>.txt.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.store.db import open_db  # noqa: E402
from engine.themes import industries, mining  # noqa: E402

SICCODES = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Siccodes12.zip"


def p_rise(n1: int, n0: int, p: float = 0.5) -> float:
    """One-sided conditional binomial: P(X ≥ n1), X ~ Bin(n0 + n1, p)."""
    n = n0 + n1
    return sum(comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n1, n + 1))


def composition(docs: list[mining.Doc], cuts: list[tuple[str, str, str]]) -> list[str]:
    out = ["\n== Corpus composition (documents · companies) =="]
    kinds = Counter()
    for d in docs:
        kinds[_kind(d)] += 1
    out.append("all: " + ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
    for name, s, e in cuts:
        sel = [d for d in docs if s <= d.dated <= e]
        by = Counter(_kind(d) for d in sel)
        out.append(f"{name} {s}..{e}: {len(sel)} docs, {len({d.cik for d in sel})} companies; "
                   + ", ".join(f"{k} {n}" for k, n in by.most_common()))  # fmt: skip
    years = Counter(d.dated[:4] for d in docs)
    out.append("by year: " + ", ".join(f"{y} {n}" for y, n in sorted(years.items())))
    return out


def _kind(d: mining.Doc) -> str:
    if d.accession.startswith(("AV-", "IR-")):
        return "call/IR"
    return d.doc_type or "?"


def mine(engine, corpus, docs, latest, prior, watch: set[str]) -> tuple[list[str], list[str]]:
    out = ["\n== Prototype mining (distinct companies per phrase) =="]
    both = {d.cik for d in docs if latest[0] <= d.dated <= latest[1]} & {
        d.cik for d in docs if prior[0] <= d.dated <= prior[1]}  # fmt: skip
    t0 = time.monotonic()
    a = mining.count_period(corpus, docs, *latest, keep_sets_for=both)
    t1 = time.monotonic()
    b = mining.count_period(corpus, docs, *prior, keep_sets_for=both)
    t2 = time.monotonic()
    out.append(f"latest {latest}: {a.n_docs} docs, {a.n_companies} companies, "
               f"{len(a.companies):,} phrases, {t1 - t0:.0f} s, pruned {a.pruned}×")  # fmt: skip
    out.append(f"prior  {prior}: {b.n_docs} docs, {b.n_companies} companies, "
               f"{len(b.companies):,} phrases, {t2 - t1:.0f} s, pruned {b.pruned}×")  # fmt: skip
    out.append(f"companies with documents in both periods: {len(both)} "
               f"({len(both & watch)} on the watchlist/tracked)")  # fmt: skip
    for floor in (2, 3, 5):
        out.append(f"  phrases with ≥ {floor} companies in latest: "
                   f"{sum(1 for v in a.companies.values() if v >= floor):,}")  # fmt: skip

    # A: all companies, latest vs prior, generic phrases (in > 30% of prior companies) out
    gen_cut = max(3, int(0.3 * b.n_companies))
    rows = []
    for g, n1 in a.companies.items():
        n0 = b.companies.get(g, 0)
        if n1 >= 3 and n0 < gen_cut and n1 >= 2 * max(n0, 1):
            rows.append((n1 - n0, n1, n0, g))
    rows.sort(reverse=True)
    out.append(f"\nA. latest ≥ 3 companies, at least double the prior, prior < {gen_cut} "
               f"(generic cut): {len(rows):,} phrases; top 40 (latest, prior, p):")  # fmt: skip
    for _, n1, n0, g in rows[:40]:
        out.append(f"  {g:<40} {n1:>4} {n0:>4}  p={p_rise(n1, n0):.3f}")

    # B: same companies only (documents in both periods): new adopters vs drops
    newc: Counter[str] = Counter()
    drop: Counter[str] = Counter()
    for cik in both:
        sa, sb = (a.by_company or {}).get(cik, set()), (b.by_company or {}).get(cik, set())
        newc.update(sa - sb)
        drop.update(sb - sa)
    rowsb = sorted(((newc[g] - drop.get(g, 0), newc[g], drop.get(g, 0), g) for g in newc
                    if newc[g] >= 2 and b.companies.get(g, 0) < gen_cut), reverse=True)  # fmt: skip
    out.append(f"\nB. companies present in both periods: phrases new at ≥ 2 of them: "
               f"{len(rowsb):,}; top 40 (new, dropped, latest all):")  # fmt: skip
    for _, n, dr, g in rowsb[:40]:
        out.append(f"  {g:<40} {n:>4} {dr:>4} {a.companies.get(g, 0):>5}")
    return out, [g for _, _, _, g in rows[:10]]


def spread_check(engine) -> list[str]:
    out = ["\n== Spread of seed phrases (stored part-1 hits, latest window per phrase) ==",
           f"cut-offs: generic when top group < {industries.GENERIC_TOP1:.0%} and top two < "
           f"{industries.GENERIC_TOP2:.0%}"]  # fmt: skip
    phrases = [
        r[0]
        for r in engine.execute(
            "SELECT DISTINCT phrase FROM theme_phrase WHERE status = 'active' ORDER BY phrase"
        )
    ]
    for ph in phrases:
        q = engine.execute(
            "SELECT query_id, start_date, end_date, total FROM fulltext_query WHERE phrase = ? "
            "AND forms LIKE '10-K%' ORDER BY end_date DESC, start_date DESC, fetched_at DESC "
            "LIMIT 1", (ph,)).fetchone()  # fmt: skip
        if q is None:
            out.append(f"  {ph}: no stored query")
            continue
        hits = engine.execute("SELECT cik, sics FROM fulltext_hit WHERE query_id = ? AND cik "
                              "IS NOT NULL", (q[0],)).fetchall()  # fmt: skip
        pairs = [(h[0], (json.loads(h[1] or "[]") or [None])[0]) for h in hits]
        s = industries.spread(pairs)
        verdict = {True: "GENERIC", False: "concentrated", None: "no SIC"}[s.generic]
        top = "; ".join(f"{g} {n}" for g, n in s.groups[:3])
        t1 = "—" if s.top1_share is None else f"{s.top1_share:.0%}"
        t2 = "—" if s.top2_share is None else f"{s.top2_share:.0%}"
        out.append(f"  {ph:<38} {q[1]}..{q[2]} docs {q[3]:>5} · cos {s.operating:>4} "
                   f"(+{s.blank_check} blank, {s.unknown} no SIC) top1 {t1:>4} top2 {t2:>4} "
                   f"{verdict:<12} [{top}]")  # fmt: skip
    return out


def check_ff12() -> list[str]:
    out = ["\n== Siccodes12 vs engine/themes/industries.py =="]
    try:
        req = urllib.request.Request(SICCODES, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        zf = zipfile.ZipFile(io.BytesIO(raw))
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    except Exception as exc:
        return out + [f"  could not read {SICCODES}: {type(exc).__name__}: {exc}"]
    theirs: dict[int, list[tuple[int, int]]] = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+([A-Za-z]+)\s", line)
        r = re.match(r"\s*(\d{4})-(\d{4})", line)
        if r and cur is not None:
            theirs[cur].append((int(r.group(1)), int(r.group(2))))
        elif m:
            cur = int(m.group(1))
            theirs.setdefault(cur, [])
    ours = {n: list(rngs) for n, _, _, rngs in industries.FF12}
    bad = [n for n in sorted(set(theirs) | set(ours)) if n != 12 and
           sorted(theirs.get(n, [])) != sorted(ours.get(n, []))]  # fmt: skip
    out.append(f"  file {len(raw)} bytes, groups {sorted(theirs)}")
    if not bad:
        out.append("  all 11 groups match")
    for n in bad:
        out.append(f"  group {n} differs: file {theirs.get(n)} · ours {ours.get(n)}")
    return out


def sec_checks(engine, corpus, top: list[str], latest, prior) -> list[str]:
    from engine.sec.client import SecClient, iso, user_agent_from_env
    from engine.sec.frames import fetch_frame
    from engine.sec.fulltext import search_page
    from engine.sec.results import Ok
    from engine.store.http import SqliteCache, SqliteFetchLog
    from engine.themes.breadth import count_phrase
    from engine.themes.universe import filers

    client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus), log=SqliteFetchLog(engine))
    now = datetime.now(UTC)
    out = ["\n== Crowding: fund registrations (page 1) =="]
    for ph in ("artificial intelligence", "quantum computing"):
        for forms in (("N-1A", "485APOS"), ("485BPOS",)):
            res = search_page(client, ph, forms=forms, start=latest[0], end=latest[1],
                              allow_fallback=False)  # fmt: skip
            if not isinstance(res, Ok):
                out.append(f"  {ph} {forms}: {res}")
                continue
            pg = res.data
            fm = Counter(h.form for h in pg.hits)
            names = list(dict.fromkeys(h.entity_name for h in pg.hits if h.entity_name))[:5]
            cap = " (capped)" if pg.capped else ""
            out.append(f"  {ph} {','.join(forms)}: {pg.total} docs{cap}"
                       f", {len(pg.entities)} entity buckets (+{pg.entities_other} other); forms "
                       f"{dict(fm)}; e.g. {names}")  # fmt: skip

    out.append("\n== Public float frames (dei:EntityPublicFloat) ==")
    seen: dict[str, float] = {}
    for q in (1, 2, 3, 4):
        period = f"CY2025Q{q}I"
        res = fetch_frame(client, engine, "dei", "EntityPublicFloat", "USD", period, now)
        out.append(f"  {period}: {res if not isinstance(res, Ok) else f'{res.data} values'}")
        for r in engine.execute("SELECT cik, value FROM frame_value WHERE taxonomy = 'dei' AND "
                                "tag = 'EntityPublicFloat' AND frame = ?", (period,)):  # fmt: skip
            seen[r[0]] = float(r[1])
    if seen:
        vals = sorted(seen.values())
        k10 = set(r[0] for r in engine.execute(
            "SELECT DISTINCT cik FROM form_filing WHERE family = '10-K' AND filed >= ?",
            ((date.today() - timedelta(days=365)).isoformat(),)))  # fmt: skip
        out.append(f"  distinct companies {len(seen):,}; 10-K filers last 12 months {len(k10):,}; "
                   f"covered {len(k10 & set(seen)):,}")  # fmt: skip
        nano = sum(0 < v < 5e7 for v in vals)
        out.append(f"  zero {sum(v == 0 for v in vals):,} · < $50M {nano:,}"
                   f" · < $250M {sum(0 < v < 2.5e8 for v in vals):,} · median "
                   f"${vals[len(vals) // 2] / 1e6:,.0f}M")  # fmt: skip

    out.append("\n== Screen: page 1 of the top mined phrases, 10-K family ==")
    t0 = time.monotonic()
    sent0 = engine.execute("SELECT count(*) FROM fetch_log WHERE from_cache = 0").fetchone()[0]
    for ph in top:
        cs = []
        for s, e in (latest, prior):
            c, _, _ = count_phrase(client, engine, ph, "10-K", s, e, now, max_pages=1)
            cs.append(c)
        f1, f0 = filers(engine, "10-K", *latest), filers(engine, "10-K", *prior)
        p = f1 / (f1 + f0) if f1 and f0 else 0.5
        n1, n0 = cs[0].companies, cs[1].companies
        pv = "—" if n1 is None or n0 is None else f"{p_rise(n1, n0, p):.3f}"
        out.append(f"  {ph:<40} latest {_cell(cs[0]):>6} prior {_cell(cs[1]):>6} docs "
                   f"{cs[0].documents}/{cs[1].documents}  p={pv} (p0 {p:.3f})")  # fmt: skip
    sent = engine.execute("SELECT count(*) FROM fetch_log WHERE from_cache = 0").fetchone()[0]
    out.append(f"  {len(top)} phrases: {sent - sent0} requests sent, {time.monotonic() - t0:.0f} s")
    total = engine.execute("SELECT count(*) FROM fetch_log WHERE at >= ? AND from_cache = 0",
                           (iso(now),)).fetchone()[0]  # fmt: skip
    out.append(f"\nSEC requests sent by this probe: {total}")
    return out


def _cell(c) -> str:
    return "fail" if c.companies is None else f"{'≥' if c.lower_bound else ''}{c.companies}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-sec", action="store_true", help="local checks only")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if (ROOT / "data" / "refresh.lock").exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 1
    import os

    os.chdir(ROOT)
    engine = open_db("engine", ROOT / "data")
    corpus = open_db("corpus", ROOT / "data")
    today = date.today()
    latest = ((today - timedelta(days=364)).isoformat(), today.isoformat())
    p_end = today - timedelta(days=365)
    prior = ((p_end - timedelta(days=364)).isoformat(), p_end.isoformat())
    lines = [f"probe_seasonal {datetime.now(UTC):%Y-%m-%d %H:%M} UTC"]
    docs = mining.corpus_docs(engine, corpus)
    lines += composition(docs, [("latest", *latest), ("prior", *prior)])
    watch = {r[0] for r in engine.execute("SELECT cik FROM tier_member WHERE status = 'active'")}
    watch |= {r[0] for r in engine.execute("SELECT DISTINCT cik FROM filing")}
    mlines, top = mine(engine, corpus, docs, latest, prior, watch)
    lines += mlines
    lines += spread_check(engine)
    if not args.no_sec:
        lines += check_ff12()
        lines += sec_checks(engine, corpus, top, latest, prior)

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"probe_seasonal_{datetime.now():%Y%m%d-%H%M%S}.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nlog written to: {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
