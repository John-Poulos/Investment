"""M02 part 6: seasonal pass — seasons, rise test, mining, twins, screen/test/propose,
candidates and flags, Gemini use case 4 checks (D-M02-8, -10, -14, -15, -49…52)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from engine import review
from engine.llm import theme_names
from engine.sec.documents import ARCHIVES, IndexDoc, store_document
from engine.sec.fulltext import EFTS_URL
from engine.sec.identity import SUBMISSIONS_URL
from engine.themes import candidates, flags, industries, mining, seasonal, twins
from engine.themes.mining import Mined, MineResult
from engine.themes.proposals import KIND_LABELS
from tests.conftest import FakeTransport, ok

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
S = seasonal.season_for_key("2026-08")  # 10-Q family, 2026-01-01..2026-08-19


# --- helpers -------------------------------------------------------------------------------


def filing(engine, cik, acc, form, filed, items=None, report=None):
    engine.execute(
        "INSERT INTO filing (accession, cik, form, filed, items, report_date, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", (acc, cik, form, filed, items, report, filed))  # fmt: skip
    engine.execute("INSERT INTO filing_cik (accession, cik) VALUES (?, ?)", (acc, cik))


def doc(corpus, cik, acc, form, text, name="d.htm"):
    url = f"{ARCHIVES}/{int(cik)}/{acc.replace('-', '')}/{name}"
    d = IndexDoc(None, None, name, url, form, None, False)
    return store_document(corpus, cik, acc, d, text.encode(), NOW).doc_id


def ten_k(body):
    return (f"PART I\nItem 1. Business\n{body}\nItem 1A. Risk Factors\nRisks apply.\n"
            "PART II\nItem 7. Management's Discussion\nResults were fine.\n"
            "Item 8. Financial Statements\nTables.\n")  # fmt: skip


def hit(cik, i, form="10-Q", sic="3674", filename=None):
    return {"_id": f"{cik}-26-{i:06d}:{filename or f'q{i}.htm'}",
            "_source": {"ciks": [cik], "display_names": [f"CO {cik}  (CIK {cik})"], "form": form,
                        "file_date": "2026-05-10", "adsh": f"{cik}-26-{i:06d}",
                        "sics": [sic] if sic else []}}  # fmt: skip


def efts(total, hits, relation="eq"):
    return ok(json.dumps({"hits": {"total": {"value": total, "relation": relation},
                                   "hits": hits}}).encode())  # fmt: skip


class Efts(FakeTransport):
    """EFTS answers keyed by (phrase, forms, startdt, from); a missing key = no hits."""

    def __init__(self, answers, routes=None):
        super().__init__(routes or {})
        self.answers = answers

    def __call__(self, url, params, headers):
        if url != EFTS_URL:
            return super().__call__(url, params, headers)
        self.calls.append((url, dict(params), dict(headers)))
        key = (
            params["q"].strip('"'),
            params["forms"],
            params["startdt"],
            int(params.get("from", 0)),
        )
        return self.answers.get(key, efts(0, []))


Q = "10-Q,10-QT,10-QSB"
FUNDS = "N-1A,485APOS"


def ciks(n, start=1):
    return [f"{i:010d}" for i in range(start, start + n)]


# --- seasons and the rise test -------------------------------------------------------------


def test_season_keys_windows_and_reminder(dbs):
    engine, _ = dbs
    assert seasonal.latest_season(date(2026, 10, 11)).key == "2026-08"
    assert seasonal.latest_season(date(2026, 4, 14)).key == "2025-11"
    may = seasonal.season_for_key("2027-05")
    assert may.family == "10-K" and may.latest == ("2027-01-01", "2027-05-20")
    assert may.prior == ("2026-01-01", "2026-05-20")
    assert S.family == "10-Q" and S.day == date(2026, 8, 19)
    assert "2026-08" in seasonal.reminder(engine, date(2026, 10, 11))
    seasonal.ensure_run(engine, S, NOW)
    assert "mined" in seasonal.reminder(engine, date(2026, 10, 11))
    seasonal.set_status(engine, S.key, "done", NOW)
    assert seasonal.reminder(engine, date(2026, 10, 11)) is None
    assert "2026-11" in seasonal.reminder(engine, date(2026, 11, 20))


def test_rise_test_matches_d_m02_49_examples_and_weights_filers():
    for n0, n1 in [(0, 5), (1, 6), (2, 7), (3, 9)]:
        assert seasonal.p_rise(n1, n0) <= seasonal.P_MAX
    for n0, n1 in [(2, 5), (3, 8)]:
        assert seasonal.p_rise(n1, n0) > seasonal.P_MAX
    # more filers this year: the same raw rise is less surprising (D-M02-52 (2))
    assert seasonal.p_rise(8, 4, 0.6) > seasonal.p_rise(8, 4, 0.5)
    assert seasonal.p_rise(0, 0) == 1.0


# --- mining and twins ----------------------------------------------------------------------


def test_mining_compares_each_company_with_its_year_ago_documents(dbs):
    engine, corpus = dbs
    a, b, c = "0000000011", "0000000022", "0000000033"
    for cik, now_text in [(a, "We sell memory and co-packaged optics. Liquid cooling grows."),
                          (b, "Our co-packaged optics ramp. We sell switches.")]:  # fmt: skip
        filing(engine, cik, f"{cik}-25-1", "10-K", "2025-02-10")
        filing(engine, cik, f"{cik}-26-1", "10-K", "2026-02-10")
        doc(corpus, cik, f"{cik}-25-1", "10-K", ten_k("We sell memory and switches."))
        doc(corpus, cik, f"{cik}-26-1", "10-K", ten_k(now_text))
    filing(engine, c, f"{c}-26-1", "10-K", "2026-02-10")  # no twin: not compared
    doc(corpus, c, f"{c}-26-1", "10-K", ten_k("We sell co-packaged optics too."))
    res = mining.mine(engine, corpus, [a, b, c], S.day)
    assert set(res.compared) == {a, b} and "no kind in both periods" in res.not_compared[c]
    top = {m.phrase: m for m in res.candidates}
    assert top["co-packaged optics"].adopters == (a, b)
    assert "sell memory" not in top and "risks apply" not in top  # in both periods: cancels
    assert "liquid cooling" not in top  # one adopter only
    assert res.candidates[0].phrase == "co-packaged optics"  # ties: two-word phrases first
    excl = mining.mine(engine, corpus, [a, b], S.day, exclude={"co-packaged optics"})
    assert "co-packaged optics" not in {m.phrase for m in excl.candidates}


def test_phrases_break_at_numbers_and_skip_stop_word_edges():
    got = mining.phrases_in("HBM3E supply grew 20% in fiscal 2026; the internet of things.")
    assert "hbm3e supply" in got and "internet of things" in got
    assert not any(p.startswith(("the ", "of ")) for p in got)
    assert "supply grew" in got and "grew in" not in got


def test_call_transcripts_compare_management_turns_only():
    assert mining.doc_kind(None, None, None, True) == "call"
    assert mining.doc_kind("EX-99.1", "8-K", "2.02,9.01", False) == "release"
    assert mining.doc_kind("EX-99.1", "8-K", "7.01", False) is None
    assert mining.doc_kind("10-K", "10-K/A", None, False) is None  # amendments not mined
    assert "call analyst" in mining.SKIP_SECTIONS


def test_twins_find_same_kind_a_year_earlier(dbs):
    engine, corpus = dbs
    cik = "0000000044"
    filing(engine, cik, "k26", "10-K", "2026-02-20")
    filing(engine, cik, "k25", "10-K", "2025-02-21")
    filing(engine, cik, "q26", "10-Q", "2026-05-01", report="2026-03-31")
    filing(engine, cik, "q25a", "10-Q", "2025-05-02", report="2025-03-31")
    filing(engine, cik, "q25b", "10-Q", "2025-08-01", report="2025-06-30")
    filing(engine, cik, "r26", "8-K", "2026-04-30", items="2.02,9.01")
    filing(engine, cik, "r25", "8-K", "2025-05-01", items="2.02,9.01")
    filing(engine, cik, "o25", "8-K", "2025-04-29", items="5.07")
    for acc, form in [("k26", "10-K"), ("q26", "10-Q")]:
        doc(corpus, cik, acc, form, ten_k("x") if form == "10-K" else "Item 2. y")
    doc(corpus, cik, "r26", "EX-99.1", "Results.", name="ex99.htm")
    todo, missing = twins.plan(engine, corpus, [cik], S.day)
    assert sorted(f.accession for f in todo) == ["k25", "q25a", "r25"] and not missing


# --- screen, test, propose -----------------------------------------------------------------


def _theme(engine, key, phrases, status="active"):
    tid = engine.execute(
        "INSERT INTO theme (key, name, source, status, discovered_at, "
        "updated_at) VALUES (?, ?, 'seed', ?, ?, ?)",
        (key, key.title(), status, "2026-10-01", "2026-10-01"),
    ).lastrowid
    for p in phrases:
        engine.execute("INSERT INTO theme_phrase (theme_id, phrase, source, status, "
                       "discovered_at, updated_at) VALUES (?, ?, 'seed', 'active', ?, ?)",
                       (tid, f'"{p}"', "2026-10-01", "2026-10-01"))  # fmt: skip
    return tid


def _mined(phrases):
    r = MineResult(("", ""), ("", ""))
    r.candidates = [Mined(p, ("0000000011", "0000000022"), 0, 2) for p in phrases]
    return r


def _answers(spec):
    """phrase → (latest ciks, prior ciks[, fund latest, fund prior]) → EFTS answers."""
    out = {}
    for ph, v in spec.items():
        lat, pri = v[0], v[1]
        for window, cs in ((S.latest[0], lat), (S.prior[0], pri)):
            out[(ph, Q, window, 0)] = efts(len(cs), [hit(c, i) for i, c in enumerate(cs)])
        if len(v) > 2:
            out[(ph, FUNDS, S.latest[0], 0)] = efts(v[2], [])
            out[(ph, FUNDS, S.prior[0], 0)] = efts(v[3], [])
    return out


def test_screen_test_and_propose_one_pass(make_client, dbs):
    engine, corpus = dbs
    optics = _theme(engine, "optics", ["silicon photonics"])
    nvda = "0000001045"
    engine.execute("INSERT INTO entity (cik, name, sic, source_ref, fetched_at) VALUES "
                   "(?, 'NVIDIA CORP', '3674', 'x', 'x')", (nvda,))  # fmt: skip
    filing(engine, nvda, "n1", "10-K", "2026-02-25")
    doc(
        corpus,
        nvda,
        "n1",
        "10-K",
        ten_k("Co-packaged optics and silicon photonics cut power.").replace(
            "Results were fine.", "Immersion tanks help."
        ),
    )  # other section: no overlap
    t = Efts(_answers({
        "co-packaged optics": (ciks(8), ciks(1), 12, 2),
        "cash flow": (ciks(100), ciks(100)),
        "immersion tanks": (ciks(7, 50), [], 0, 0),
        "rare words": (ciks(3), []),
    }) | {("cash flow", Q, S.latest[0], 0): efts(4000, [hit(c, i) for i, c in enumerate(ciks(100))],
                                                 "gte"),
          ("cash flow", Q, S.prior[0], 0): efts(4100, [hit(c, i) for i, c in enumerate(ciks(100))],
                                                "gte")})  # fmt: skip
    client = make_client(t)
    seasonal.ensure_run(engine, S, NOW)
    seasonal.store_mined(engine, S, _mined(["co-packaged optics", "cash flow",
                                            "immersion tanks", "rare words"]), NOW)  # fmt: skip
    budget = seasonal.Budget()
    assert seasonal.screen(client, engine, S, NOW, budget) == 4
    stage = dict(engine.execute("SELECT phrase, stage FROM seasonal_phrase").fetchall())
    assert stage == {"co-packaged optics": "screened", "immersion tanks": "screened",
                     "cash flow": "screened_out", "rare words": "screened_out"}  # fmt: skip
    why = dict(engine.execute("SELECT phrase, reason FROM seasonal_phrase").fetchall())
    assert "documents" in why["cash flow"] and "fewer than 5" in why["rare words"]
    assert seasonal.test(client, engine, corpus, S, NOW, budget) == 2
    row = engine.execute("SELECT * FROM seasonal_phrase WHERE phrase = 'co-packaged optics'"
                         ).fetchone()  # fmt: skip
    assert row["stage"] == "passed" and row["theme_id"] == optics and row["overlap"] == 1.0
    crowd = json.loads(row["crowding"])
    assert (crowd["prior"], crowd["latest"], crowd["flag"]) == (2, 12, True)
    sp = json.loads(row["spread"])
    assert sp["groups"][0][0].startswith("business equipment") and sp["operating"] == 8
    assert json.loads(row["samples"])[0]["name"] == "NVIDIA CORP"
    # a resumed run re-uses stored counts: no new EFTS requests
    sent = len(t.calls)
    seasonal.count(client, engine, S, "co-packaged optics", "10-Q", S.latest, 10, NOW)
    assert len(t.calls) == sent

    out = seasonal.propose_pass(engine, S, NOW, {"0000000011": "AAA"})
    assert out["proposed"] == 2
    items = {r["kind"]: r for r in engine.execute("SELECT * FROM review_queue")}
    phrase_item = json.loads(items["m02_phrase"]["payload"])
    assert phrase_item["theme_key"] == "optics" and phrase_item["adopters"][0] == "AAA"
    assert phrase_item["phrase_id"] and phrase_item["grade"] == "A"
    theme_item = items["m02_theme"]
    p = json.loads(theme_item["payload"])
    assert p["new_theme"] and p["theme_key"] == "mined-immersion-tanks"
    assert engine.execute("SELECT status FROM theme WHERE key = 'mined-immersion-tanks'"
                          ).fetchone()[0] == "proposed"  # fmt: skip
    review.m02_action(engine, theme_item["item_id"], "accept", "", "owner", NOW)
    assert engine.execute("SELECT status FROM theme WHERE key = 'mined-immersion-tanks'"
                          ).fetchone()[0] == "active"  # fmt: skip
    assert engine.execute("SELECT status FROM theme_phrase WHERE phrase = '\"immersion tanks\"'"
                          ).fetchone()[0] == "active"  # fmt: skip


def test_pass_proposes_at_most_ten_and_longer_phrase_covers(make_client, dbs):
    engine, corpus = dbs
    spec = {f"theme words {chr(97 + i)}": (ciks(6 + i), []) for i in range(11)}
    spec["bandwidth memory"] = (ciks(10, 200), [])
    spec["high bandwidth memory"] = (ciks(10, 200), [])
    client = make_client(Efts(_answers(spec)))
    seasonal.ensure_run(engine, S, NOW)
    seasonal.store_mined(engine, S, _mined(list(spec)), NOW)
    budget = seasonal.Budget()
    seasonal.screen(client, engine, S, NOW, budget)
    seasonal.test(client, engine, corpus, S, NOW, budget)
    out = seasonal.propose_pass(engine, S, NOW)
    assert out["proposed"] == seasonal.PROPOSE_CAP and out["listed"] == 3
    reason = engine.execute("SELECT reason FROM seasonal_phrase WHERE phrase = 'bandwidth memory'"
                            ).fetchone()[0]  # fmt: skip
    assert reason == 'covered by "high bandwidth memory"'
    # weekly cap: the 11th+ M02 item waits; the pass cap keeps it to 10 anyway
    assert engine.execute("SELECT count(*) FROM review_queue").fetchone()[0] == 10


# --- candidates and flags ------------------------------------------------------------------


def test_float_frames_and_size_labels(dbs):
    engine, _ = dbs
    assert flags.float_frames(date(2026, 10, 11), 3) == ["CY2026Q3I", "CY2026Q2I", "CY2026Q1I"]
    assert flags.float_frames(date(2026, 2, 1), 2) == ["CY2025Q4I", "CY2025Q3I"]
    for cik, v in [
        ("0000000001", 0),
        ("0000000002", 3e7),
        ("0000000003", 2e8),
        ("0000000004", 5e9),
    ]:
        engine.execute(
            "INSERT INTO frame_value (taxonomy, tag, unit, frame, cik, value, accession, "
            "period_end, fetched_at) VALUES ('dei', 'EntityPublicFloat', 'USD', "
            "'CY2026Q2I', ?, ?, 'a', '2026-06-30', 'x')",
            (cik, v),
        )
    labels = [flags.size_of(engine, f"{i:010d}").label for i in range(1, 6)]
    assert labels[0].startswith("no public float") and labels[1].startswith("nano")
    assert labels[2].startswith("micro") and labels[3] == "float $5.00B"
    assert labels[4] == "size unknown"


def test_submission_flags_around_first_mention():
    data = {"formerNames": [{"name": "OLD MINING CO", "from": "2019-01-01", "to": "2026-03-01"}],
            "filings": {"recent": {
                "accessionNumber": ["a1", "a2", "a3", "a4"],
                "filingDate": ["2026-04-01", "2026-03-15", "2025-01-01", "2026-02-10"],
                "form": ["S-3", "8-K", "S-1", "8-K"],
                "items": ["", "2.01,5.01", "", "5.06"]}}}  # fmt: skip
    got = flags.submission_flags(data, "0000000077", date(2026, 3, 20))
    assert got[0] == "renamed 2026-03-01 (was OLD MINING CO)"
    assert got[1] == "share offering: S-3 2026-04-01"  # the 2025 S-1 is too far away
    assert "reverse-merger signs: 8-K 2026-03-15 (Items 2.01 + 5.01)" in got
    assert "shell status change: 8-K 2026-02-10 (Item 5.06)" in got


def test_mentions_section_and_quantified_rule(dbs):
    engine, corpus = dbs
    text = ("PART I\nItem 1. Financial Statements\nTables.\n"
            "Item 2. Management's Discussion\nCo-packaged optics revenue was $12 million.\n"
            "PART II\nItem 1A. Risk Factors\nCo-packaged optics may not succeed.\n")  # fmt: skip
    d = doc(corpus, "0000000077", "x1", "10-Q", text)
    ms = candidates.mentions(corpus, d, ['"co-packaged optics"'])
    assert [(m.section, m.substantive) for m in ms] == [
        ("10-Q Part I Item 2", True),
        ("10-Q Part II Item 1A", False),
    ]


def test_candidates_read_hits_flag_and_propose(make_client, dbs):
    engine, corpus = dbs
    tid = _theme(engine, "optics", ["co-packaged optics"])
    x, y, core = "0000000077", "0000000088", "0000001045"
    q10 = ("PART I\nItem 1. Financial Statements\nTables.\nItem 2. Management's Discussion\n"
           "Our co-packaged optics orders reached $12 million.\n")  # fmt: skip
    risk = (
        "PART I\nItem 1. Financial Statements\nTables.\nItem 2. Management's Discussion\n"
        "Fine.\nPART II\nItem 1A. Risk Factors\nCo-packaged optics may not succeed.\n"
    )
    hits = [hit(x, 1, filename="x.htm"), hit(y, 2, filename="y.htm"),
            hit(core, 3), hit("0000000099", 4, sic="6770")]  # fmt: skip
    subs = {"formerNames": [{"name": "OLD CO", "to": "2026-04-01"}],
            "filings": {"recent": {"accessionNumber": ["s1"], "filingDate": ["2026-05-01"],
                                   "form": ["S-1"], "items": [""]}}}  # fmt: skip
    frame = {"data": [{"cik": 77, "val": 30_000_000, "accn": "f1", "end": "2026-06-30",
                       "entityName": "X"}]}  # fmt: skip
    frames = {f"https://data.sec.gov/api/xbrl/frames/dei/EntityPublicFloat/USD/{p}.json":
              [ok(json.dumps(frame).encode()) if p == "CY2026Q2I" else ok(b"", status=404)]
              for p in flags.float_frames(NOW.date())}  # fmt: skip
    routes = frames | {
        f"{ARCHIVES}/77/{x}26000001/x.htm": [ok(q10.encode())],
        f"{ARCHIVES}/88/{y}26000002/y.htm": [ok(risk.encode())],
        SUBMISSIONS_URL.format(cik=x): [ok(json.dumps(subs).encode())],
        SUBMISSIONS_URL.format(cik=y): [ok(json.dumps({"filings": {"recent": {}}}).encode())],
    }  # fmt: skip
    t = Efts({("co-packaged optics", Q, S.latest[0], 0): efts(4, hits)}, routes)
    rep = candidates.run_candidates(make_client(t), engine, corpus, S, {core}, NOW, lambda: False)
    assert (rep.phrases_counted, rep.companies_seen, rep.read) == (1, 2, 2)
    assert (rep.candidates, rep.watch) == (1, 1)
    rows = {r["cik"]: r for r in engine.execute("SELECT * FROM seasonal_company")}
    assert rows[x]["tier"] == "candidate" and rows[x]["section"] == "10-Q Part I Item 2"
    fl = json.loads(rows[x]["flags"])
    assert fl[0].startswith("renamed 2026-04-01") and fl[1].startswith("share offering: S-1")
    assert fl[-1].startswith("nano: float $30.0M")
    assert rows[y]["tier"] == "watch" and json.loads(rows[y]["flags"]) == []  # size unknown
    item = engine.execute("SELECT * FROM review_queue WHERE kind = 'm02_candidate'").fetchone()
    p = json.loads(item["payload"])
    assert item["cik"] == x and p["theme_key"] == "optics" and p["quantified"]
    assert p["first_note"] == "first mention this season" and rows[x]["theme_id"] == tid


# --- Gemini use case 4 checks and spread ---------------------------------------------------


def test_gemini_variants_need_verbatim_quotes(dbs):
    engine, corpus = dbs
    passages = {"S1": {"body": "We ship co-packaged optics (CPO) and linear pluggable optics "
                               "to hyperscalers.", "start_offset": 0, "accession": "a",
                       "filename": "f", "sha256": "s"}}  # fmt: skip
    check = theme_names._check("co-packaged optics", passages)
    obs = check({"name": "co-packaged optics", "variants": [
        {"phrase": "linear pluggable optics", "passage": "S1",
         "quote": "We ship co-packaged optics (CPO) and linear pluggable optics to hyperscalers."},
        {"phrase": "optical engines", "passage": "S1", "quote": "We ship optical engines."},
        {"phrase": "co-packaged optics", "passage": "S1", "quote": "x"}]})  # fmt: skip
    assert [(o.claim, o.verified) for o in obs] == [
        ("co-packaged optics", True), ("linear pluggable optics", True),
        ("optical engines", False), ("co-packaged optics", False)]  # fmt: skip


def test_spread_counts_finance_apart():
    sp = industries.spread([("1", "3674"), ("2", "7372"), ("3", "6798"), ("4", "6770"),
                            ("5", None), ("6", "4813")])  # fmt: skip
    assert (sp.operating, sp.blank_check, sp.finance, sp.unknown) == (5, 1, 1, 1)
    assert sp.groups[0] == ("business equipment (chips, computers, software)", 2)
    assert sp.top1_share == 2 / 3 and sp.to_json()["generic_d49"] is False


def test_new_review_kinds_are_known():
    assert {"m02_phrase", "m02_theme", "m02_candidate"} <= set(KIND_LABELS)
