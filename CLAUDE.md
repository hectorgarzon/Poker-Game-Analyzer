# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"            # install package + dev deps (Python 3.13+ required)
pre-commit install                 # required once before first commit
python run.py                      # run the Dash app at http://localhost:8050

pytest                             # all tests
pytest tests/test_parser.py::TestClassName::test_name    # single test
ruff check --fix .                 # lint (project-wide)
ruff format .                      # format (project-wide)
mypy src/                          # strict type check
```

**Ruff scope rule:** `ruff check --fix` and `ruff format` reformat the whole project. If you have unrelated uncommitted changes, scope to your touched files (e.g. `ruff format src/pokerhero/ingestion/ tests/test_ingestion.py`). Always commit formatting changes together with the feature/fix that triggered them — never as a separate commit.

## Source-of-Truth Documents

All design decisions, conventions, and formulas live in `.MD` files at the repo root. Read the relevant one before working on an area:

| File | Covers |
|------|--------|
| `Architecture.MD` | Tech stack, data-flow pipeline, current directory tree, Dash gotchas, format quirks |
| `DataStructure.MD` | SQLite schema, dataclass models, DB field mappings |
| `AnalysisLogic.MD` | Math formulas (EV, SPR, MDF, Pot Odds, VPIP, PFR, AF, etc.) |
| `TestingStrategy.MD` | TDD policy, fixture inventory |
| `Contributing.MD` | Toolchain, type-hint rules, naming, docstrings, commit protocol |
| `UserExperience.MD` | UI navigation, drill-down flow, dashboard KPIs |

If a requested change contradicts a rule/formula in the `.MD` files, **stop and flag it** — update the `.MD` first, then change code. After any code change, check whether the relevant `.MD` needs syncing and include the update in the same commit.

## Workflow Rules (non-negotiable)

- **TDD two-commit pattern is mandatory.** Per feature/fix make exactly two commits in this order: first `test(scope): ...` containing **only** the new failing tests, then `feat(scope): ...` or `fix(scope): ...` containing the implementation plus any `.MD` updates. Never bundle tests with their implementation — the red-state snapshot is intentional. Check `git log` to confirm the pattern before committing.
- **One logical change per commit.** Stage and commit affected files immediately after each agreed change before moving on.
- **Break large tasks into sub-tasks** (per test class, per module, per logical feature) and implement one per agent call — each fully tested and committed before the next.
- **Never `git add -f` a gitignored file.** `TODO.MD` is intentionally git-ignored.
- **Conventional Commits, imperative mood**: `feat|fix|test|docs|chore|refactor(scope): description`.

## Architecture Big Picture

Strictly linear pipeline: **raw `.txt` → splitter → parser → SQLite → queries/stats → Dash UI**.

- `src/pokerhero/parser/` — regex-based PokerStars parser (`hand_parser.py`) producing `ParsedHand` dataclasses (`models.py`). PokerStars-only; format quirks (UTF-8 BOM, CRLF, unpadded hour like `1:23:57`, EUR `€` prefix shifting regex group indices) are documented in `Architecture.MD`.
- `src/pokerhero/database/` — raw `sqlite3` (no ORM). Schema in `schema.sql`; helpers in `db.py`. **Always cast `numpy.int64` to Python `int()` before passing as `pd.read_sql_query` bind params** — sqlite3 silently returns empty results otherwise.
- `src/pokerhero/ingestion/` — splitter + ingest pipeline with re-buy detection.
- `src/pokerhero/analysis/` — `queries.py` (DataFrame-returning queries), `stats.py` (VPIP/PFR/EV/equity/archetype classification), `ranges.py` (169-hand pre-flop ranges, blend & contraction).
- `src/pokerhero/frontend/` — Dash multi-page app (`use_pages=True`). Pages in `frontend/pages/`. Theme via `dcc.Store("theme-store")` + clientside callback toggling `body.dark`; CSS variables in `assets/theme.css`.

**Design philosophy: "Numbers First, Space is Cheap."** Derived values (SPR, MDF, Pot Odds) are pre-calculated at parse time. EV is pre-computed and cached in `action_ev_cache` only via the explicit "📊 Calculate EVs" button — never on page load. Session reports render instantly by reading the cache.

## Code Style (enforced)

- **Strict mypy.** `typing.Any` is **banned** — use `TypedDict` for heterogeneous dicts (prefix `_` for module-internal, PascalCase for exported).
- Every function signature and class variable explicitly typed.
- PEP-8 naming; Google-style docstrings on public functions (include math reasoning where applicable).
- Decimal-aware money formatting only — `int()` and `:.0f` truncate micro-stake values. Use the `_fmt_blind` / `_fmt_pnl` helpers; Plotly hovertemplates use d3-format (`%{y:,.4g}`), not Python format.

## Recurring Pitfalls

- **Pattern-matching Dash callbacks** fire on mount with `n_clicks=0`. Guard with `if not ctx.triggered[0].get("value"): raise dash.exceptions.PreventUpdate`.
- **`dcc.Input` does not support `type="date"`** — use `type="text"` with a `YYYY-MM-DD` placeholder. `dash.html` has no `Input` — always use `dcc.Input`.
- **`hole_cards IS NOT NULL` ≠ hero reached showdown.** PokerStars records hero hole cards even on folds — filter on `hero_hp.went_to_showdown = 1`.
- **JOINs on `hand_players` produce one row per matching player.** Multiway showdowns duplicate hands unless deduplicated via correlated subquery (`= (SELECT MIN(...) ...)`) or `GROUP BY h.id`.
- **Test fixtures must mirror real PokerStars format exactly** — including `€` prefixes on every monetary value in EUR fixtures, not just the header.
- When a test file exceeds ~20 classes or ~1,000 lines, split along page/feature boundaries (`test_{page}.py`). Duplicate the `db` fixture rather than creating a shared `conftest.py`.
