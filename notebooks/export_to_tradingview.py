# sr_system/notebooks/export_to_tradingview.py
"""Bridge: detect S/R levels in Python, emit a Pine v6 indicator for TradingView.

Runs the full sr_system pipeline (data + multi-method detection + confluence)
on a ticker/timeframe, then writes a self-contained Pine v6 indicator with the
detected levels as the default values of input.float() fields.

Once pasted into TradingView the indicator draws horizontal lines for every
support, resistance, and multi-timeframe confluence level on the user's real
TradingView chart. Each level is editable in the indicator settings, so the
user can refresh values either by re-pasting the script or by tweaking the
input fields directly.

Usage from the repo root:

    PYTHONPATH=. python3 notebooks/export_to_tradingview.py AMD 1D
    PYTHONPATH=. python3 notebooks/export_to_tradingview.py SPY 1H
    PYTHONPATH=. python3 notebooks/export_to_tradingview.py BTC-USD 1D

The Pine source is:
  - written to notebooks/exports/<TICKER>_<TF>_levels.pine
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List

# Make the project root importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import get_engine  # noqa: E402


# Maximum slots per category in the generated Pine indicator. Keep these small
# enough to fit comfortably in TradingView's 30-line / 30-label budgets while
# still covering more than enough levels for any realistic chart.
MAX_SUPPORT = 10
MAX_RESISTANCE = 10
MAX_CONFLUENCE = 5


@dataclass
class _Slot:
    price: float
    confidence: float
    is_support: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pine_title(s: str, max_len: int) -> str:
    """Strip non-ASCII and force into the Pine indicator title length budget."""
    out = "".join(c for c in s if 32 <= ord(c) < 127)
    if len(out) > max_len:
        out = out[:max_len]
    return out


def _pad_slots(items: List[_Slot], target: int, is_support: bool) -> List[_Slot]:
    """Pad with zero-valued slots so the Pine output has a fixed number of inputs."""
    out = list(items)[:target]
    while len(out) < target:
        out.append(_Slot(price=0.0, confidence=0.0, is_support=is_support))
    return out


def _format_price(p: float) -> str:
    """Render a price as a Pine-friendly float literal with sensible precision."""
    if p == 0:
        return "0.0"
    if p >= 1000:
        return f"{p:.2f}"
    if p >= 10:
        return f"{p:.4f}"
    return f"{p:.6f}"


# ---------------------------------------------------------------------------
# Pine generator
# ---------------------------------------------------------------------------

def _pine_inputs(slots: List[_Slot], prefix: str, group: str) -> str:
    lines = []
    for i, s in enumerate(slots, start=1):
        lines.append(
            f'i_{prefix}{i}p = input.float({_format_price(s.price)}, '
            f'"{prefix.upper()}{i} price", group=g_{group}, inline="{prefix}{i}")'
        )
        lines.append(
            f'i_{prefix}{i}c = input.float({s.confidence:.1f}, '
            f'"{prefix.upper()}{i} conf",  group=g_{group}, inline="{prefix}{i}")'
        )
    return "\n".join(lines)


def _pine_inputs_confluence(slots: List[_Slot], group: str) -> str:
    lines = []
    for i, s in enumerate(slots, start=1):
        is_supp = "true" if s.is_support else "false"
        lines.append(
            f'i_c{i}p = input.float({_format_price(s.price)}, '
            f'"C{i} price", group=g_{group}, inline="c{i}")'
        )
        lines.append(
            f'i_c{i}c = input.float({s.confidence:.1f}, '
            f'"C{i} conf",  group=g_{group}, inline="c{i}")'
        )
        lines.append(
            f'i_c{i}s = input.bool({is_supp}, '
            f'"C{i} is support", group=g_{group}, inline="c{i}")'
        )
    return "\n".join(lines)


def _array_from_call(prefix: str, suffix: str, count: int) -> str:
    parts = ", ".join(f"i_{prefix}{i}{suffix}" for i in range(1, count + 1))
    return f"array.from({parts})"


def generate_pine_script(
    ticker: str,
    timeframe: str,
    current_price: float,
    regime: str,
    pattern: str,
    signal: str,
    support: List[_Slot],
    resistance: List[_Slot],
    confluence: List[_Slot],
) -> str:
    timestamp = datetime.now().isoformat(timespec="seconds")

    full_title = _safe_pine_title(f"sr_system - {ticker} {timeframe}", 50)
    short_title = _safe_pine_title("SR-Sys", 10)

    s_padded = _pad_slots(support, MAX_SUPPORT, is_support=True)
    r_padded = _pad_slots(resistance, MAX_RESISTANCE, is_support=False)
    c_padded = _pad_slots(confluence, MAX_CONFLUENCE, is_support=True)

    s_inputs = _pine_inputs(s_padded, prefix="s", group="supp")
    r_inputs = _pine_inputs(r_padded, prefix="r", group="res")
    c_inputs = _pine_inputs_confluence(c_padded, group="conf")

    s_prices = _array_from_call("s", "p", MAX_SUPPORT)
    s_confs = _array_from_call("s", "c", MAX_SUPPORT)
    r_prices = _array_from_call("r", "p", MAX_RESISTANCE)
    r_confs = _array_from_call("r", "c", MAX_RESISTANCE)
    c_prices = _array_from_call("c", "p", MAX_CONFLUENCE)
    c_confs = _array_from_call("c", "c", MAX_CONFLUENCE)
    c_supports = _array_from_call("c", "s", MAX_CONFLUENCE)

    return f"""//@version=6
indicator("{full_title}", "{short_title}", overlay=true, max_lines_count={MAX_SUPPORT + MAX_RESISTANCE + MAX_CONFLUENCE + 5}, max_labels_count={MAX_SUPPORT + MAX_RESISTANCE + MAX_CONFLUENCE + 5})

// ============================================================
// Generated by sr_system/notebooks/export_to_tradingview.py
// Generated at: {timestamp}
// Ticker:       {ticker}
// Timeframe:    {timeframe}
// Price at gen: {_format_price(current_price)}
// Regime:       {regime}
// Pattern:      {pattern}
// Signal:       {signal}
//
// To refresh: rerun the Python exporter, then either replace this whole
// source or just edit the input values in TradingView's indicator settings.
// ============================================================

// ----- Style -----
g_style = "Style"
i_cSupp     = input.color(color.new(#00C853, 0), "Support color",          group=g_style)
i_cRes      = input.color(color.new(#FF1744, 0), "Resistance color",       group=g_style)
i_cConfSupp = input.color(color.new(#FFEB3B, 0), "Confluence support col", group=g_style)
i_cConfRes  = input.color(color.new(#FF9800, 0), "Confluence resist col",  group=g_style)
i_lw        = input.int(2,    "Line width",       minval=1, maxval=4, group=g_style)
i_show_lbls = input.bool(true,"Show labels",                          group=g_style)
i_min_conf  = input.float(0.0,"Min confidence to show", minval=0, maxval=100, group=g_style)

// ----- Support levels (set price=0 to hide a slot) -----
g_supp = "Support Levels"
{s_inputs}

// ----- Resistance levels -----
g_res = "Resistance Levels"
{r_inputs}

// ----- Confluence (multi-timeframe agreement) -----
g_conf = "Confluence Levels"
{c_inputs}

// ============================================================
// Drawing
// ============================================================
var array<line>  drawnLines  = array.new<line>()
var array<label> drawnLabels = array.new<label>()

if barstate.islast
    for ln in drawnLines
        line.delete(ln)
    drawnLines.clear()
    for lb in drawnLabels
        label.delete(lb)
    drawnLabels.clear()

    array<float> sPrices = {s_prices}
    array<float> sConfs  = {s_confs}
    array<float> rPrices = {r_prices}
    array<float> rConfs  = {r_confs}
    array<float> cPrices = {c_prices}
    array<float> cConfs  = {c_confs}
    array<bool>  cIsSupp = {c_supports}

    for i = 0 to sPrices.size() - 1
        float p = sPrices.get(i)
        float c = sConfs.get(i)
        if p > 0 and c >= i_min_conf
            line ln = line.new(x1 = bar_index - 50, y1 = p, x2 = bar_index + 10, y2 = p, xloc = xloc.bar_index, extend = extend.both, color = i_cSupp, width = i_lw, style = line.style_solid)
            drawnLines.push(ln)
            if i_show_lbls
                string txt = "S " + str.tostring(p, format.mintick) + " [" + str.tostring(int(c)) + "]"
                label lb = label.new(x = bar_index + 5, y = p, text = txt, xloc = xloc.bar_index, color = color.new(i_cSupp, 80), textcolor = i_cSupp, style = label.style_label_left, size = size.small)
                drawnLabels.push(lb)

    for i = 0 to rPrices.size() - 1
        float p = rPrices.get(i)
        float c = rConfs.get(i)
        if p > 0 and c >= i_min_conf
            line ln = line.new(x1 = bar_index - 50, y1 = p, x2 = bar_index + 10, y2 = p, xloc = xloc.bar_index, extend = extend.both, color = i_cRes, width = i_lw, style = line.style_solid)
            drawnLines.push(ln)
            if i_show_lbls
                string txt = "R " + str.tostring(p, format.mintick) + " [" + str.tostring(int(c)) + "]"
                label lb = label.new(x = bar_index + 5, y = p, text = txt, xloc = xloc.bar_index, color = color.new(i_cRes, 80), textcolor = i_cRes, style = label.style_label_left, size = size.small)
                drawnLabels.push(lb)

    for i = 0 to cPrices.size() - 1
        float p = cPrices.get(i)
        float c = cConfs.get(i)
        bool  isSupp = cIsSupp.get(i)
        if p > 0 and c >= i_min_conf
            color col = isSupp ? i_cConfSupp : i_cConfRes
            line ln = line.new(x1 = bar_index - 50, y1 = p, x2 = bar_index + 10, y2 = p, xloc = xloc.bar_index, extend = extend.both, color = col, width = i_lw + 1, style = line.style_solid)
            drawnLines.push(ln)
            if i_show_lbls
                string role = isSupp ? "CS" : "CR"
                string txt = role + " " + str.tostring(p, format.mintick) + " [" + str.tostring(int(c)) + "]"
                label lb = label.new(x = bar_index + 5, y = p, text = txt, xloc = xloc.bar_index, color = color.new(col, 70), textcolor = col, style = label.style_label_left, size = size.normal)
                drawnLabels.push(lb)
"""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _slot_from_unified(level) -> _Slot:
    return _Slot(
        price=float(level.price),
        confidence=float(getattr(level, "confidence", 0.0)),
        is_support=getattr(level, "is_support", level.level_type == "support"),
    )


def _slot_from_srlevel(level) -> _Slot:
    is_supp = bool(getattr(level, "is_support", True))
    return _Slot(
        price=float(level.price),
        confidence=float(getattr(level, "confidence", 0.0)),
        is_support=is_supp,
    )


def export(ticker: str, timeframe: str) -> str:
    ticker = ticker.upper().strip()
    engine = get_engine()

    print(f"[export] running detection for {ticker} ({timeframe}) ...")

    unified = engine.detect_unified(ticker, timeframe)
    if timeframe not in unified:
        raise SystemExit(
            f"[export] no data returned for {ticker} {timeframe}; "
            f"check the ticker and timeframe (try '1D', '1H', '5m')."
        )

    s_levels = unified[timeframe].get("support", [])[:MAX_SUPPORT]
    r_levels = unified[timeframe].get("resistance", [])[:MAX_RESISTANCE]
    confluence = engine.get_confluence_levels(ticker)[:MAX_CONFLUENCE]

    mtf_data = engine._get_mtf_data(ticker, [timeframe])
    data = mtf_data[timeframe]
    closes = list(data.closes)
    current_price = float(closes[-1]) if closes else 0.0

    regime = engine.classify_regime(data).name
    try:
        pattern_obj = engine.analyze_pattern(ticker, timeframe)
        pattern = pattern_obj.pattern_type.value
    except Exception:
        pattern = "unknown"
    signal = engine.analyze_price_action(ticker, current_price, timeframe).get(
        "signal", "neutral"
    )

    s_slots = [_slot_from_unified(l) for l in s_levels]
    r_slots = [_slot_from_unified(l) for l in r_levels]
    c_slots = [_slot_from_srlevel(l) for l in confluence]

    pine_src = generate_pine_script(
        ticker=ticker,
        timeframe=timeframe,
        current_price=current_price,
        regime=regime,
        pattern=pattern,
        signal=signal,
        support=s_slots,
        resistance=r_slots,
        confluence=c_slots,
    )

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    os.makedirs(out_dir, exist_ok=True)
    safe_name = ticker.replace("-", "_")
    out_path = os.path.join(out_dir, f"{safe_name}_{timeframe}_levels.pine")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(pine_src)

    print()
    print("=" * 60)
    print(f"GENERATED PINE INDICATOR for {ticker} {timeframe}")
    print("=" * 60)
    print(f"  Current price : {current_price:.2f}")
    print(f"  Regime        : {regime}")
    print(f"  Pattern       : {pattern}")
    print(f"  Signal        : {signal}")
    print(f"  Support found : {len(s_slots)} (showing top {MAX_SUPPORT})")
    print(f"  Resist  found : {len(r_slots)} (showing top {MAX_RESISTANCE})")
    print(f"  Confluence    : {len(c_slots)} (showing top {MAX_CONFLUENCE})")
    print()
    print(f"Pine source written to:")
    print(f"  {out_path}")
    print()
    print("Top support levels:")
    for slot in s_slots[:5]:
        if slot.price > 0:
            print(f"  {slot.price:>10.2f}   conf {slot.confidence:>5.1f}")
    print("Top resistance levels:")
    for slot in r_slots[:5]:
        if slot.price > 0:
            print(f"  {slot.price:>10.2f}   conf {slot.confidence:>5.1f}")
    if c_slots:
        print("Top confluence levels (multi-timeframe agreement):")
        for slot in c_slots:
            if slot.price > 0:
                role = "support" if slot.is_support else "resistance"
                print(f"  {slot.price:>10.2f}   conf {slot.confidence:>5.1f}   {role}")
    print()
    print("HOW TO USE IN TRADINGVIEW")
    print("-" * 60)
    print("  1. Open TradingView, click 'Pine Editor' at the bottom")
    print("  2. Click 'Open' -> 'New blank script' (delete starter code)")
    print(f"  3. Open the file at:")
    print(f"     {out_path}")
    print("     in any text editor and copy its entire contents")
    print("  4. Paste into the Pine Editor, click 'Save', name it")
    print("  5. Click 'Add to chart'")
    print()
    print("  To refresh later: rerun this exporter, then either")
    print("  re-paste the new source OR edit the input values in")
    print("  the indicator's settings panel directly.")
    print("=" * 60)
    print()

    return out_path


def main() -> int:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AMD"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1D"
    export(ticker, timeframe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
