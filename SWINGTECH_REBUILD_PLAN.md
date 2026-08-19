# SWINGTECH REBUILD PLAN
## Claude Execution Contract — Fix Once, Prove Every Phase, Never Patch Blindly

**Repository:** `ahmedfahd74-del/sr_system`  
**Primary Pine area:** `pinescripts/`  
**Plan file:** `SWINGTECH_REBUILD_PLAN.md`

---

# 0. PURPOSE

This document is the execution contract for the SWINGTECH rebuild.

The goal is **not** to keep patching the current script until the symptoms disappear.  
The goal is to remove the architectural causes of:

- MTF inconsistency and appearing/disappearing levels;
- realtime-vs-reload differences;
- duplicate or fake confluence;
- direction-blind level scoring;
- stale BOS / EQH / EQL / FVG state;
- retrospective level-memory leakage;
- multiple competing "brains";
- unsafe 5-of-6 execution logic;
- weak stop/target semantics;
- misleading custom backtest statistics;
- duplicate calculations and dead code.

The final system must have one deterministic pipeline:

```text
MARKET DATA
    ↓
CONFIRMED SOURCE ENGINE
    ↓
CANONICAL STRUCTURE + LEVEL STATE
    ↓
LEVEL LIFECYCLE + PROSPECTIVE MEMORY
    ↓
DIRECTION ENGINE
    ↓
CONFLUENCE ENGINE
    ↓
LOCATION ENGINE
    ↓
LOCKED SETUP
    ↓
TIMING STATE MACHINE
    ↓
RISK ENGINE
    ↓
GO / WAIT / INVALIDATE
    ↓
OBSERVABILITY + ALERTS + STRATEGY HARNESS
```

## Architectural law

> A module may publish evidence.  
> A module may consume published evidence.  
> A module must NOT secretly recreate another module's decision.

There must be:

- **one source truth;**
- **one definition of direction;**
- **one definition of location;**
- **one setup lock;**
- **one timing state machine;**
- **one risk definition;**
- **one backtest definition.**

---

# 1. NON-NEGOTIABLE WORK LOOP

Claude must execute **every phase** with this loop.

```text
FOR PHASE = 0 → FINAL:

    1. READ
       - Re-read this phase.
       - Inspect current code that the phase touches.
       - List exact functions/variables/modules affected.

    2. BASELINE
       - Record current behavior before editing.
       - Record current compile/runtime status.
       - Save before-values needed for regression comparison.

    3. IMPLEMENT
       - Change ONLY what the phase requires.
       - Do not introduce unrelated features.
       - Do not "improve" scoring while fixing data integrity.
       - Preserve frozen behavior contracts unless this phase explicitly changes them.

    4. STATIC AUDIT
       - Search for duplicate implementations.
       - Search for dead references.
       - Search for stale comments/tooltips.
       - Confirm bounded history references.
       - Confirm no accidental lookahead or chart-TF dependency was introduced.

    5. COMPILE
       - Pine v6 must compile with zero errors.
       - If Claude cannot access TradingView compiler:
           STATUS = AWAITING_TV_PROOF
           DO NOT claim PASS.

    6. TEST
       - Run all phase-specific tests.
       - Run the regression tests inherited from previous phases.

    7. PROVE
       - Create `docs/swingtech/rebuild/PHASE_<NN>_PROOF.md`.
       - Include:
         * files changed;
         * exact issue fixed;
         * before behavior;
         * after behavior;
         * test procedure;
         * expected result;
         * actual result;
         * screenshots/logs/tables if available;
         * unresolved risks;
         * commit SHA.

    8. GATE
       IF any required test fails:
           - STOP.
           - Diagnose root cause.
           - Fix within the same phase.
           - Repeat steps 4–8.
       ELSE:
           - Mark PHASE PASS.
           - Commit.
           - Advance to next phase.

END FOR
```

## Hard rule

**NO PHASE SKIPPING.**

If Phase 1 source integrity is not proven, do not work on ranking.  
If canonical level state is not proven, do not work on memory.  
If location is not proven, do not work on timing.  
If timing is not proven, do not tune exits or backtest results.

---

# 2. REQUIRED REBUILD ARTIFACTS

Create and maintain:

```text
docs/swingtech/rebuild/
    REBUILD_STATUS.md
    PHASE_00_PROOF.md
    PHASE_01_PROOF.md
    ...
    FINAL_ACCEPTANCE_PROOF.md

pinescripts/
    archive/
        SWINGTECH_CLAUDE_FROZEN.pine
    swingtech_rebuild.pine
    swingtech_strategy_harness.pine
```

`REBUILD_STATUS.md` must contain:

| Phase | Status | Commit | TradingView proof | Notes |
|---|---|---|---|---|

Allowed status values:

- `NOT STARTED`
- `IN PROGRESS`
- `AWAITING_TV_PROOF`
- `FAILED`
- `PASS`

---

# PHASE 0 — FREEZE THE BASELINE

## Issue

The current SWINGTECH has accumulated additive layers. Editing the only working copy makes regressions impossible to isolate.

## Why this is dangerous

Without an immutable baseline, a later difference can be mistaken for a fix when it is actually an unrelated regression.

## Correct design

Preserve Claude's current version as a **read-only behavioral reference**.

## Work

1. Identify the current latest Claude SWINGTECH source.
2. Copy it to:
   `pinescripts/archive/SWINGTECH_CLAUDE_FROZEN.pine`
3. Never edit the frozen file afterward.
4. Create:
   `pinescripts/swingtech_rebuild.pine`
5. Add a clear version header.
6. Record:
   - line count;
   - all `request.*()` calls;
   - all main state engines;
   - all scoring systems;
   - all tables/modes;
   - current default inputs.

## Proof

`PHASE_00_PROOF.md` must contain:

- SHA256 or git blob identity of frozen source;
- compile status;
- baseline screenshots or descriptions for at least:
  - 1D;
  - 30m;
  - 5m;
  - 1m;
- current known defects.

## Exit gate

PASS only when baseline is immutable and rebuild file compiles identically before logic changes.

---

# PHASE 1 — SOURCE INTEGRITY / CONFIRMED MTF PUBLICATION

## Issue

Current HTF publication can use developing higher-timeframe state, causing realtime/reload differences.

## Why this is a problem

A Daily/Weekly/4H level must not exist live and disappear after reload, or change depending on the chart used to view it.

This contaminates:

- MTF lines;
- bias;
- alerts;
- execution;
- any historical signal tracker.

## Correct design

Every fixed source timeframe publishes the **last fully confirmed source-bar state**.

All lower charts consume the same confirmed packet.

## Work

1. Create a single source packet function.
2. Use one consistent confirmed-source clock.
3. Remove mixed equal-TF/lower-TF publication semantics.
4. Do not use a developing HTF value as production state.
5. Keep source state deterministic on:
   - 3M;
   - 1M;
   - 1W;
   - 2D;
   - 1D;
   - 4H;
   - 1H;
   - 30m;
   - 15m;
   - 5m.
6. Keep compact primitive transport. Do not return large UDTs through `request.security()`.
7. Respect Pine tuple/request limits.

## Proof

For one symbol:

- record raw W BOS price on W;
- compare same W BOS raw value on D/4H/1H/30m/15m/5m/1m;
- repeat for D and 4H;
- reload indicator;
- repeat comparison.

Required result:

> confirmed source value is identical on every permitted lower timeframe and identical after reload.

## Exit gate

No confirmed-source mismatch.

---

# PHASE 2 — LOWER-TIMEFRAME / VOLUME PROFILE REQUEST SAFETY

## Issue

A configurable intrabar request can become invalid when the requested "lower" timeframe is actually above the chart timeframe. H/L/V are also requested redundantly.

## Why this is a problem

Can halt the script on 1m/5m or waste request resources.

## Correct design

One safe lower-TF tuple request.

## Work

1. Replace three separate H/L/V lower-TF requests with one tuple request.
2. Validate requested intrabar TF against chart TF.
3. Auto-select a valid lower/equal TF or gracefully disable VP when impossible.
4. No runtime halt on any supported chart TF.
5. Add Data Window diagnostic:
   - requested VP TF;
   - effective VP TF;
   - VP valid YES/NO.

## Proof

Test charts:

- 1m;
- 5m;
- 15m;
- 30m;
- 1H;
- 4H;
- 1D.

No invalid-timeframe runtime error.

## Exit gate

All supported chart TFs load safely.

---

# PHASE 3 — ONE CANONICAL LEVEL MODEL

## Issue

Current slots do not preserve enough semantics. Price/source/type alone cannot tell the system what a level means.

## Why this is a problem

Later modules guess:

- support vs resistance;
- bullish vs bearish;
- alive vs consumed;
- usable vs stale.

This creates conflicting decisions.

## Correct design

Every logical level has one canonical state containing at minimum:

```text
price
sourceTF
type
direction
role
lifecycleState
birthTime
lastUpdateTime
touches
holds
breaks
owner
authority
```

Suggested enums/concepts:

### Type
- BOS
- LS
- EQH
- EQL
- FVG
- PMZ (later, observational first)

### Direction
- BULL
- BEAR
- NEUTRAL

### Role
- FLOOR
- CEILING
- EQUILIBRIUM
- TARGET
- CONTESTED

### Lifecycle
- DISCOVERING
- ACTIVE
- TESTED
- PRESSURED
- BROKEN
- FLIP_CANDIDATE
- RETESTING
- FLIP_CONFIRMED
- FLIP_FAILED
- RETIRED

## Work

1. Build canonical internal representation.
2. Preserve direction from source event.
3. Remove any downstream need to infer direction from line position alone.
4. Rendering consumes canonical state; it does not define state.

## Proof

Data Window/debug table must show for each test level:

`TF | TYPE | PRICE | DIR | ROLE | STATE`

Verify manually on bullish and bearish BOS/FVG examples.

## Exit gate

No production decision may rely on a level whose direction/state is unknown.

---

# PHASE 4 — REMOVE `LOC` DOUBLE COUNTING

## Issue

Chart timeframe can appear once as its explicit fixed source and again as `"LOC"`.

## Why this is a problem

Same candle series can be counted twice as if two independent timeframes agree.

## Correct design

Canonical source identity is always the actual timeframe.

`LOC` may exist only as a cosmetic alias.

## Work

1. Replace logical `LOC` identity with actual chart timeframe identity.
2. If chart is 30m, local 30m evidence and fixed 30m evidence must deduplicate.
3. Same source + same logical event contributes once.
4. Same-TF multiple types may be retained but marked correlated.

## Proof

On 30m:

- create/find a 30m BOS present in fixed pool;
- confirm local version does not increase independent TF count;
- repeat 15m and 5m.

## Exit gate

No source event can masquerade as two independent TFs.

---

# PHASE 5 — LEVEL LIFECYCLE ENGINE

## Issue

BOS/EQH/EQL/FVG states can remain latched without meaningful consumption/retirement semantics.

## Why this is a problem

Dead evidence can continue to score and influence execution.

## Correct design

State changes must be explicit, deterministic, and source-owned.

## Work

### BOS lifecycle
Implement:
`ACTIVE → TESTED/PRESSURED → BROKEN → FLIP_CANDIDATE → RETESTING → FLIP_CONFIRMED/FAILED → RETIRED`

### EQH/EQL lifecycle
Implement:
`ACTIVE_SHELF → ATTACKED → SWEPT/BROKEN → RETIRED or FLIPPED`

### FVG lifecycle
Implement:
`BORN → ACTIVE → PARTIAL_FILL → MITIGATED/FILLED → RETIRED`

### Liquidity sweep lifecycle
Separate:
- level being swept;
- sweep event;
- subsequent ownership.

## Proof

Replay examples for each lifecycle transition.

Each proof must record:

- level price;
- source TF;
- transition bar/time;
- previous state;
- new state;
- reason.

## Exit gate

A consumed/retired level contributes zero production authority unless explicitly reactivated by a valid flip lifecycle.

---

# PHASE 6 — PROSPECTIVE LEVEL MEMORY

## Issue

Retrospective scorecard scans history around today's level price, potentially counting interactions before the level existed.

## Why this is a problem

This is hindsight contamination.

It also changes with chart ATR/chart bars.

## Correct design

Memory starts at level birth and only updates from future independent encounters on the source timeframe.

## Work

1. At birth:
   `touches=0, holds=0, breaks=0`
2. Define an encounter zone with source-normalized tolerance.
3. Count one encounter only after price leaves the zone and later returns.
4. A newborn level cannot self-count.
5. Store memory in source state.
6. No chart-TF rescanning.
7. Keep raw counts.
8. Optional state labels:
   - M0 UNTESTED
   - M1 TESTED/DEFENDED
   - M2+
9. Do not tune multipliers yet.

## Proof

Replay:

- create new level;
- verify zero memory at birth;
- first future revisit increments once;
- several bars parked at level do not add multiple touches;
- leave/re-enter increments next independent encounter;
- same W/D level has identical memory on 1m and source chart.

## Exit gate

Zero pre-birth memory and cross-TF memory parity proven.

---

# PHASE 7 — DIRECTION-AWARE CONFLUENCE

## Issue

Current confluence can combine nearby evidence without fully accounting for directional compatibility and independence.

## Why this is a problem

Conflict can be rewarded as agreement.

## Correct design

Confluence = **compatible independent evidence**, not raw proximity.

## Work

Score components separately:

1. Source authority.
2. Independent-TF agreement.
3. Same-TF correlation discount.
4. Direction compatibility.
5. Lifecycle validity.
6. Source-normalized price proximity.

Rules:

- BULL + BULL compatible.
- BEAR + BEAR compatible.
- BULL + BEAR = conflict, never extra agreement.
- RETIRED = zero.
- same TF repeated types are discounted.
- canonical higher-authority identity owns cluster representation.

## Proof

Construct/locate:

- compatible multi-TF cluster;
- same-TF multi-type cluster;
- opposing-direction cluster.

Expected:

- independent compatible cluster ranks highest;
- same-TF stack discounted;
- directional conflict labeled CONFLICT and not rewarded as agreement.

## Exit gate

No direction-blind confluence remains.

---

# PHASE 8 — PERMANENT MTF PARITY / CANONICAL INHERITANCE

## Issue

Changing chart timeframe changes candidate universe and can alter inherited HTF visibility/ranking.

## Why this is a problem

A 30m/D/W anchor must not vanish on 1m just because 15m/5m evidence exists.

## Correct design

Separate:

### Brain universe
Fixed source state; chart-independent.

### Visual universe
May add LTF context but cannot rewrite HTF identity/state.

## Work

1. Higher-authority source owns a clustered identity.
2. LTF sources can add context/confluence.
3. LTF sources cannot displace inherited HTF anchor identity.
4. Canonical membership must not depend on chart ATR.
5. If visual sleep/focus exists, it cannot change Brain state.
6. Add raw parity diagnostics per TF/type.

## Proof matrix

Same symbol/settings:

| Source | Source chart | 30m | 15m | 5m | 1m |
|---|---:|---:|---:|---:|---:|
| W BOS | compare | compare | compare | compare | compare |
| D BOS | compare | compare | compare | compare | compare |
| 4H BOS | compare | compare | compare | compare | compare |
| 1H BOS | — | compare | compare | compare | compare |
| 30m BOS | — | compare | compare | compare | compare |
| 15m BOS | — | — | compare | compare | compare |
| 5m BOS | — | — | — | compare | compare |

Values must match exactly where valid.

## Exit gate

No raw parity mismatch. Any visual-only difference must be explainable and must not affect Brain selection.

---

# PHASE 9 — DELETE COMPETING BRAINS

## Issue

Current script has overlapping decision systems:
- old checklist;
- confluence/focus;
- execution score;
- tracker interpretation.

## Why this is a problem

The chart can say one thing while Execution trades another.

## Correct design

One Decision Engine.

## Work

1. Delete old five-point checklist or convert it to pure diagnostics with no authority.
2. Delete misleading rows/variables.
3. Focus is cosmetic only.
4. Confluence publishes evidence only.
5. Execution consumes Location + Timing output only.
6. Tracker observes same GO event, never recreates a separate signal.

## Proof

Search code for:
- duplicate setup scores;
- duplicate readiness variables;
- duplicate location scans.

Required result:
one production `GO` source.

## Exit gate

Exactly one function/state path can produce GO LONG/GO SHORT.

---

# PHASE 10 — MARKET DIRECTION ENGINE

## Issue

Single configurable bias TF and BOS event direction are insufficient definitions of macro market structure.

## Why this is a problem

A last bullish BOS event can remain latched while actual HH/HL/LH/LL regime has become bearish.

## Correct design

Macro structure:

- W structure;
- D structure;
- 4H structure;
- majority 2-of-3.

1H is alignment/execution context, not macro vote.

BOS event direction remains separate metadata.

## Work

1. Publish source structure classification:
   - HH/LH;
   - HL/LL.
2. `structureDir=+1` only HH+HL.
3. `structureDir=-1` only LH+LL.
4. otherwise 0/MIXED.
5. Compute W/D/4H 2-of-3 macro bias.
6. Preserve latest BOS direction separately.

## Proof

Test:
- W↓ D↓ 4H↑ => BEARISH
- W↑ D↑ 4H↓ => BULLISH
- unresolved => MIXED

## Exit gate

Dashboard and Decision Engine use true structure regime, never stale BOS direction as a substitute.

---

# PHASE 11 — ONE LOCATION ENGINE

## Issue

Focus and Execution independently select levels.

## Why this is a problem

The chart may hide/reject one level while execution uses it anyway.

## Correct design

One Location Engine publishes:

```text
bestBullLocation
bestBearLocation
nearestOpposition
selectedPrice
selectedSource
selectedType
selectedDirection
selectedLifecycle
selectedOwner
selectedMemory
selectedAuthority
selectedConfluence
selectedDistance
selectedInvalidation
locationRank
```

## Work

1. Remove independent Execution raw-array location scan.
2. Remove production dependence on Focus selection.
3. Build directional eligibility.
4. Invalid/retired/conflicting level cannot be selected.
5. PMZ remains observational initially.
6. Psychological-number alignment remains observational, zero weight initially.

## Proof

For a known chart:
- show all candidate locations;
- show why winner won;
- show why rejected candidates lost;
- verify Execution uses exact same selected location.

## Exit gate

Display, alerts, execution, observer all reference the same location ID/price.

---

# PHASE 12 — SETUP LOCK

## Issue

If rankings move while price approaches, the setup can become a moving target.

## Why this is a problem

Sweep/reclaim/MSS must refer to the same defended level.

## Correct design

Lock location when:
- direction valid;
- location eligible;
- rank threshold passes;
- price enters approach band.

## Work

State:
`SCANNING → WATCHING → APPROACHING → LOCKED`

Once locked, location cannot be stolen by another candidate until:

- GO;
- hard invalidation;
- timeout;
- macro conflict.

Store:
- lock level;
- lock source;
- lock type;
- lock direction;
- lock time/bar.

## Proof

Replay while another level's score becomes higher.

Expected:
locked setup does not switch.

## Exit gate

Every timing event references one immutable locked location ID.

---

# PHASE 13 — LIQUIDITY SEMANTICS

## Issue

"Liquidity sweep" can refer to a historical leg-origin sweep or the current entry-level sweep.

## Why this is a problem

A user sees SWEEP ✓ and assumes the entry trigger has occurred.

## Correct design

Two separate variables:

### LEG SWEEP
Historical context/evidence.

### ENTRY SWEEP
Attack on exact locked location from defended side.

## Work

1. Rename variables/UI explicitly.
2. Never use LEG SWEEP as automatic ENTRY SWEEP.
3. ENTRY SWEEP valid only after setup lock.
4. Preserve sweep extreme for stop logic.

## Proof

Show:
- leg sweep true, entry sweep false;
- entry sweep true on locked level;
- unrelated sweep does not advance timing state.

## Exit gate

No ambiguous `sweep` variable in production execution code.

---

# PHASE 14 — TIMING STATE MACHINE

## Issue

A score threshold is not an entry sequence.

## Why this is a problem

Location must be converted into a trade only through deterministic price action.

## Correct design

```text
LOCKED
  ↓
ENTRY_SWEEP
  ↓
RECLAIM
  ↓
MSS/BOS
  ↓
DISPLACEMENT CHECK
  ↓
ARMED
  ↓
GO
```

Alternative continuation trigger may be configurable only after base path is proven.

## Work

1. Confirmed-bar transitions.
2. No future references.
3. Reconstruct recent sequence after reload using bounded lookback if required.
4. Store:
   - sweep extreme;
   - reclaim level;
   - MSS level;
   - trigger bar.
5. Define invalidation/timeout.

## Proof

Replay one full LONG and SHORT sequence bar by bar.

Document state on every transition.

## Exit gate

State machine cannot skip a mandatory stage.

---

# PHASE 15 — FVG UNIFICATION

## Issue

Multiple independent FVG detectors exist in chart engine, MTF engine and execution logic.

## Why this is a problem

They can disagree and stale FVG can satisfy a new setup.

## Correct design

One FVG publisher with lifecycle.

## Work

1. Remove duplicate execution FVG detector.
2. Use source packet FVG state.
3. Attach FVG to source + birth bar + lifecycle.
4. Optional rule:
   compatible ACTIVE FVG can increase rank.
5. FVG never creates GO independently.
6. Old unrelated FVG cannot satisfy current locked setup.

## Proof

Compare same FVG across:
- source chart;
- lower chart;
- execution observer.

One identity only.

## Exit gate

Exactly one FVG truth source.

---

# PHASE 16 — RISK ENGINE

## Issue

Nearest line + ATR buffer is not always a semantically valid stop.

## Why this is a problem

Risk can be based on a level that is not actually defending the setup.

## Correct design

### Sweep entry
Stop beyond locked setup's sweep extreme + optional execution buffer.

### Non-sweep model
Stop beyond explicit location invalidation boundary.

Targets:
- TP1 nearest valid internal opposition;
- TP2 next valid opposition;
- TP3 HTF floor/ceiling or opposing major zone.

## Work

1. Entry price defined explicitly.
2. Stop tied to locked setup.
3. Targets tied to canonical opposition.
4. Compute R:R from planned entry/stop/target.
5. Minimum R:R is a **mandatory gate**, not one interchangeable score point.

## Proof

For 10 sample setups:
- record location;
- sweep extreme;
- entry;
- stop;
- TP1/2/3;
- calculated R values.

Manually verify arithmetic.

## Exit gate

No GO without valid stop and minimum R:R.

---

# PHASE 17 — OPTIONAL EVIDENCE / PMZ OBSERVER

## Issue

Promising concepts can contaminate the core if given weight before prospective validation.

## Correct design

PMZ, owner, psych proximity, POC, extra FVG signals initially observe only.

## Work

At setup lock snapshot:

- direction;
- location;
- source;
- rank;
- memory;
- PMZ match;
- PMZ type;
- owner;
- owner alignment;
- psych proximity;
- leg sweep;
- entry sweep;
- FVG state.

After setup measure:

- MFE;
- MAE;
- 0.5R / 1R / 2R / 3R;
- bars-to-target;
- invalidation;
- timeout.

## Proof

Observer fields cannot affect GO when observer-only mode enabled.

A/B check:
toggle observer display on/off and verify identical GO bars.

## Exit gate

Observer has zero decision side effects.

---

# PHASE 18 — TRACKER ACCOUNTING REPAIR

## Issue

Custom tracker statistics can use inconsistent denominators and ambiguous timeout treatment.

## Correct design

Each tracked setup has exactly one status:

- OPEN
- WIN
- LOSS
- TIMEOUT

## Work

Report:

- total signals;
- closed;
- open;
- wins;
- losses;
- timeouts;
- win rate excluding timeout;
- win rate treating timeout as non-win;
- total R;
- expectancy;
- average win;
- average loss;
- MFE;
- MAE;
- max consecutive losses.

Any subset (e.g. 6/6 legacy comparison) must include its own timeout count and consistent denominator.

## Proof

Create a small deterministic synthetic/manual test set where expected results are known.

Expected counts must equal actual counts exactly.

## Exit gate

No statistic uses a hidden/inconsistent population.

---

# PHASE 19 — SEPARATE OBSERVER FROM REAL STRATEGY BACKTEST

## Issue

An indicator-based OHLC tracker is not the same as TradingView's broker-emulated strategy.

## Correct design

Two separate tools:

### `swingtech_rebuild.pine`
Indicator/observer for visual and state debugging.

### `swingtech_strategy_harness.pine`
`strategy()` implementation consuming identical frozen GO/SL/TP semantics.

## Work

Strategy harness must define:

- order timing;
- entry fill assumption;
- stop/limit behavior;
- commission;
- slippage;
- spread assumption when relevant;
- position sizing;
- pyramiding/overlap policy;
- Bar Magnifier policy.

Do not change the strategy logic while porting.

## Proof

For a small set of manually inspected signals:
- observer GO bar;
- strategy order creation;
- actual strategy fill;
- stop/target values.

Explain any expected one-bar/fill difference.

## Exit gate

Backtest is broker-emulator based and signal parity is documented.

---

# PHASE 20 — PERFORMANCE / REQUEST CLEANUP

## Issue

Duplicate engines and repeated requests waste Pine runtime budget.

## Correct design

One calculation per logical fact.

## Work

1. One structure source engine.
2. One FVG source engine.
3. One memory engine.
4. One confluence engine.
5. One location engine.
6. One timing engine.
7. One lower-TF tuple request where possible.
8. Bound all history scans.
9. Keep `max_bars_back` discipline.
10. Use Pine Profiler before/after.

## Proof

Record:
- number of request calls;
- tuple width;
- max loop bounds;
- profiler hotspots before/after;
- object counts.

## Exit gate

No runtime timeout in normal supported configurations.

---

# PHASE 21 — DEAD CODE / COMMENTS / INPUT CONTRACT CLEANUP

## Issue

Dead variables and stale comments make future maintenance unsafe.

## Work

Search every variable/function/input.

Classify:
- production;
- debug;
- deprecated;
- dead.

Delete dead code.

Correct:
- tooltips;
- comments;
- rule counts;
- version labels;
- stale "max lines" comments;
- obsolete mode descriptions.

No variable named for behavior it does not represent.

## Proof

Static search log included in phase proof.

## Exit gate

No known dead production variables and no known misleading comments.

---

# PHASE 22 — COCKPIT / COSMETIC AGENT

## Rule

Cosmetics come after logic.

The Cosmetic Agent may read state but never influence it.

## Required cockpit

```text
BIAS        BEARISH · W↓ D↓ 4H↑
LOCATION    D CEILING · LOCKED ✓
OWNER       BEAR ✓ / OBS
MEMORY      M2 · 3 TESTS / 2 HOLDS
RANK        74/65 ✓
ENTRY SWEEP ✓
RECLAIM     ✓
MSS/BOS     WAIT
ACTION      WAIT · MSS
```

Action must identify the first blocker:

- WAIT · SCAN
- WAIT · DIRECTION
- WAIT · LOCATION
- WAIT · RANK
- WAIT · LOCK
- WAIT · SWEEP
- WAIT · RECLAIM
- WAIT · MSS
- WAIT · RISK
- GO LONG
- GO SHORT
- INVALIDATED

## Proof

Toggle cosmetics off.

GO bars, raw state and strategy results must remain identical.

## Exit gate

Cosmetic layer has zero feedback into Brain.

---

# PHASE 23 — FULL REGRESSION GAUNTLET

No optimization in this phase.

Run correctness tests only.

## Test A — Compile

- Pine v6 zero compile errors.
- No unresolved warnings accepted without documentation.

## Test B — Historical bounds

No:
- negative bars-back errors;
- > allowed history-reference errors;
- invalid lower-TF requests.

## Test C — MTF raw parity

Run complete source/chart matrix from Phase 8.

## Test D — Reload stability

1. Record raw states.
2. Reload.
3. Compare confirmed history.

No confirmed-state changes.

## Test E — Replay / no early knowledge

Walk:
- pivot formation;
- BOS;
- level birth;
- first touch;
- sweep;
- reclaim;
- MSS;
- GO.

No state appears before confirmation.

## Test F — Memory

New level starts M0.
No pre-birth touch count.

## Test G — Lifecycle

Test:
- support broken;
- flip candidate;
- opposite-side retest;
- flip confirmation/failure.

## Test H — Setup lock

Ranking changes do not steal locked location.

## Test I — Mandatory gate enforcement

Force each gate false one at a time.

No GO if any mandatory gate fails.

## Test J — Visual independence

Cosmetic/display toggles must not change GO.

## Exit gate

Every test PASS with evidence.

---

# PHASE 24 — CONTROLLED STRATEGY VALIDATION

Only begin after Phase 23 passes.

## No tuning after seeing results

Freeze all default parameters and commit them before first formal test.

## Minimum markets

Use at least:
- one liquid crypto;
- one major FX pair;
- Gold/XAU;
- optionally one additional volatile instrument.

## Minimum time segments

Use:
- development/in-sample segment;
- untouched out-of-sample segment;
- if possible walk-forward windows.

## A/B sequence

### A — CONTROL
Structure + canonical location + timing + risk.

### B — PMZ
A + PMZ/ownership feature.

### C — MEMORY
B + prospective memory weighting.

### D — OPTIONAL EVIDENCE
C + one optional feature at a time.

Never add five modules at once.

## Required metrics

- number of trades;
- wins/losses/timeouts;
- win rate;
- expectancy R/trade;
- total R;
- profit factor;
- max drawdown R;
- average winner;
- average loser;
- median R;
- longest losing streak;
- MFE;
- MAE;
- long vs short;
- regime breakdown;
- source-TF breakdown;
- setup-grade breakdown;
- PMZ matched vs unmatched;
- owner aligned vs conflict;
- sweep vs no-sweep;
- in-sample vs out-of-sample.

## Proof

Export Strategy Tester results/CSV where possible.
Store under:

`docs/swingtech/rebuild/backtests/`

## Exit gate

No claim of edge until out-of-sample expectancy and drawdown are acceptable with adequate sample size.

---

# FINAL ACCEPTANCE PHASE — RELEASE PROOF

Create:

`docs/swingtech/rebuild/FINAL_ACCEPTANCE_PROOF.md`

It must contain all of the following.

## 1. Source integrity proof

Table showing W/D/4H/1H/30m/15m/5m raw values match downward across chart TFs.

## 2. Reload proof

Before/reload comparison for confirmed states.

## 3. No-lookahead/replay proof

At least one documented LONG and SHORT replay from:
`level birth → lock → entry sweep → reclaim → MSS → GO`.

## 4. Memory proof

At least one level proving:
- birth = 0 tests;
- first future encounter = 1;
- independent second encounter = 2;
- no pre-birth count.

## 5. Lifecycle proof

At least one:
- floor → break → flip candidate → retest → flip confirmed;
- ceiling → break → flip candidate → retest → flip confirmed/failed.

## 6. Mandatory gate proof

A table showing GO is impossible when any one mandatory gate is intentionally false.

## 7. Observer/cosmetic isolation proof

Same GO event sequence with:
- dashboard on/off;
- labels on/off;
- observer on/off.

## 8. Strategy-harness proof

Exact mapping:
`GO event → strategy order → fill → SL/TP`.

## 9. Performance proof

Final profiler/request/object-count summary.

## 10. Git proof

List every phase commit SHA.

## 11. TradingView proof

Include compiler confirmation and runtime/replay evidence.

If TradingView was not available to Claude:

> Final status MUST remain `AWAITING_TV_PROOF`.

Claude must never write "verified", "non-repainting", "backtest passed", or "production-ready" without the corresponding evidence.

---

# FINAL RELEASE CRITERIA

SWINGTECH is not complete until ALL are true:

- [ ] Frozen baseline exists.
- [ ] Confirmed MTF publication proven.
- [ ] No invalid lower-TF requests.
- [ ] One canonical level model.
- [ ] No LOC double counting.
- [ ] Direction attached to level evidence.
- [ ] BOS/EQ/FVG lifecycle implemented.
- [ ] Prospective memory only.
- [ ] Direction-aware confluence.
- [ ] Raw MTF parity proven.
- [ ] One production Brain.
- [ ] W/D/4H market structure majority implemented.
- [ ] One Location Engine.
- [ ] Setup lock proven.
- [ ] LEG SWEEP and ENTRY SWEEP separated.
- [ ] Timing sequence cannot skip mandatory stages.
- [ ] One FVG truth source.
- [ ] Risk tied to locked setup.
- [ ] PMZ/psych/POC observational until validated.
- [ ] Tracker accounting internally consistent.
- [ ] Separate `strategy()` backtest harness exists.
- [ ] Dead code/comments cleaned.
- [ ] Cosmetics have zero Brain influence.
- [ ] Full regression gauntlet passes.
- [ ] Out-of-sample strategy test completed.
- [ ] `FINAL_ACCEPTANCE_PROOF.md` complete.

---

# CLAUDE START COMMAND / OPERATING INSTRUCTION

When Claude pulls this repository, the first instruction is:

> Read `SWINGTECH_REBUILD_PLAN.md` completely.  
> Do not begin by editing the strategy.  
> Start at **Phase 0**.  
> Create/update `docs/swingtech/rebuild/REBUILD_STATUS.md`.  
> Execute the phase loop exactly.  
> Do not move to the next phase until the current phase has proof and PASS status.  
> If TradingView compile/runtime proof is unavailable, mark the phase `AWAITING_TV_PROOF` rather than claiming success.  
> Commit every passed phase separately.  
> Preserve the frozen baseline.  
> Never introduce an unrelated feature while repairing a phase.  
> At the end, produce `FINAL_ACCEPTANCE_PROOF.md`.

---

# THE LOOP IN ONE SENTENCE

> **READ → BASELINE → IMPLEMENT → STATIC AUDIT → COMPILE → TEST → PROVE → COMMIT → GATE → REPEAT.**

That loop is the rebuild.
