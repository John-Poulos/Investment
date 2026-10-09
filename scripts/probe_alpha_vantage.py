"""Probe Alpha Vantage's EARNINGS_CALL_TRANSCRIPT endpoint (M02 D-M02-6, DS1).

    uv run python scripts/probe_alpha_vantage.py

One-off check before building call-guidance ingestion: does the free key reach the
endpoint, which companies and quarters it covers, whether "quarter" is calendar or
fiscal (Microsoft and Oracle are asked both ways), and whether capex wording appears.
Makes 7 requests, 15 s apart (free tier: 25 per day). Key: ALPHA_VANTAGE_API_KEY in
.env, sent as the query parameter Alpha Vantage requires and never printed.

Writes a summary to logs/probe_av_<YYYYMMDD-HHMMSS>.txt (send it back) and the raw
responses to data/probe/alpha_vantage/ for the build (not committed).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.alphavantage.co/query"
PAIRS = [
    ("AMZN", "2026Q2"),
    ("MSFT", "2026Q2"),  # calendar Q2 = Microsoft FY26 Q4 (call 2026-07-29)
    ("MSFT", "2026Q4"),  # fiscal label for the same call
    ("ORCL", "2026Q3"),  # calendar Q3 = Oracle FY27 Q1 (call 2026-09)
    ("ORCL", "2027Q1"),  # fiscal label for the same call
    ("AAPL", "2026Q3"),
    ("TSLA", "2026Q2"),
]
CAPEX = re.compile(r"capital expenditure|capex|capital spending", re.IGNORECASE)
SPACING_S = 15


def first_sentence_with(text: str, pattern: re.Pattern[str], limit: int = 200) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if pattern.search(sentence):
            return sentence[:limit]
    return ""


def summarize(symbol: str, quarter: str, status: int, data: object) -> list[str]:
    lines = [f"{symbol} {quarter}: HTTP {status}"]
    if not isinstance(data, dict):
        return lines + [f"  not a JSON object: {type(data).__name__}"]
    lines.append(f"  keys: {sorted(data)}")
    for k in ("Information", "Note", "Error Message"):
        if k in data:
            lines.append(f"  {k}: {str(data[k])[:300]}")
    segments = data.get("transcript")
    if not isinstance(segments, list):
        return lines
    text = " ".join(str(s.get("content", "")) for s in segments if isinstance(s, dict))
    lines.append(f"  returned symbol/quarter: {data.get('symbol')} / {data.get('quarter')}")
    lines.append(f"  segments: {len(segments)}, characters: {len(text):,}")
    if segments and isinstance(segments[0], dict):
        lines.append(f"  segment fields: {sorted(segments[0])}")
    for s in segments[:3]:
        if isinstance(s, dict):
            lines.append(f"  speaker: {s.get('speaker')} | {s.get('title')}")
    lines.append(f"  capex mentions: {len(CAPEX.findall(text))}")
    example = first_sentence_with(text, CAPEX)
    if example:
        lines.append(f"  first capex sentence: {example}")
    return lines


def main() -> int:
    load_dotenv(ROOT / ".env")
    key = os.getenv("ALPHA_VANTAGE_API_KEY", "").strip()
    if not key:
        print("ALPHA_VANTAGE_API_KEY is not set in .env")
        return 1
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_dir = ROOT / "data" / "probe" / "alpha_vantage"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out: list[str] = [f"Alpha Vantage transcript probe {stamp}", ""]
    for i, (symbol, quarter) in enumerate(PAIRS):
        if i:
            time.sleep(SPACING_S)
        params = {
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": symbol,
            "quarter": quarter,
            "apikey": key,
        }
        try:
            r = requests.get(URL, params=params, timeout=60)
            try:
                data: object = r.json()
            except ValueError:
                data = r.text[:300]
            (raw_dir / f"{symbol}_{quarter}.json").write_text(
                json.dumps(data, indent=1), encoding="utf-8"
            )
            lines = summarize(symbol, quarter, r.status_code, data)
        except requests.RequestException as e:
            lines = [f"{symbol} {quarter}: request failed: {type(e).__name__}"]
        lines = [ln.replace(key, "***") for ln in lines]
        print("\n".join(lines), flush=True)
        out += lines + [""]
    log = ROOT / "logs" / f"probe_av_{stamp}.txt"
    log.parent.mkdir(exist_ok=True)
    log.write_text("\n".join(out), encoding="utf-8")
    print(f"\nwrote {log.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
