# Investment engine — instructions for Claude Code

Start here: @docs/DESIGN.md (resume point, decisions, working agreements)

## Working rules
- Strategy changes are proposed with sources first and applied only after owner approval; ask before designing ambiguous sections.
- Keep docs concise; update the module doc in docs/ in the same commit as the code.
- Commit messages cite decision IDs (e.g. D13, R19).
- Tests never call live SEC endpoints unless marked `live`. SEC allows 10 requests/s per user; we target ≤ 8.
- No character limits on analysis text. Missing data stays missing, never zero.
- LLM output is accepted only with a verbatim quote verified against a stored passage.

## Reference code
Owner's old engine (pharma app) in `reference/old_engine/`: read-only source for reuse; never imported. What to keep, change or drop is mapped in `docs/M00_SEC_DATA.md`.

## Environment
Windows 11 · Python via uv · SQLite (WAL) in data/ · repo at C:\dev\Investment

## Commands
`uv sync` · `uv run pytest` · nightly refresh: `uv run python scripts/run_refresh.py` (tasks: `.\scripts\register_tasks.ps1`) · live SEC tests (owner runs, sends log): `uv run python scripts/run_live.py <label>` · call transcripts (owner runs): `uv run python scripts/run_calls.py --fetch N` · `uv run ruff check --fix .` · `uv run ruff format .` · `uv run pre-commit run --all-files`

## Module docs (read when working on that module)
`docs/M00_SEC_DATA.md` · `docs/M00_STORAGE.md` · `docs/M00_SEARCH.md` · `docs/M00_UI.md` · `docs/M01_TIMEFRAMES.md` · `docs/M02_THEMES.md` · `docs/M04_FINANCIALS.md` · `docs/SOURCES.md` · `docs/DATA_SOURCES.md` (data gaps; check at each module build) · `docs/LESSONS.md` (cross-module lessons; read at every build) · `docs/M02_BUILD_LOG.md` (M02 parts) · `docs/M04_BUILD_LOG.md` (M04 parts)
