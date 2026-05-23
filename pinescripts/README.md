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
