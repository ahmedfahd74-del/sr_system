# sr_system/detection/fractal.py
"""Bill Williams Fractal-based Support & Resistance detection."""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from data.ohlcv import OHLCVData


@dataclass
class FractalLevel:
    """A fractal-based S/R level."""
    price: float
    level_type: str          # "support" or "resistance"
    fractal_type: str        # "up" or "down" fractal
    bar_index: int           # Index of the pivot bar
    confidence: float        # 0-100
    lookback: int            # Period used for fractal detection
    source: str = "fractal"
    timeframe: str = "1D"

    @property
    def is_support(self) -> bool:
        return self.level_type == "support"

    @property
    def is_resistance(self) -> bool:
        return self.level_type == "resistance"


def find_up_fractals(data: OHLCVData, period: int = 2) -> List[int]:
    """
    Find Bill Williams up fractals (sell fractal).
    An up fractal forms when a middle bar has a higher high than
    the 'period' bars before and after it.

    Args:
        data: OHLCV data
        period: Number of bars to check on each side (default 2 = 5-bar fractal)

    Returns:
        List of bar indices where up fractals formed
    """
    highs = data.highs
    fractals = []

    for i in range(period, len(highs) - period):
        # Check if current high is highest
        is_highest = True
        left = max(0, i - period)
        right = min(len(highs), i + period + 1)
        for j in range(left, right):
            if j != i and highs[j] >= highs[i]:
                is_highest = False
                break

        if is_highest:
            fractals.append(i)

    return fractals


def find_down_fractals(data: OHLCVData, period: int = 2) -> List[int]:
    """
    Find Bill Williams down fractals (buy fractal).
    A down fractal forms when a middle bar has a lower low than
    the 'period' bars before and after it.

    Args:
        data: OHLCV data
        period: Number of bars to check on each side (default 2 = 5-bar fractal)

    Returns:
        List of bar indices where down fractals formed
    """
    lows = data.lows
    fractals = []

    for i in range(period, len(lows) - period):
        # Check if current low is lowest
        is_lowest = True
        left = max(0, i - period)
        right = min(len(lows), i + period + 1)
        for j in range(left, right):
            if j != i and lows[j] <= lows[i]:
                is_lowest = False
                break

        if is_lowest:
            fractals.append(i)

    return fractals


def find_all_fractals(data: OHLCVData, period: int = 2) -> Tuple[List[int], List[int]]:
    """Find both up and down fractals."""
    return find_down_fractals(data, period), find_up_fractals(data, period)


def compute_fractal_strength(data: OHLCVData, fractal_idx: int, fractal_type: str, period: int = 2) -> float:
    """
    Compute the strength/confidence of a fractal level.
    Considers:
    - How much the fractal bar protrudes beyond neighbors (height)
    - Volume at the fractal bar
    - Recency of the fractal
    """
    if fractal_type == "up":
        fractal_price = data.highs[fractal_idx]
        neighbor_highs = list(data.highs[max(0, fractal_idx - period):fractal_idx]) + \
                         list(data.highs[fractal_idx + 1:min(len(data), fractal_idx + period + 1)])
    else:
        fractal_price = data.lows[fractal_idx]
        neighbor_lows = list(data.lows[max(0, fractal_idx - period):fractal_idx]) + \
                        list(data.lows[fractal_idx + 1:min(len(data), fractal_idx + period + 1)])
        neighbor_highs = neighbor_lows  # Use same neighbor concept

    if not neighbor_highs:
        return 50  # Default

    avg_neighbor = np.mean(neighbor_highs)

    # Height score: how much does fractal protrude
    if fractal_type == "up":
        protrusion = fractal_price - avg_neighbor
        height_score = min(protrusion / avg_neighbor * 1000, 50)  # Cap at 50
    else:
        protrusion = avg_neighbor - fractal_price
        height_score = min(protrusion / avg_neighbor * 1000, 50)

    # Volume score
    vol = data.volumes[fractal_idx] if fractal_idx < len(data.volumes) else 0
    avg_vol = np.mean(data.volumes) if len(data.volumes) > 0 else 1
    vol_score = min(vol / avg_vol * 25, 25) if avg_vol > 0 else 0  # Cap at 25

    # Recency score (max 25)
    bars_ago = len(data) - 1 - fractal_idx
    recency_score = max(0, 25 - bars_ago * 0.5)

    return height_score + vol_score + recency_score


def detect_fractal_sr(
    data: OHLCVData,
    period: int = 2,
    lookback: int = 100,
    timeframe: str = "1D",
) -> Tuple[List[FractalLevel], List[FractalLevel]]:
    """
    Detect S/R levels using Bill Williams fractals.

    Args:
        data: OHLCV data
        period: Fractal period (2 = 5-bar, 3 = 7-bar, etc.)
        lookback: Number of bars to analyze
        timeframe: Timeframe identifier

    Returns:
        (support_levels, resistance_levels)
    """
    if len(data) < period * 2 + 1:
        return [], []

    window = data.last_n(max(lookback, period * 4))
    if len(window) < period * 2 + 1:
        return [], []

    # Find fractals
    down_fractals = find_down_fractals(window, period)  # Buy fractals = support
    up_fractals = find_up_fractals(window, period)      # Sell fractals = resistance

    support_levels = []
    resistance_levels = []

    # Create support levels from down fractals
    for idx in down_fractals:
        strength = compute_fractal_strength(window, idx, "down", period)
        level = FractalLevel(
            price=window.lows[idx],
            level_type="support",
            fractal_type="down",
            bar_index=idx,
            confidence=strength,
            lookback=period,
            source="fractal",
            timeframe=timeframe,
        )
        support_levels.append(level)

    # Create resistance levels from up fractals
    for idx in up_fractals:
        strength = compute_fractal_strength(window, idx, "up", period)
        level = FractalLevel(
            price=window.highs[idx],
            level_type="resistance",
            fractal_type="up",
            bar_index=idx,
            confidence=strength,
            lookback=period,
            source="fractal",
            timeframe=timeframe,
        )
        resistance_levels.append(level)

    # Sort by confidence
    support_levels.sort(key=lambda x: x.confidence, reverse=True)
    resistance_levels.sort(key=lambda x: x.confidence, reverse=True)

    return support_levels, resistance_levels


def merge_fractal_levels(
    levels: List[FractalLevel],
    price_threshold_pct: float = 0.5
) -> List[FractalLevel]:
    """
    Merge fractal levels that are within a price threshold of each other.

    Args:
        levels: List of fractal levels
        price_threshold_pct: Maximum percentage difference to merge

    Returns:
        Merged list of fractal levels
    """
    if not levels:
        return []

    # Group by type first
    by_type = {"support": [], "resistance": []}
    for level in levels:
        by_type[level.level_type].append(level)

    merged = []
    for level_type, type_levels in by_type.items():
        if not type_levels:
            continue

        sorted_levels = sorted(type_levels, key=lambda x: x.price)
        current_group = [sorted_levels[0]]

        for level in sorted_levels[1:]:
            if len(current_group) == 0:
                current_group.append(level)
                continue

            last = current_group[-1]
            price_diff_pct = abs(level.price - last.price) / last.price * 100

            if price_diff_pct <= price_threshold_pct:
                # Merge: keep highest confidence, combine bars
                current_group.append(level)
            else:
                # Finalize current group
                merged.extend(_consolidate_fractal_group(current_group))
                current_group = [level]

        # Don't forget last group
        if current_group:
            merged.extend(_consolidate_fractal_group(current_group))

    merged.sort(key=lambda x: x.confidence, reverse=True)
    return merged


def _consolidate_fractal_group(group: List[FractalLevel]) -> List[FractalLevel]:
    """Consolidate a group of nearby fractals into a single level."""
    if not group:
        return []

    if len(group) == 1:
        return group

    # Use the most recent, highest confidence fractal as the anchor
    most_recent = max(group, key=lambda x: x.bar_index)
    highest_conf = max(group, key=lambda x: x.confidence)

    # Create merged level
    merged = FractalLevel(
        price=highest_conf.price,  # Use highest confidence price
        level_type=group[0].level_type,
        fractal_type=group[0].fractal_type,
        bar_index=most_recent.bar_index,
        confidence=max(g.confidence for g in group),  # Boost for multiple fractals
        lookback=group[0].lookback,
        source=f"fractal_{len(group)}",
        timeframe=group[0].timeframe,
    )

    return [merged]


def get_fractal_channels(data: OHLCVData, period: int = 2, lookback: int = 50) -> Tuple[List[FractalLevel], List[FractalLevel]]:
    """
    Detect fractal-based channels (parallel support/resistance lines).

    Returns parallel channel lines based on consecutive fractal alignment.
    """
    window = data.last_n(max(lookback, period * 4))

    # Find all fractals
    down_fracs = find_down_fractals(window, period)
    up_fracs = find_up_fractals(window, period)

    support_lines = []
    resistance_lines = []

    # Simple channel detection: group consecutive fractals with similar slopes
    if len(down_fracs) >= 2:
        for i in range(len(down_fracs) - 1):
            p1_bar = down_fracs[i]
            p2_bar = down_fracs[i + 1]
            if p2_bar - p1_bar <= period * 3:  # Not too far apart
                slope = (window.lows[p2_bar] - window.lows[p1_bar]) / (p2_bar - p1_bar)
                if abs(slope) < window.closes.mean() * 0.01:  # Reasonably flat
                    level = FractalLevel(
                        price=window.lows[p1_bar],
                        level_type="support",
                        fractal_type="down",
                        bar_index=p1_bar,
                        confidence=50 + (10 * (i == 0)),  # Higher for recent
                        lookback=period,
                        source="fractal_channel",
                        timeframe="1D",
                    )
                    support_lines.append(level)

    if len(up_fracs) >= 2:
        for i in range(len(up_fracs) - 1):
            p1_bar = up_fracs[i]
            p2_bar = up_fracs[i + 1]
            if p2_bar - p1_bar <= period * 3:
                slope = (window.highs[p2_bar] - window.highs[p1_bar]) / (p2_bar - p1_bar)
                if abs(slope) < window.closes.mean() * 0.01:
                    level = FractalLevel(
                        price=window.highs[p1_bar],
                        level_type="resistance",
                        fractal_type="up",
                        bar_index=p1_bar,
                        confidence=50 + (10 * (i == 0)),
                        lookback=period,
                        source="fractal_channel",
                        timeframe="1D",
                    )
                    resistance_lines.append(level)

    return support_lines, resistance_lines