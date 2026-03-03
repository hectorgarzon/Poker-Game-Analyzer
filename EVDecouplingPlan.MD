# EV Decoupling: Range Equity for Decisions, All-In EV for Variance

> **Status:** ✅ Implemented
> **Branch:** `feat/ev-decoupling`
> **Scope:** Decouple decision-review equity (always range-based) from variance-tracking equity (exact, all-in only). No backward-compatibility constraints.

---

## Problem Statement

The current EV system uses **exact equity** (against the villain's revealed cards) as its primary metric whenever cards are known, falling back to **range equity** only when the villain didn't show. This conflates two distinct analytical purposes:

1. **Decision Review** — "Was this call correct at the time I made it?" requires equity against the **villain's likely range**, because the hero couldn't know their exact hand.
2. **Variance Tracking** — "Was I lucky or unlucky?" requires equity against the villain's **actual cards**, but only at the **all-in moment** (the last point where both players committed all remaining chips and no further decisions could change the pot).

Industry-standard tools (PokerTracker 4, Hold'em Manager, Hand2Note) follow the **All-In EV** model: exact equity is only meaningful at the all-in street, and all other actions are evaluated against ranges.

### Current Behaviour (Problems)

| Scenario | Current Display | Problem |
|---|---|---|
| Hero calls preflop, villain shows at showdown | `Equity: 15% EV: −$X` (exact) | Makes a correct range-based call look terrible — hero couldn't know villain's hand |
| Hero calls flop, everyone checks to river showdown | `Equity: 42% EV: +$X` (exact at flop) | Equity computed against known cards, not the range hero was actually facing |
| Hero goes all-in on turn, villain calls | `Equity: 65% EV: +$X` (exact at turn) | ✅ This one is correct — all-in moment, exact cards, no further decisions |
| Hero folds river facing bet, villain showed | `✓ Good fold (call EV: −$X)` (exact) | May be misleading — fold correctness should be judged against the range, not the specific hand |

### Desired Behaviour

| Context | Metric | Source |
|---|---|---|
| **Action table** (hand replayer) — every hero action | **Range Equity** always | Villain's inferred range, contracted per street |
| **Variance summary** (Lucky/Unlucky) | **All-In Exact Equity** | Exact cards, but **only** for the all-in street |
| **All-In EV line** (session graph, future) | **All-In EV** | `(all-in equity × pot) − chips_invested` vs actual result |

---

## Design

### Two EV Tracks

The system will compute and store **two independent EV tracks** per action where applicable:

#### Track 1: Range EV (Decision Review)

- **Computed for**: Every hero CALL, BET, RAISE, and FOLD-facing-bet action.
- **Equity source**: Always `compute_equity_vs_range()` — villain's inferred range built from session stats, contracted street by street.
- **Stored as**: `ev_type = 'range'` or `'range_multiway_approx'` in `action_ev_cache`.
- **Displayed in**: Action table (hand replayer). This becomes the **only** EV shown in the action column.
- **Purpose**: "Was this decision correct given what I could have known?"

#### Track 2: All-In EV (Variance Tracking)

- **Computed for**: Only the hero action that is an **all-in** (or calls an all-in) where villain cards are known. Specifically: the hero's action where `is_all_in = 1` on the **all-in street** — the street where the last player went all-in.
- **Equity source**: `compute_equity()` or `compute_equity_multiway()` against the villain's actual hole cards.
- **Stored as**: `ev_type = 'allin_exact'` or `'allin_exact_multiway'` in `action_ev_cache`.
- **Displayed in**: Variance summary (Lucky/Unlucky section on session report). NOT shown in the action table's primary EV column.
- **Purpose**: "Did I run above or below expectation in spots where all the money went in?"

### Key Rules

1. **Action table always shows range equity.** Even when villain cards are known, the decision-review column uses range-based EV. This trains the user to think in ranges and avoids the hindsight bias of exact cards.

2. **All-In EV is only computed at the all-in moment.** If players went all-in on the flop, compute exact equity on the flop. If nobody went all-in (called down to showdown with money behind), no all-in EV is computed for that hand — it does not appear in the Lucky/Unlucky summary.

3. **Hands without an all-in are excluded from variance tracking.** If the hand reached showdown but players always had money behind (e.g. check-call-check-call to river), there is no single "luck moment" to measure — every street involved active decisions that changed the outcome. These hands still get range EV in the action table but produce no Lucky/Unlucky flag.

4. **Fold EV continues to use range equity.** The "Was this fold correct?" verdict is a decision-review metric. It uses the same range-based EV as all other action-table entries.

5. **Both tracks can coexist for the same action.** An all-in action gets both a range EV row (for the action table) and an all-in exact EV row (for variance tracking). They are stored as separate rows in `action_ev_cache` with different `ev_type` values.

---

## Schema Changes

### `action_ev_cache` — New `ev_type` Values

Add two new allowed values to the `ev_type` CHECK constraint:

```sql
-- Current: CHECK(ev_type IN ('exact', 'exact_multiway', 'range', 'range_multiway_approx'))
-- New:     CHECK(ev_type IN ('exact', 'exact_multiway', 'range', 'range_multiway_approx',
--                             'allin_exact', 'allin_exact_multiway'))
```

The old `'exact'` and `'exact_multiway'` values become **deprecated** — no new rows will be written with those types after this feature, but existing rows remain for backward compatibility until the user recalculates EVs.

### No New Tables or Columns Required

The existing schema supports dual rows per action (the PK is `(action_id, hero_id)` — **this needs to change** to allow two rows per action):

```sql
-- Current PK: PRIMARY KEY (action_id, hero_id)
-- New PK:     PRIMARY KEY (action_id, hero_id, ev_type)
```

This allows one action to have both a `range` row and an `allin_exact` row.

---

## Orchestrator Changes (`calculate_session_evs`)

### Current Flow

```
For each hero action:
  1. Identify primary villain
  2. If villain cards known → compute exact EV
  3. Else → compute range EV
  4. Store single row
```

### New Flow

```
For each hero action:
  1. Identify primary villain
  2. ALWAYS compute range EV → store as 'range' row
  3. IF this action is_all_in AND villain cards known:
     a. Also compute exact EV against known cards
     b. Store as 'allin_exact' row (second row for same action)
  4. Store both rows
```

### All-In Street Detection

The "all-in street" for the hero is the street where the **hero** became all-in (i.e. the hero's action has `is_all_in = 1`). This is the moment the hero was locked in and could make no further decisions.

**Multiway all-in edge case:** If hero goes all-in on the flop but two villains both call and still have chips behind, those villains may continue betting on the turn and river (creating a side pot). Hero's all-in EV is still computed **on the flop** — the moment hero was locked in — against **all active players' revealed cards** at showdown. The `compute_equity_multiway()` function evaluates hero's equity on the flop board against all opponents' actual hands, regardless of whether those opponents later created side pots.

Example:
- Flop: Hero shoves, V1 calls (still has chips), V2 calls (still has chips)
- Turn/River: V1 and V2 bet into a side pot
- Showdown: All three hands revealed
- Hero's all-in EV = equity on the **flop** against V1 + V2's revealed hands × main pot − hero's investment

The query `get_session_hero_ev_actions` already returns `is_all_in` per action row, so no query change is needed for detection.

### Range EV for All Actions

Currently, when villain cards are known, the orchestrator skips range computation entirely. After this change, it always runs the range path first. If `compute_equity_vs_range` returns < 5 surviving combos, the range EV is still skipped (same as today), but the all-in exact EV is still computed if applicable.

---

## Display Changes

### Action Table (`_build_ev_cell`)

- **Remove** the `ev_type in ('exact', 'exact_multiway')` branch entirely.
- **Always** display range EV: `Est. Equity: ~X% Est. EV: ±Y` with the ℹ tooltip.
- The FOLD verdict branch continues to work the same way (it already uses whatever EV is stored; now it will always be range-based).
- **Optional enhancement**: If an all-in exact EV also exists for this action, show a small secondary annotation like `(All-in EV: ±Y)` — but this is low priority and can be deferred.

### Session Report — Lucky/Unlucky (`_build_ev_summary`, `_build_flagged_hands_list`)

- **Change** `get_session_showdown_evs` to filter on `ev_type IN ('allin_exact', 'allin_exact_multiway')` instead of `('exact', 'exact_multiway')`.
- The summary now reads: "Based on **N all-in hands**" instead of "Based on N showdown hands".
- Hands that went to showdown without an all-in are excluded from Lucky/Unlucky classification.
- Thresholds remain the same (lucky < 40% equity, unlucky > 60% equity).

### Action Table — `_render_actions` EV Cache Loading

- When loading the EV cache for display, filter to `ev_type IN ('range', 'range_multiway_approx')` to avoid accidentally picking up an all-in exact row. Currently it reads all types and picks the last one; this needs to be explicit.

---

## Migration Strategy

### Recalculation Required

After deploying this change, users must press **📊 Calculate EVs** again for each session. The orchestrator will:
1. Clear existing `action_ev_cache` rows for the session (existing behaviour via `clear_session_evs`).
2. Recompute all rows with the new dual-track logic.

Since there are no production users, existing data can be cleared and reloaded. No incremental migration is needed.

---

## Implementation Plan

### Part A — Schema & Orchestrator

1. **Update `action_ev_cache` PK** to `(action_id, hero_id, ev_type)` and add `'allin_exact'` / `'allin_exact_multiway'` to the CHECK constraint — `schema.sql`. No migration needed (data will be cleared and reloaded).
2. **Update `save_action_evs`** in `db.py` to handle multiple rows per action.
3. **Refactor `calculate_session_evs`** to always compute range EV first, then conditionally compute all-in exact EV as a second row. Must handle multiway all-in correctly (compute exact equity against all revealed hands on the all-in street).

### Part B — Display Changes

4. **Simplify `_build_ev_cell`** — remove exact EV branch; always show range format.
5. **Update `_render_actions`** — filter EV cache to range types only.
6. **Update `get_session_showdown_evs`** → `get_session_allin_evs` — filter to `allin_exact` types; rename for clarity.
7. **Update `_build_ev_summary`** — change wording from "showdown hands" to "all-in hands".
8. **Update `_build_flagged_hands_list`** — same filter change.

### Part C — Tests

9. **Update `TestCalculateSessionEvs`** — verify dual rows written for all-in hands; verify range-only for non-all-in.
10. **New test: `TestAllInMultiwayEV`** — verify all-in on flop computes exact equity against all revealed hands (multiway side-pot scenario).
11. **Update `TestBuildEvCell`** — remove exact display tests; verify range-only display.
12. **Update `TestBuildEvSummary` and `TestBuildFlaggedHandsList`** — verify all-in-only filtering.
13. **Update `TestRenderActionsEVShowdown`** — verify range EV loaded for display even when cards known.

### Part D — Documentation

14. **Update `AnalysisLogic.MD`** — rewrite §4.A (exact → all-in only), §4.B (range → always for actions), §4.F (Lucky/Unlucky uses all-in only).
15. **Update `UserGuide.MD`** — rewrite EV column description (always range), Lucky/Unlucky description (all-in only).
16. **Update `DataStructure.MD`** — new PK, new ev_type values.
17. **Update `guide.py`** — match UserGuide changes.

---

## Files Touched

| File | Change type |
|---|---|
| `schema.sql` | PK migration, new ev_type values |
| `db.py` | Migration logic for PK change; update `save_action_evs` |
| `stats.py` | Refactor orchestrator: always range first, all-in exact second |
| `queries.py` | Rename `get_session_showdown_evs` → `get_session_allin_evs`; filter change |
| `sessions.py` | Simplify `_build_ev_cell`; update `_render_actions` EV cache filter; update summary/flagged wording |
| `AnalysisLogic.MD` | Rewrite EV section |
| `DataStructure.MD` | New PK, new ev_type values |
| `UserGuide.MD` | Rewrite EV descriptions |
| `guide.py` | Match UserGuide |
| `test_analysis.py` | Update orchestrator tests |
| `test_sessions.py` | Update display + summary tests |
| `test_database.py` | Update schema tests for new PK |

---

## Open Questions

1. **Should we show the all-in exact EV as a secondary annotation in the action table?** E.g. `Est. Equity: ~62% Est. EV: +$3.20 (All-in EV: +$4.10)`. This gives the user both perspectives but adds visual complexity. → **Proposed: defer to a future enhancement.**

2. **What about hands where hero is all-in but villain cards are unknown?** (e.g., hero shoves, everyone folds, no showdown). → **No all-in EV computed** — there's no exact equity to measure. Range EV is still computed for the action table.

3. **Performance impact of always computing range EV.** Currently, hands with known villain cards skip the range path entirely (faster). Now every action runs the range pipeline. The range path involves `build_range` → `expand_combos` → `contract_range` → MC sampling, which is heavier than the exact path. → **Acceptable** — the Calculate EVs button already runs in a blocking callback, and the extra time per action is ~50-200ms (dominated by MC sampling which is the same either way).

4. **Should fold EV verdict (§D) also get an all-in variant?** A fold by definition isn't all-in, so → **No. Fold EV remains range-only.**
