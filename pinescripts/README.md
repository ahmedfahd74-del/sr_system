# sr_system Pine indicators

Native Pine v6 indicators that run inside TradingView. **Add once, works
on any chart you switch to** (no Python, no per-ticker level paste).

## Files

### `sr_auto_levels.pine`  *(recommended for live trading)*

Auto-detecting multi-timeframe S/R indicator.

**What it does**

- Scans pivot highs / lows on the current chart timeframe AND up to 3
  higher timeframes (default: 1H, 4H, Daily).
- Clusters nearby pivots into "levels" using a percent-of-price tolerance.
- Scores each level by:
    1. number of touches
    2. recency
    3. multi-timeframe confluence (pivots that show up on HTFs too)
- Renders the top N strongest levels:
    - 🟢 green = support
    - 🔴 red   = resistance
    - 🟡 yellow tint on the label = level confirmed across 2+ HTFs
    - line thickness scales with strength
- Status table (top right) showing symbol / pivot length / level count.
- 4 built-in `alertcondition`s:
    - Approaching support
    - Approaching resistance
    - Broke support
    - Broke resistance

**Why this and not the Python -> Pine bridge**

The bridge in `notebooks/export_to_tradingview.py` is per-ticker: each
generated `.pine` file has the levels for ONE ticker hardcoded. Switch
the chart symbol on TradingView and the levels are wrong. Useful for
analysis / sharing, but not for daily trading.

`sr_auto_levels.pine` does its own detection inside Pine, so the same
indicator works on any symbol. Switch from AMD to BTCUSDT.P to SOLUSDT.P
and it auto-detects fresh levels every time.

### `institutional_engine_v6.pine`  *(full market-structure engine)*

Complete Pine v6 port of the institutional trading engine: swing
structure with BOS/CHoCH state machine, 11-sensor trend composite,
W/D/4H/1H bias ladder, liquidity pools and sweeps, PDH-to-PMH levels
with role reversal, volume profile (POC/VA/HVN/LVN), anchored VWAP,
order blocks, fair value gaps, 9 entry setups, ATR-based stops,
clustered profit targets, a 10-sensor A+++ trade score with hard
rejects, and risk gates. No-lookahead by construction (pivots confirm
k bars later, orders fill next-bar open); includes an on-chart
explainability table showing which sensors drove each decision.

**Usage**: paste into a blank Pine v6 indicator, add to chart, then
tune the input group (swing legs, ATR length, score thresholds) to your
instrument. See the header comment inside the file for the full engine
mapping and caveats (delta is a signed-volume proxy; HTF bias is one
period delayed).

### `institutional_engine_v6_1.pine`  *(flagship + Visual Pack)*

The `institutional_engine_v6.pine` engine with a toggle-gated Visual
Pack layer (Settings → "11 · Visual Pack"): OTE/equilibrium band
(VWAP ± 0.1 ATR), anchored VWAP at the last BOS/CHoCH with 1σ/2σ
bands, HTF bias background tint + badge, and trend bar tint.

This version also carries the verification-pass fixes, all confirmed
against the TypeScript reference platform:

- Role-reversal level scan uses `close[bar_index - j]` (index → offset)
  — the retest setup was reading the wrong bars.
- Stop loss attached to **all three** exit legs (was 20% only), so 100%
  of the position is protected.
- EMA sensor confirms direction only (`emaDir == 1 / -1`) — no flips.
- Order-block displacement measured forward (causal), matching the
  engine's "next 3 bars" rule.
- Circuit-breaker pause (`cbPause`) is implemented in the entry gate.
- Session windows use UTC (`hour(time, "UTC")`), matching the reference.
- `EXECUTE_REDUCED` sizes at 0.75× risk; sizing accounts for
  `syminfo.pointvalue`.
- Visual Pack plots use `color.aqua` (valid built-in).

Engine logic is otherwise byte-identical to `institutional_engine_v6.pine`.

**Usage**: paste into the Pine editor (strategy), add to chart. Inputs
match the base engine plus the Visual Pack group at the bottom.

### `tip_v6.pine` — TIP Market Structure + Trend + Regime + Levels

Research-mirror indicator (Pine v6) of the deterministic engines in the
Trading Intelligence Platform: fractal swing detection, structure
classification (HH/HL/LH/LL, BOS, CHoCH), a 6-vote trend engine, a
precedence-based regime engine, and objective levels (PDH/PDL, PWH/PWL,
PMH/PML, D/W/M opens, session hi/lo, session VWAP, rolling POC).

**What it does**

- `ta.pivothigh/low` k-bar-confirmed swing detection — everything shown
  is causal (no repaint past bar confirmation).
- Structure events: HH/HL/LH/LL labels, BOS and CHoCH markers, with
  `lastBias` tracking to distinguish CHoCH (bias-flip) from BOS.
- Trend: 6 independent votes (structure, EMA, momentum, VWAP, volume
  participation + volatility shown direction-less) with agreement % —
  no fused score.
- Regime: deterministic precedence COMPRESSION → HIGH_VOL/LOW_VOL →
  TRENDING_BULL/BEAR → RANGE, driven by ADX, BBW percentile and ATR
  percentile, with a momentum guard so clean trends aren't labelled
  compression.
- Levels: prior-period extremes via `request.security` with
  `lookahead_off` (strictly backward-looking), strength by proximity,
  touch-count estimation, strength/touch filtering and a max-lines cap
  (strongest first). Level table bottom-right, trend/regime panel
  top-right, 4 `alertcondition`s (BOS/CHoCH up/down).

**Install / use** — same steps as below; settings groups: Swing
Detection, Market Structure, Trend Engine, Regime Engine, Objective
Levels, Display.

### `ti_smc_v6.pine` — Institutional SMC indicator

Pine v6 indicator ("Trading Intelligence [Institutional SMC]") mirroring
an institutional market-structure + smart-money-concepts engine.

**What it does**

- **Market structure** — N-bar fractal swings (HH/HL/LH/LL with ATR-based
  significance), BOS (break of structure, continuation) vs CHoCH (change
  of character, reversal) with displacement filters, trend state from the
  recent swing sequence.
- **Order blocks** — last opposite candle before an impulsive move,
  unmitigated-only option, boxed and shaded.
- **Fair value gaps** — 3-candle gaps filtered by ATR multiple, unmitigated
  tracking.
- **Liquidity** — equal-high/equal-low pools (BSL/SSL) plus sweep labels
  with reaction confirmation.
- **Trend engine** — composite score [-1,+1] from swing + EMA-stack + ADX
  components (35/35/30 weights).
- **Regime engine** — TRENDING / RANGING / EXPANSION / COMPRESSION from
  ATR-percentile ratio and trend score.
- **VWAP** — session-reset cumulative VWAP with 1σ/2σ bands.
- **S/R confluence** — swing levels + VWAP + round numbers clustered
  within ATR tolerance, top N displayed.
- Info table (trend/regime/structure/last event/VWAP/ATR), trend
  background tint, 7 alertconditions (BOS, CHoCH, sweeps, regime change).

**Install / use** — same steps as below; settings groups: Market
Structure, Order Blocks, Fair Value Gaps, Liquidity Pools, Trend & Bias,
Regime Detection, VWAP, Support & Resistance, Colors.

## How to install

1. Open TradingView.
2. Click **Pine Editor** at the bottom of the page.
3. Click **Open** -> **New blank indicator** (delete the starter code).
4. Open `pinescripts/sr_auto_levels.pine` in any text editor (or
   `cat pinescripts/sr_auto_levels.pine | pbcopy` on Mac to copy in one step).
5. Paste into the Pine Editor.
6. Click **Save**, name it (e.g. `SR Auto Levels`).
7. Click **Add to chart**.

That's it. The indicator now runs on every chart you open.

## Tuning

Open the indicator's settings (gear icon) on your chart:

| Section               | Useful tweaks                                                  |
|-----------------------|----------------------------------------------------------------|
| Detection             | `Lookback bars` (more = more historical levels), `Min touches` |
| Multi-Timeframe       | Change HTFs to match your trading style (e.g. `15`, `60`, `D`) |
| Scoring weights       | Boost `HTF confluence weight` if you want fewer, stronger lvls |
| Style                 | Colors, line widths, label visibility                          |

## Setting up alerts

1. Right-click the indicator name on your chart.
2. **Add alert on SR Auto Levels...**
3. Pick the condition (Approaching support / Broke resistance / etc.).
4. Configure delivery (popup, email, mobile push, webhook).

Pair this with the Python `live_dashboard.py` for redundancy: TV pops
your phone, Python logs it to `alerts.log`.
