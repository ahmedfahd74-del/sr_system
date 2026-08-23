# SwingTech D20 Hardening Proof

**Baseline commit:** `3dbd7ccdfa845770affd1ce0bfe353360892c7f3`

**Baseline Pine SHA-256:** `474111f40213bbd2d51d719517dee80195e95ee5d34f9fcdb286b73e53064383`

**Status:** `AWAITING_TV_PROOF`

## Finding disposition

| Finding | Reproduction | Change | Regression evidence |
|---|---|---|---|
| Canonical scoring divergence | **REPRODUCED.** `f_locScore()` omitted `conflCrossType` and `scFold`; confluence and focus independently recomputed scores. | Replaced numeric derivations with one `f_levelScore()` used by candidate selection, winning-level publication, confluence display and focus ranking. It applies type gating, canonical-source deduplication, direction compatibility, lifecycle authority and optional record folding once. | Static audit requires one definition plus four consumers and asserts both formerly omitted settings occur inside it. |
| LOC FVG confirmation | **REPRODUCED.** LOC latches mutated on every realtime update before confirmed ingest. | `f_fvgRaw()` still evaluates every bar, but LOC latch mutation is inside `if barstate.isconfirmed`. | Static audit isolates the LOC block and requires the confirmation gate. |
| Unsafe drawing handles | **REPRODUCED.** Execution, confluence filtering/decorating and focus called `line.set_*` on registry entries whose line may be `na` when outside `lvlDrawMax`. | Added `not na(handle)` guards at every affected setter. Existing label setters were already guarded. | Static audit requires every affected handle-specific guard; repository-wide setter inventory was reviewed. |
| Persistent GO | **REPRODUCED.** `timeState == 5` made GO true on every bar until reset. | Kept ARMED persistent, added `goConsumed`, and emits confirmed `goFire` once per armed/locked setup. Plots, alerts and tracker consume that event directly. | Static audit requires the confirmed one-shot latch and forbids tracker edge reconstruction. |
| Invalid parity-count premise | **REPRODUCED.** Registry totals depend on chart-loaded history, despite comments requiring equality. | Removed count/live-count parity plots. W/D/4H diagnostics now expose newest BOS source timestamp (identity), price and lifecycle state for comparison over common loaded history. | Static audit rejects count functions and requires all nine identity/price/state plots. |
| Duplicate FVG definition | **REPRODUCED.** The chart-leg diagnostic repeated bullish/bearish inequalities inline. | Extended `f_fvgRaw(atr, offset)` and routed source packet, LOC and leg diagnostic through it. Offset is non-negative and bounded by the existing 400-bar leg scan; threshold arithmetic remains unchanged. | Static audit requires exactly one definition/three consumers and rejects both former inline inequalities. |
| Dead/misleading diagnostics and naming | **REPRODUCED.** `hasLeg` was a redundant intermediary; its Phase 21 correction claim was false; `showLS`/`showLs` differed only by case. | Diagnostics state their predicates directly; misleading text was corrected; identifiers became `showLegSweep` and `showPoolSweep` without changing labels/defaults. | Static audit rejects the dead identifier and both case-only names in executable code. |

## Behavioral changes

- Non-default `conflCrossType=false` and `scFold=true` now affect the decision score exactly as they affect the displayed score. Defaults and numeric constants are unchanged.
- A developing chart-bar FVG cannot become permanent LOC state unless it still exists at close.
- GO is an event on one confirmed bar; ARMED remains visible as persistent state.
- Parity diagnostics no longer claim chart-history-dependent totals must match.
- Drawing calls skip absent handles instead of relying on undocumented setter behavior.

No threshold, weight, profile, risk default or trading-methodology constant changed.

## Verification

```text
python3 tools/audit_swingtech_hardening.py
SwingTech hardening static audit: PASS

python3 -m py_compile tools/audit_swingtech_hardening.py
PASS

python3 tools/pine_linter.py --test
PASS (the seeded six errors and one warning were detected)

python3 -m pytest -q
158 passed, 2 failed, 8 warnings
```

The two failures were live Yahoo Finance tests blocked by sandbox DNS. Exact unsandboxed retry:

```text
python3 -m pytest -q tests/test_full_system.py::test_data_fetch tests/test_full_system.py::test_unified_detection
2 passed, 2 warnings
```

Combined test evidence: all 160 collected repository tests passed when the two network-dependent cases were given network access.

The Pine linter reports 15 `STR001` errors on both the untouched baseline and hardened file. They are identical pre-existing false positives caused by apostrophes inside double-quoted strings; no new linter diagnostic was introduced. `git diff --check` passes.

## Harness disposition

This remote baseline contains neither `pinescripts/swingtech_strategy_harness.pine` nor an existing SwingTech harness generator. The permitted contract forbids hand-maintaining a divergent harness, so none was created or changed.

## TradingView-only proof still required

No TradingView compiler/runtime is available here. The following remain unresolved:

1. Pine v6 compilation with zero errors.
2. Realtime test proving a transient intrabar LOC FVG does not persist after bar close/reload.
3. Registry above `lvlDrawMax` proving no absent-handle runtime error in normal, focus, confluence and execution modes.
4. One setup held ARMED for multiple bars proving exactly one GO marker/alert/tracker entry.
5. `conflCrossType` and `scFold` toggles proving the line tag, focus rank and cockpit `Level ★` remain numerically identical.
6. W/D/4H newest BOS source-time, price and state comparison across chart timeframes using the same loaded-history start, followed by reload/replay comparison.
7. Visual and numerical comparison confirming leg FVG boxes/OTE diagnostics are unchanged on historical fixtures.

No compile, non-repainting, production-readiness or final-acceptance claim is made.
