# sr_system/ai/features.py
"""Feature extraction utilities for AI pattern recognition."""

from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np
from data.ohlcv import OHLCVData
from detection.horizontal import atr


@dataclass
class MarketFeatures:
    """Extracted market features for pattern recognition."""
    # Volatility features
    atr_current: float
    atr_percentile: float        # Current ATR vs 20-bar ATR
    atr_ratio: float             # Current ATR / Average ATR
    range_compression_ratio: float  # Recent range / Average range

    # Volume features
    volume_ratio: float          # Recent volume / Average volume
    volume_cv: float             # Volume coefficient of variation
    volume_uniformity: float     # 1 - normalized CV (1.0 = perfect uniformity)

    # Price action features
    momentum: float              # % change over lookback
    range_narrowing: float       # 5-bar range vs 20-bar range ratio
    body_ratio_avg: float        # Average candle body / range

    # Trend features
    adx: float                  # Directional index (trend strength)
    trend_direction: str        # "up", "down", "neutral"
    trend_strength: float       # 0-100

    # Pattern features
    consolidation_score: float  # 0-100, how compressed price is
    symmetry_score: float       # How symmetric the consolidation is


def compute_atr_features(data: OHLCVData, period: int = 14) -> Tuple[float, float, float]:
    """
    Compute ATR-based volatility features.

    Returns: (atr_current, atr_percentile, atr_ratio)
    """
    atr_vals = atr(data, period)
    atr_current = atr_vals[-1] if len(atr_vals) > 0 else 0

    # ATR percentile
    if len(atr_vals) >= 20:
        atr_percentile = (atr_current / np.percentile(atr_vals, 50)) * 50
        atr_avg = atr_vals[-20:].mean()
    else:
        atr_avg = atr_vals.mean() if len(atr_vals) > 0 else 1
        atr_percentile = 50

    atr_ratio = atr_current / atr_avg if atr_avg > 0 else 1

    return atr_current, atr_percentile, atr_ratio


def compute_range_compression(data: OHLCVData, lookback: int = 20) -> float:
    """
    Compute price range compression ratio.

    Returns ratio of recent range to average range.
    """
    if len(data) < lookback:
        return 1.0

    recent_range = (data.highs[-lookback:] - data.lows[-lookback:]).mean()
    older_range = (data.highs[:-lookback] - data.lows[:-lookback]).mean()

    if older_range == 0:
        return 1.0

    return recent_range / older_range


def compute_volume_features(data: OHLCVData, lookback: int = 20) -> Tuple[float, float, float]:
    """
    Compute volume-based features.

    Returns: (volume_ratio, volume_cv, volume_uniformity)
    """
    if len(data) < 5:
        return 1.0, 1.0, 0.0

    volumes = data.volumes[-lookback:]

    # Volume ratio
    recent_vol = volumes[-5:].mean()
    older_vol = volumes[:-5].mean() if len(volumes) > 5 else recent_vol
    volume_ratio = recent_vol / older_vol if older_vol > 0 else 1.0

    # Coefficient of variation
    volume_cv = volumes.std() / volumes.mean() if volumes.mean() > 0 else 1.0

    # Volume uniformity (inverse of CV, normalized)
    volume_uniformity = max(0, 1 - volume_cv)

    return volume_ratio, volume_cv, volume_uniformity


def compute_momentum(data: OHLCVData, lookback: int = 10) -> float:
    """Compute price momentum as % change."""
    if len(data) < lookback:
        return 0.0

    current_close = data.closes[-1]
    past_close = data.closes[-lookback]

    if past_close == 0:
        return 0.0

    return ((current_close - past_close) / past_close) * 100


def compute_range_narrowing(data: OHLCVData) -> float:
    """
    Compute range narrowing trend.

    Returns ratio of 5-bar avg range to 20-bar avg range.
    """
    if len(data) < 20:
        return 1.0

    ranges = data.highs - data.lows

    avg_5 = ranges[-5:].mean()
    avg_20 = ranges[-20:].mean()

    if avg_20 == 0:
        return 1.0

    return avg_5 / avg_20


def compute_body_ratio(data: OHLCVData, lookback: int = 20) -> float:
    """Compute average candle body to range ratio."""
    if len(data) < lookback:
        return 0.5

    bodies = np.abs(data.closes[-lookback:] - data.opens[-lookback:])
    ranges = data.highs[-lookback:] - data.lows[-lookback:]

    # Avoid division by zero
    ranges = np.where(ranges == 0, 1, ranges)

    ratios = bodies / ranges

    return np.mean(ratios)


def compute_adx(data: OHLCVData, period: int = 14) -> Tuple[float, str, float]:
    """
    Compute ADX-like trend strength measure.

    Returns: (adx_value, direction, strength)
    """
    if len(data) < period + 1:
        return 0.0, "neutral", 0.0

    closes = data.closes
    deltas = np.diff(closes)

    pos_dm = np.maximum(deltas, 0)
    neg_dm = np.maximum(-deltas, 0)

    # Smooth DMs
    alpha = 2 / (period + 1)
    smoothed_pos = np.zeros(len(pos_dm))
    smoothed_neg = np.zeros(len(neg_dm))

    smoothed_pos[0] = pos_dm[0]
    smoothed_neg[0] = neg_dm[0]

    for i in range(1, len(pos_dm)):
        smoothed_pos[i] = smoothed_pos[i-1] * (1 - alpha) + pos_dm[i] * alpha
        smoothed_neg[i] = smoothed_neg[i-1] * (1 - alpha) + neg_dm[i] * alpha

    # Compute DI
    tr_vals = atr(data, period)
    # tr_vals has same length as closes, but smoothed_pos/neg are len(closes)-1
    tr_vals = tr_vals[:-1]  # Align lengths
    smoothed_tr = np.zeros(len(tr_vals))
    smoothed_tr[0] = tr_vals[0]
    for i in range(1, len(tr_vals)):
        smoothed_tr[i] = smoothed_tr[i-1] * (1 - alpha) + tr_vals[i] * alpha

    # Avoid division by zero
    pos_di = np.zeros(len(smoothed_tr))
    neg_di = np.zeros(len(smoothed_tr))

    for i in range(len(smoothed_tr)):
        if smoothed_tr[i] > 0:
            pos_di[i] = (smoothed_pos[i] / smoothed_tr[i]) * 100
            neg_di[i] = (smoothed_neg[i] / smoothed_tr[i]) * 100

    # DX
    di_sum = pos_di + neg_di
    dx = np.zeros(len(pos_di))
    for i in range(len(dx)):
        if di_sum[i] > 0:
            dx[i] = abs(pos_di[i] - neg_di[i]) / di_sum[i] * 100

    # ADX (smoothed DX)
    adx_value = dx[-period:].mean() if len(dx) >= period else 0

    # Direction
    pos_avg = pos_di[-period:].mean() if len(pos_di) >= period else 0
    neg_avg = neg_di[-period:].mean() if len(neg_di) >= period else 0

    if pos_avg > neg_avg * 1.25:
        direction = "up"
    elif neg_avg > pos_avg * 1.25:
        direction = "down"
    else:
        direction = "neutral"

    strength = min(adx_value, 100)

    return adx_value, direction, strength


def compute_consolidation_score(data: OHLCVData) -> float:
    """
    Compute consolidation score (0-100).

    Based on:
    - Range compression
    - Volume uniformity
    - Symmetry of ranges
    """
    if len(data) < 20:
        return 0.0

    # Range compression component
    range_ratio = compute_range_narrowing(data)
    range_score = max(0, (1 - range_ratio) * 50)  # Lower ratio = higher compression

    # Volume uniformity component
    _, _, vol_uniformity = compute_volume_features(data)
    vol_score = vol_uniformity * 30

    # Symmetry component - check if compression is consistent
    ranges = data.highs[-10:] - data.lows[-10:]
    if len(ranges) > 1:
        range_std = ranges.std()
        range_mean = ranges.mean()
        symmetry = 1 - (range_std / range_mean) if range_mean > 0 else 0
        symmetry_score = max(0, symmetry * 20)
    else:
        symmetry_score = 0

    total_score = range_score + vol_score + symmetry_score

    return min(total_score, 100)


def compute_symmetry_score(data: OHLCVData) -> float:
    """
    Compute symmetry score of recent price action.

    Checks if recent bars have similar up/down ranges.
    """
    if len(data) < 10:
        return 0.0

    closes = data.closes[-10:]
    highs = data.highs[-10:]
    lows = data.lows[-10:]

    # Compute directional moves
    up_moves = []
    down_moves = []

    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            up_moves.append(closes[i] - closes[i-1])
        elif closes[i] < closes[i-1]:
            down_moves.append(closes[i-1] - closes[i])

    if not up_moves or not down_moves:
        return 30.0  # No clear direction = partial symmetry

    avg_up = np.mean(up_moves)
    avg_down = np.mean(down_moves)

    # Symmetry: how close are up/down moves
    if avg_up == 0 or avg_down == 0:
        return 30.0

    ratio = min(avg_up, avg_down) / max(avg_up, avg_down)
    symmetry = ratio * 100

    return symmetry


def extract_all_features(data: OHLCVData) -> MarketFeatures:
    """
    Extract all market features for pattern recognition.

    Returns:
        MarketFeatures dataclass with all computed features
    """
    atr_current, atr_percentile, atr_ratio = compute_atr_features(data)
    volume_ratio, volume_cv, volume_uniformity = compute_volume_features(data)
    range_compression = compute_range_compression(data)
    momentum = compute_momentum(data)
    range_narrowing = compute_range_narrowing(data)
    body_ratio = compute_body_ratio(data)
    adx, direction, strength = compute_adx(data)
    consolidation_score = compute_consolidation_score(data)
    symmetry_score = compute_symmetry_score(data)

    return MarketFeatures(
        atr_current=atr_current,
        atr_percentile=atr_percentile,
        atr_ratio=atr_ratio,
        range_compression_ratio=range_compression,
        volume_ratio=volume_ratio,
        volume_cv=volume_cv,
        volume_uniformity=volume_uniformity,
        momentum=momentum,
        range_narrowing=range_narrowing,
        body_ratio_avg=body_ratio,
        adx=adx,
        trend_direction=direction,
        trend_strength=strength,
        consolidation_score=consolidation_score,
        symmetry_score=symmetry_score,
    )


def detect_volume_buildup(data: OHLCVData, threshold: float = 1.5) -> bool:
    """
    Detect if volume is building up (potential breakout signal).

    Returns True if recent volume is significantly higher than average.
    """
    if len(data) < 20:
        return False

    recent_vol = data.volumes[-5:].mean()
    avg_vol = data.volumes[-20:].mean()

    return recent_vol > avg_vol * threshold


def detect_range_contraction(data: OHLCVData, threshold: float = 0.7) -> bool:
    """
    Detect if price range is contracting.

    Returns True if recent range is significantly smaller than average.
    """
    if len(data) < 20:
        return False

    recent_range = (data.highs[-5:] - data.lows[-5:]).mean()
    avg_range = (data.highs[-20:] - data.lows[-20:]).mean()

    return recent_range < avg_range * threshold