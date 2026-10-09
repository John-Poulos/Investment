"""M02 theme core: seeds, form-index denominators, breadth (D-M02-1, -14, -16)."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

from engine.sec.fulltext import EFTS_URL, parse_entities
from engine.themes.breadth import (
    THEME_ROW,
    breadth_rows,
    breadth_windows,
    compute_theme,
    count_phrase,
    year_back,
)
from engine.themes.seeds import active_phrases, active_themes, load_seeds, sync_seeds
from engine.themes.universe import (
    INDEX_URL,
    ensure_quarters,
    family_of,
    filers,
    parse_form_index,
    quarters_between,
)
from tests.conftest import FIXTURES, FakeTransport, ok

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)

# --- seeds -------------------------------------------------------------------------


def test_repo_seed_file_loads_cleanly():
    themes, problems = load_seeds(ROOT / "config" / "themes.toml")
    assert problems == []
    assert len(themes) == 8
    hbm = next(t for t in themes if t.key == "hbm_packaging")
    assert '"high bandwidth memory"' in hbm.phrases and '"HBM"' in hbm.phrases
    assert hbm.companies == ("MU", "INTC", "GFS")


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "themes.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_bad_entries_are_reported_not_stored(tmp_path):
    path = _write(
        tmp_path,
        """
[[theme]]
key = "Bad Key"
name = "x"
[[theme]]
key = "ok"
name = "OK"
phrases = ["good phrase", "a OR b", "x:y"]
[[theme]]
key = "ok"
name = "dup"
""",
    )
    themes, problems = load_seeds(path)
    assert [t.key for t in themes] == ["ok"]
    assert themes[0].phrases == ('"good phrase"',)
    assert len(problems) == 4  # bad key, two bad phrases, duplicate


def test_sync_is_idempotent_and_archives_removed(tmp_path, dbs):
    engine, _ = dbs
    path = _write(
        tmp_path,
        """
[[theme]]
key = "q"
name = "Quantum"
phrases = ["qubit", "quantum computing"]
companies = ["infq"]
""",
    )
    r1 = sync_seeds(engine, path, NOW)
    assert r1.themes_added == ["q"] and len(r1.phrases_added) == 2
    assert r1.companies_added == ["q: INFQ"]
    r2 = sync_seeds(engine, path, NOW)
    assert not (r2.themes_added or r2.phrases_added or r2.phrases_archived)

    _write(
        tmp_path,
        """
[[theme]]
key = "q"
name = "Quantum computing"
phrases = ["qubit"]
""",
    )
    r3 = sync_seeds(engine, path, NOW)
    assert r3.phrases_archived == ['q: "quantum computing"']
    assert r3.companies_archived == ["q: INFQ"]
    theme = active_themes(engine)[0]
    assert theme["name"] == "Quantum computing"
    assert active_phrases(engine, theme["theme_id"]) == ['"qubit"']
    # archived, not deleted: discovery date kept
    row = engine.execute("SELECT status, discovered_at FROM theme_phrase WHERE phrase = ?",
                         ('"quantum computing"',)).fetchone()  # fmt: skip
    assert row["status"] == "archived" and row["discovered_at"]

    _write(tmp_path, "")
    r4 = sync_seeds(engine, path, NOW)
    assert r4.themes_archived == ["q"] and active_themes(engine) == []


# --- form index (denominator) ------------------------------------------------------

FORM_IDX = (FIXTURES / "sec" / "form_idx_sample.idx").read_text(encoding="latin-1")


def test_parse_form_index_keeps_tracked_families():
    rows = parse_form_index(FORM_IDX)
    assert {(r.family, r.form, r.cik) for r in rows} == {
        ("10-K", "10-K", "0000723125"),
        ("10-K", "10-K/A", "0000001111"),
        ("10-K", "10-K", "0000002222"),
        ("10-K", "10-K", "0000003333"),
        ("10-Q", "10-Q", "0000723125"),
    }
    assert rows[0].accession == "0000723125-25-000001" and rows[0].filed == "2025-02-10"
    assert family_of("10-KT/A") == "10-K" and family_of("SC 13D") is None


def test_quarters_between():
    got = quarters_between(date(2024, 11, 1), date(2025, 4, 2))
    assert got == [(2024, 4), (2025, 1), (2025, 2)]


def test_ensure_quarters_gz_then_idx_and_filers(make_client, dbs):
    engine, _ = dbs
    gz_url = INDEX_URL.format(year=2025, quarter=1, name="form.gz")
    t = FakeTransport({
        gz_url: [ok(gzip.compress(FORM_IDX.encode("latin-1")))],
        INDEX_URL.format(year=2025, quarter=2, name="form.gz"): [ok(b"", status=404)],
        INDEX_URL.format(year=2025, quarter=2, name="form.idx"): [ok(FORM_IDX.encode())],
    })  # fmt: skip
    client = make_client(t)
    res = ensure_quarters(client, engine, [(2025, 1), (2025, 2)], NOW)
    assert [(r.status, r.rows) for r in res] == [("fetched", 5), ("fetched", 5)]
    # Closed quarters are not fetched again.
    assert [r.status for r in ensure_quarters(client, engine, [(2025, 1)], NOW)] == ["stored"]
    assert filers(engine, "10-K", "2025-01-01", "2025-03-31") == 4  # co-registrants count
    assert filers(engine, "10-Q", "2025-01-01", "2025-03-31") == 1
    # A window touching an unstored quarter is missing, not zero.
    assert filers(engine, "10-K", "2024-12-01", "2025-03-31") is None


# --- EFTS entity summary and breadth -------------------------------------------------


def test_parse_entities():
    data = {"aggregations": {"entity_filter": {
        "buckets": [{"key": "MICRON TECHNOLOGY INC  (MU)  (CIK 0000723125)", "doc_count": 3},
                    {"key": "NO CIK NAME", "doc_count": 1}],
        "sum_other_doc_count": 7}}}  # fmt: skip
    assert parse_entities(data) == (("0000723125", "NO CIK NAME"), 7)
    assert parse_entities({}) == ((), None)


def efts(total, ciks, relation="eq", buckets=()):
    hits = [{"_id": f"0000{c}-25-00000{i}:doc{i}.htm",
             "_source": {"ciks": [c], "display_names": [f"CO {c}  (CIK {c})"], "form": "10-K",
                         "file_date": "2025-02-10", "adsh": f"0000{c}-25-00000{i}", "sics": []}}
            for i, c in enumerate(ciks)]  # fmt: skip
    body = {"hits": {"total": {"value": total, "relation": relation}, "hits": hits},
            "aggregations": {"entity_filter": {"buckets": [{"key": f"X (CIK {b})"}
                                                           for b in buckets]}}}  # fmt: skip
    return ok(json.dumps(body).encode())


class Efts(FakeTransport):
    """EFTS answers keyed by (phrase, startdt, from); other URLs as FakeTransport."""

    def __init__(self, answers, routes=None):
        super().__init__(routes or {})
        self.answers = answers

    def __call__(self, url, params, headers):
        if url != EFTS_URL:
            return super().__call__(url, params, headers)
        self.calls.append((url, dict(params), dict(headers)))
        key = (params["q"], params["startdt"], int(params.get("from", 0)))
        if key not in self.answers:
            raise AssertionError(f"unexpected EFTS query {key}")
        return self.answers[key]


def test_count_phrase_exact_lower_bound_and_failure(make_client, dbs):
    engine, _ = dbs
    t = Efts({
        ('"hbm"', "2025-01-01", 0): efts(2, ["0000000001", "0000000002"]),
        ('"ai"', "2025-01-01", 0): efts(5000, ["0000000001"] * 1, "gte",
                                        buckets=["0000000001", "0000000009", "0000000008"]),
        ('"ai"', "2025-01-01", 1): efts(5000, [], "gte"),
        ('"bad"', "2025-01-01", 0): ok(b"oops", status=400),
    })  # fmt: skip
    client = make_client(t)
    c, ciks, _ = count_phrase(client, engine, '"hbm"', "10-K", "2025-01-01", "2025-12-31", NOW)
    assert (c.documents, c.filings, c.companies, c.lower_bound) == (2, 2, 2, False)
    assert ciks == {"0000000001", "0000000002"}
    c, _, _ = count_phrase(client, engine, '"ai"', "10-K", "2025-01-01", "2025-12-31", NOW,
                           max_pages=1)  # fmt: skip
    assert c.lower_bound and c.companies == 3  # fetched ∪ entity buckets
    c, _, _ = count_phrase(client, engine, '"bad"', "10-K", "2025-01-01", "2025-12-31", NOW)
    assert c.documents is None and c.companies is None and c.error


def test_compute_theme_union_shares_and_yoy(make_client, dbs):
    engine, _ = dbs
    engine.execute("INSERT INTO theme (key, name, source, status, discovered_at, updated_at) "
                   "VALUES ('t', 'T', 'seed', 'active', 'x', 'x')")  # fmt: skip
    # Denominator: 10 filers in 2024, 20 in 2025 (both quarters' indexes stored as closed).
    for y, n in ((2024, 10), (2025, 20)):
        for q in range(1, 5):
            engine.execute("INSERT INTO form_index VALUES (?, ?, 0, ?, 1, 'x', 'x')",
                           (y, q, f"{y}-12-31"))  # fmt: skip
        engine.executemany("INSERT INTO form_filing VALUES (?, ?, '10-K', '10-K', ?)",
                           [(f"a{y}{i}", f"{i:010d}", f"{y}-03-01") for i in range(n)])  # fmt: skip
    t = Efts({
        ('"a"', "2024-01-01", 0): efts(1, ["0000000001"]),
        ('"b"', "2024-01-01", 0): efts(1, ["0000000001"]),
        ('"a"', "2025-01-01", 0): efts(2, ["0000000001", "0000000002"]),
        ('"b"', "2025-01-01", 0): efts(2, ["0000000003", "0000000004"]),
    })  # fmt: skip
    client = make_client(t)
    windows = [("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")]
    compute_theme(client, engine, 1, "t", ['"a"', '"b"'], "10-K", windows, NOW)
    rows = {(r.phrase, r.start[:4]): r for r in breadth_rows(engine, 1, "10-K")}
    theme25 = rows[(THEME_ROW, "2025")]
    assert theme25.companies == 4 and theme25.filers == 20 and theme25.share == 0.2
    assert rows[(THEME_ROW, "2024")].share == 0.1
    assert round(theme25.change_pts, 6) == 10.0
    assert rows[('"a"', "2025")].companies == 2 and not rows[('"a"', "2025")].lower_bound


def test_windows_compare_like_with_like():
    w = breadth_windows(2023, date(2026, 10, 9))
    assert w == [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
                 ("2025-01-01", "2025-12-31"), ("2025-01-01", "2025-10-09"),
                 ("2026-01-01", "2026-10-09")]  # fmt: skip
    assert year_back(date(2028, 2, 29)) == date(2027, 2, 28)


def test_failed_window_is_split_in_halves(make_client, dbs):
    engine, _ = dbs
    answers = {
        ("2020-01-01", "2020-12-31"): ok(b"err", status=500),
        ("2020-01-01", "2020-07-01"): efts(2, ["0000000001", "0000000002"]),
        ("2020-07-02", "2020-12-31"): efts(1, ["0000000002"]),
    }

    def route(url, params, headers):
        assert url == EFTS_URL
        return answers[(params["startdt"], params["enddt"])]

    client = make_client(route)
    c, ciks, _ = count_phrase(client, engine, '"advanced packaging"', "10-K", "2020-01-01",
                              "2020-12-31", NOW)  # fmt: skip
    assert c.documents == 3 and c.companies == 2 and not c.lower_bound
    assert "two halves" in c.error and ciks == {"0000000001", "0000000002"}
