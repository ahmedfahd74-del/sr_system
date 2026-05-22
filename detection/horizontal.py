# sr_system/detection/horizontal.py
"""Horizontal Support & Resistance detection using pivot highs/lows."""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from data.ohlcv import OHLCVData


@dataclass
class SRLevel:
    """A support or resistance level."""
    price: float
    level_type: str          # "support" or "resistance"
    confidence: float        # 0-100
    touch_count: int
    touch_bars: List[int]    # bar indices where price touched this level
    source: str = "horizontal"
    timeframe: str = "1D"

    @property
    def is_support(self) -> bool:
        return self.level_type == "support"

    @property
    def is_resistance(self) -> bool:
        return self.level_type == "resistance"


def atr(data: OHLCVData, period: int = 14) -> np.ndarray:
    """Calculate Average True Range."""
    highs = data.highs
    lows = data.lows
    closes = data.closes

    tr = np.maximum(highs - lows,
                    np.maximum(
                        np.abs(highs - np.roll(closes, 1)),
                        np.abs(lows - np.roll(closes, 1))
                    ))
    tr[0] = highs[0] - lows[0]

    atr = np.zeros_like(tr)
    atr[period - 1] = tr[:period].mean()
    for i in range(period, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def find_pivot_highs(data: OHLCVData, left_bars: int = 5, right_bars: int = 5) -> List[Tuple[int, float]]:
    """Find pivot high points."""
    highs = data.highs
    pivots = []
    for i in range(left_bars, len(highs) - right_bars):
        if highs[i] == max(highs[i - left_bars:i + right_bars + 1]):
            pivots.append((i, highs[i]))
    return pivots


def find_pivot_lows(data: OHLCVData, left_bars: int = 5, right_bars: int = 5) -> List[Tuple[int, float]]:
    """Find pivot low points."""
    lows = data.lows
    pivots = []
    for i in range(left_bars, len(lows) - right_bars):
        if lows[i] == min(lows[i - left_bars:i + right_bars + 1]):
            pivots.append((i, lows[i]))
    return pivots


def merge_nearby_levels(levels: List[SRLevel], threshold_pct: float = 0.5) -> List[SRLevel]:
    """Merge S/R levels that are within threshold_pct of each other."""
    if not levels:
        return []

    # Sort by price
    sorted_levels = sorted(levels, key=lambda x: x.price)
    merged = [sorted_levels[0]]

    for level in sorted_levels[1:]:
        last = merged[-1]
        price_diff_pct = abs(level.price - last.price) / last.price * 100
        if price_diff_pct <= threshold_pct:
            # Merge: keep higher confidence, combine touch counts
            combined_touches = list(set(last.touch_bars + level.touch_bars))
            last.touch_count = len(combined_touches)
            last.touch_bars = sorted(combined_touches)
            last.confidence = max(last.confidence, level.confidence)
            # Keep the one closer to current price as the anchor
            if level.confidence > last.confidence:
                last.price = level.price
        else:
            merged.append(level)

    return merged


def compute_confidence(
    touch_count: int,
    volume_profile: np.ndarray,
    touch_bars: List[int],
    atr_val: float,
    price: float,
    current_idx: int,
    weights: dict = None
) -> float:
    """Compute confidence score 0-100 for an S/R level."""
    if weights is None:
        weights = {"touches": 0.30, "volume": 0.25, "recency": 0.20, "confluence": 0.25}

    # Touch score: more touches = higher, but diminishing returns
    touch_score = min(touch_count / 5, 1.0) * 100 * weights["touches"]

    # Volume score: was volume elevated at touch points?
    if touch_bars:
        touch_vols = volume_profile[touch_bars]
        avg_vol = volume_profile[:len(volume_profile)//4].mean() if len(volume_profile) > 20 else volume_profile.mean()
        vol_ratio = touch_vols.mean() / avg_vol if avg_vol > 0 else 0
        vol_score = min(vol_ratio / 2, 1.0) * 100 * weights["volume"]
    else:
        vol_score = 0

    # Recency score: recent touches weighted more
    if touch_bars:
        most_recent = max(touch_bars)
        bars_ago = current_idx - most_recent
        recency_score = max(0, (1 - bars_ago / 100)) * 100 * weights["recency"]
    else:
        recency_score = 0

    return touch_score + vol_score + recency_score


def detect_horizontal_sr(
    data: OHLCVData,
    lookback: int = 100,
    min_touches: int = 2,
    atr_multiplier: float = 2.0,
    merge_threshold_pct: float = 0.5,
    timeframe: str = "1D",
) -> Tuple[List[SRLevel], List[SRLevel]]:
    """
    Detect horizontal support and resistance levels.

    Returns: (support_levels, resistance_levels)
    """
    if len(data) < 30:
        return [], []

    # Use last N bars (minimum 50 for ATR calculation)
    window = data.last_n(max(lookback, 50))
    if len(window) < 50:
        return [], []
    closes = window.closes
    highs = window.highs
    lows = window.lows
    volumes = window.volumes

    atr_vals = atr(window)
    current_atr = atr_vals[-1] if len(atr_vals) > 0 else 0

    # Find pivots - use ATR to determine pivot significance
    pivot_highs = find_pivot_highs(window)
    pivot_lows = find_pivot_lows(window)

    support_levels = []
    resistance_levels = []

    # Process resistance (pivot highs)
    for idx, price in pivot_highs:
        # Count how many times price approached this level (within ATR)
        touch_bars = []
        for i in range(len(window)):
            if abs(highs[i] - price) <= current_atr * atr_multiplier:
                touch_bars.append(i)

        if len(touch_bars) >= min_touches:
            confidence = compute_confidence(
                len(touch_bars), volumes, touch_bars,
                current_atr, price, len(window) - 1
            )
            level = SRLevel(
                price=price,
                level_type="resistance",
                confidence=confidence,
                touch_count=len(touch_bars),
                touch_bars=touch_bars,
                source="horizontal",
                timeframe=timeframe,
            )
            resistance_levels.append(level)

    # Process support (pivot lows)
    for idx, price in pivot_lows:
        touch_bars = []
        for i in range(len(window)):
            if abs(lows[i] - price) <= current_atr * atr_multiplier:
                touch_bars.append(i)

        if len(touch_bars) >= min_touches:
            confidence = compute_confidence(
                len(touch_bars), volumes, touch_bars,
                current_atr, price, len(window) - 1
            )
            level = SRLevel(
                price=price,
                level_type="support",
                confidence=confidence,
                touch_count=len(touch_bars),
                touch_bars=touch_bars,
                source="horizontal",
                timeframe=timeframe,
            )
            support_levels.append(level)

    # Merge nearby levels
    support_levels = merge_nearby_levels(support_levels, merge_threshold_pct)
    resistance_levels = merge_nearby_levels(resistance_levels, merge_threshold_pct)

    # Sort by confidence
    support_levels.sort(key=lambda x: x.confidence, reverse=True)
    resistance_levels.sort(key=lambda x: x.confidence, reverse=True)

    return support_levels, resistance_levels