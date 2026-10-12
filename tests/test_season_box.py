"""D-M02-51: the logon refresh mines a due season, asks Yes/No after releasing the lock, and
runs the pass on Yes; theme-page crowding (D-M02-10)."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from engine.store.db import open_db
from engine.themes import season_pass, seasonal
from engine.themes import views as themes
from tests.test_ui import client  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_refresh", ROOT / "scripts" / "run_refresh.py")
assert spec and spec.loader
run_refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_refresh)

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
S = seasonal.season_for_key("2026-08")
REPORT = SimpleNamespace(watchlist={"NVDA": "NVIDIA CORP (0001045810)", "X": "no cik"})


def _prep(n: int = 120) -> season_pass.Prepared:
    return season_pass.Prepared(S, n, 900, [])


def test_question_states_candidates_requests_and_minutes():
    q = _prep().question()
    assert "Seasonal pass 2026-08 (due 2026-08-19): 120 candidate phrases" in q
    assert "about 900 SEC requests (about 8 min" in q and "Run it now?" in q


def test_core_promoted_from_the_report():
    assert run_refresh.core_promoted(REPORT) == {"0001045810": "NVDA"}


def test_step_mines_only_for_background_runs_not_declined_today(dbs, monkeypatch):
    engine, corpus = dbs
    monkeypatch.setattr(season_pass, "prepare", lambda *a: _prep())
    monkeypatch.setattr(seasonal, "latest_season", lambda today: S)
    text, prep = run_refresh.seasonal_step(engine, corpus, REPORT, background=False)
    assert "Seasonal pass 2026-08" in text and prep is None  # manual: reminder only
    text, prep = run_refresh.seasonal_step(engine, corpus, REPORT, background=True)
    assert prep is not None and "120 candidate phrases mined" in text
    engine.execute("INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
                   "('seasonal_declined', 'owner', 'x', ?)",
                   (f"2026-08:{datetime.now(UTC).date()}",))  # fmt: skip
    assert run_refresh.seasonal_step(engine, corpus, REPORT, background=True)[1] is None


def test_no_is_remembered_and_yes_runs_under_the_lock(tmp_path, dbs, monkeypatch):
    engine, _ = dbs
    shown: list[str] = []
    monkeypatch.setattr(run_refresh, "show_info", lambda title, text: shown.append(text))
    monkeypatch.setattr(run_refresh, "ask_yes_no", lambda title, text: False)
    run_refresh.ask_and_run_season(engine, tmp_path, _prep(), "3 review item(s) open")
    row = engine.execute("SELECT detail FROM refresh_state WHERE name = 'seasonal_declined'"
                         ).fetchone()  # fmt: skip
    assert row[0].startswith("2026-08:") and shown == []
    held: list[bool] = []

    def fake_run(engine_, folder, prep):
        held.append((folder / "refresh.lock").exists())
        return "Seasonal pass 2026-08: season 2026-08 done."

    monkeypatch.setattr(run_refresh, "ask_yes_no", lambda title, text: "3 review" in text)
    monkeypatch.setattr(run_refresh, "run_season", fake_run)
    run_refresh.ask_and_run_season(engine, tmp_path, _prep(), "3 review item(s) open")
    assert held == [True] and not (tmp_path / "refresh.lock").exists()
    assert shown == ["Seasonal pass 2026-08: season 2026-08 done."]


def _crowd(engine) -> int:
    tid = engine.execute("INSERT INTO theme (key, name, source, status, discovered_at, "
                         "updated_at) VALUES ('quantum', 'Quantum computing', 'seed', 'active', "
                         "'x', 'x')").lastrowid  # fmt: skip
    for p in ("quantum computing", "qubit"):
        engine.execute("INSERT INTO theme_phrase (theme_id, phrase, source, status, "
                       "discovered_at, updated_at) VALUES (?, ?, 'seed', 'active', 'x', 'x')",
                       (tid, f'"{p}"'))  # fmt: skip
    seasonal.ensure_run(engine, S, NOW)
    for window, n in ((S.latest, 40), (S.prior, 12)):
        engine.execute("INSERT INTO seasonal_count (season, phrase, family, start_date, "
                       "end_date, max_pages, documents, lower_bound, sics, computed_at) VALUES "
                       "('2026-08', 'quantum computing', 'fund', ?, ?, 1, ?, 0, '{}', 'x')",
                       (*window, n))  # fmt: skip
    return tid


def test_theme_crowding_view(dbs):
    engine, _ = dbs
    tid = _crowd(engine)
    c = themes.theme_crowding(engine, tid)
    assert c["flagged"] == ["quantum computing"]
    assert [r["flag"] for r in c["rows"]] == [True, None]  # qubit not counted yet
    assert themes.crowded_themes(engine) == {"quantum"}


def test_theme_pages_show_crowding(client):  # noqa: F811
    engine = open_db("engine", client.app.state.settings.data_dir)
    _crowd(engine)
    engine.close()
    html = client.get("/themes/quantum").text
    assert "Crowding: new fund registrations" in html and "rose beyond chance" in html
    assert "not counted yet" in html
    assert "crowding" in client.get("/themes").text
