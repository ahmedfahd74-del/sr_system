# sr_system/detection/trendline.py
"""Diagonal Trendline Support & Resistance detection."""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
from data.ohlcv import OHLCVData
from detection.horizontal import SRLevel, find_pivot_highs, find_pivot_lows


@dataclass
class TrendlineLevel:
    """A diagonal S/R trendline."""
    price_start: float      # Price at start (oldest point)
    price_end: float        # Price at end (most recent point)
    slope: float            # Price change per bar
    touch_count: int
    touch_bars: List[int]   # Bar indices where price touched this line
    touch_prices: List[float]  # Actual prices at touch points
    confidence: float       # 0-100
    level_type: str         # "support" or "resistance"
    source: str = "trendline"
    timeframe: str = "1D"

    @property
    def current_price(self) -> float:
        """Extrapolated price at the most recent bar."""
        return self.price_end

    @property
    def is_support(self) -> bool:
        return self.level_type == "support"

    @property
    def is_resistance(self) -> bool:
        return self.level_type == "resistance"


def slope_from_points(x1: int, y1: float, x2: int, y2: float) -> float:
    """Calculate slope (price change per bar)."""
    if x2 == x1:
        return 0
    return (y2 - y1) / (x2 - x1)


def price_at_bar(trendline: TrendlineLevel, bar_idx: int, start_bar: int) -> float:
    """Get the trendline price at a specific bar index."""
    bars_since_start = bar_idx - start_bar
    return trendline.price_start + trendline.slope * bars_since_start


def fit_trendline(points: List[Tuple[int, float]], max_residual: float = 0.02) -> Optional[Tuple[float, float, float]]:
    """
    Fit a linear trendline to a list of (bar_index, price) points.
    Returns: (slope, intercept, r_squared) or None if fit is poor.
    """
    if len(points) < 2:
        return None

    indices = np.array([p[0] for p in points])
    prices = np.array([p[1] for p in points])

    # Linear regression: price = slope * index + intercept
    n = len(points)
    sum_x = indices.sum()
    sum_y = prices.sum()
    sum_xy = (indices * prices).sum()
    sum_x2 = (indices ** 2).sum()

    denom = n * sum_x2 - sum_x ** 2
    if abs(denom) < 1e-10:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n

    # Calculate R-squared
    y_mean = prices.mean()
    ss_tot = ((prices - y_mean) ** 2).sum()
    ss_res = ((prices - (slope * indices + intercept)) ** 2).sum()
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    # Check residual threshold
    avg_price = prices.mean()
    max_allowed_residual = avg_price * max_residual
    if ss_res / n > max_allowed_residual ** 2:
        return None

    return slope, intercept, r_squared


def find_swing_points(data: OHLCVData, left_bars: int = 3, right_bars: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Find shorter-term swing highs and lows for trendline fitting."""
    highs = data.highs
    lows = data.lows

    swing_highs = []
    swing_lows = []

    for i in range(left_bars, len(highs) - right_bars):
        # Swing high: higher than all bars in window
        if highs[i] == max(highs[max(0, i - left_bars):min(len(highs), i + right_bars + 1)]):
            swing_highs.append((i, highs[i]))
        # Swing low: lower than all bars in window
        if lows[i] == min(lows[max(0, i - left_bars):min(len(lows), i + right_bars + 1)]):
            swing_lows.append((i, lows[i]))

    return swing_highs, swing_lows


def connect_trendline_points(points: List[Tuple[int, float]], min_touches: int = 2,
                              slope_sensitivity: float = 0.001) -> List[TrendlineLevel]:
    """Connect consecutive swing points into trendlines."""
    if len(points) < min_touches:
        return []

    levels = []
    n = len(points)

    for i in range(n - 1):
        for j in range(i + 1, n):
            # Get all points between i and j (inclusive)
            segment_points = points[i:j + 1]
            if len(segment_points) < min_touches:
                continue

            # Fit trendline
            fit = fit_trendline(segment_points)
            if fit is None:
                continue

            slope, intercept, r_squared = fit

            # Check slope sensitivity - reject too flat or too steep
            avg_price = np.mean([p[1] for p in segment_points])
            if avg_price <= 0:
                continue
            slope_pct = abs(slope) / avg_price
            if slope_pct < slope_sensitivity:  # Too flat
                continue

            # Determine if support or resistance based on price action
            # If points are lows and price stays above trend -> support
            # If points are highs and price stays below trend -> resistance
            level_type = "support" if points[0][1] > 0 else "resistance"  # Will refine below

            level = TrendlineLevel(
                price_start=intercept + slope * segment_points[0][0],
                price_end=intercept + slope * segment_points[-1][0],
                slope=slope,
                touch_count=len(segment_points),
                touch_bars=[p[0] for p in segment_points],
                touch_prices=[p[1] for p in segment_points],
                confidence=r_squared * 100,
                level_type="support",  # Will be refined
                source="trendline",
                timeframe="1D",
            )

            levels.append(level)

    return levels


def refine_trendline_type(data: OHLCVData, level: TrendlineLevel) -> TrendlineLevel:
    """Refine whether trendline is support or resistance based on price interaction."""
    start_bar = level.touch_bars[0]
    end_bar = len(data) - 1

    above_count = 0
    below_count = 0

    for i in range(start_bar, end_bar + 1):
        trend_price = level.price_start + level.slope * (i - start_bar)
        if data.highs[i] > trend_price:
            above_count += 1
        if data.lows[i] < trend_price:
            below_count += 1

    # If price consistently stays above, it's support
    # If price consistently stays below, it's resistance
    if above_count > below_count * 1.5:
        level.level_type = "support"
    elif below_count > above_count * 1.5:
        level.level_type = "resistance"
    else:
        # Ambiguous - use slope direction as tiebreaker
        level.level_type = "support" if level.slope > 0 else "resistance"

    return level


def detect_trendline_sr(
    data: OHLCVData,
    lookback: int = 50,
    min_touches: int = 2,
    slope_sensitivity: float = 0.001,
    swing_window: int = 3,
    timeframe: str = "1D",
) -> Tuple[List[TrendlineLevel], List[TrendlineLevel]]:
    """
    Detect diagonal support and resistance trendlines.

    Returns: (support_trendlines, resistance_trendlines)
    """
    if len(data) < 20:
        return [], []

    window = data.last_n(max(lookback, 50))
    if len(window) < 20:
        return [], []

    # Find swing points
    swing_highs, swing_lows = find_swing_points(window, swing_window, swing_window)

    support_trendlines = []
    resistance_trendlines = []

    # Process swing lows -> potential support trendlines
    for level in connect_trendline_points(swing_lows, min_touches, slope_sensitivity):
        level = refine_trendline_type(window, level)
        level.timeframe = timeframe
        if level.level_type == "support":
            support_trendlines.append(level)
        else:
            resistance_trendlines.append(level)

    # Process swing highs -> potential resistance trendlines
    for level in connect_trendline_points(swing_highs, min_touches, slope_sensitivity):
        level = refine_trendline_type(window, level)
        level.timeframe = timeframe
        if level.level_type == "resistance":
            resistance_trendlines.append(level)
        else:
            support_trendlines.append(level)

    # Sort by confidence
    support_trendlines.sort(key=lambda x: x.confidence, reverse=True)
    resistance_trendlines.sort(key=lambda x: x.confidence, reverse=True)

    return support_trendlines, resistance_trendlines


def get_trendline_price_at_bar(level: TrendlineLevel, bar_idx: int, anchor_bar: int) -> float:
    """Calculate the price of a trendline at a given bar index."""
    return level.price_start + level.slope * (bar_idx - anchor_bar)


def merge_trendlines(levels: List[TrendlineLevel], price_threshold_pct: float = 1.0) -> List[TrendlineLevel]:
    """Merge trendlines with similar slopes and prices."""
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda x: x.slope)
    merged = [sorted_levels[0]]

    for level in sorted_levels[1:]:
        last = merged[-1]
        # Check if slopes are similar (within 20%)
        slope_diff = abs(level.slope - last.slope) / max(abs(last.slope), 1e-10)
        if slope_diff > 0.2:
            merged.append(level)
            continue

        # Check if current prices are within threshold
        price_diff_pct = abs(level.current_price - last.current_price) / last.current_price * 100
        if price_diff_pct > price_threshold_pct:
            merged.append(level)
        else:
            # Merge: combine touches, keep higher confidence
            last.touch_bars = sorted(list(set(last.touch_bars + level.touch_bars)))
            last.touch_count = len(last.touch_bars)
            last.touch_prices.extend(level.touch_prices)
            last.confidence = max(last.confidence, level.confidence)

    return merged