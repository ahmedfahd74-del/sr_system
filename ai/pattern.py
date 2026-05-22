# sr_system/ai/pattern.py
"""Pattern recognition for market conditions."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
import numpy as np
from data.ohlcv import OHLCVData
from ai.features import MarketFeatures, extract_all_features, detect_volume_buildup, detect_range_contraction


class PatternType(Enum):
    """Market pattern types."""
    CONSOLIDATION = "consolidation"
    BREAKOUT_IMMINENT = "breakout_imminent"
    BREAKOUT_ACTIVE = "breakout_active"
    FALSE_BREAKOUT = "false_breakout"
    TREND_CONTINUATION = "trend_continuation"
    TREND_REVERSAL = "trend_reversal"
    UNKNOWN = "unknown"


class Action(Enum):
    """Suggested trading actions."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WAIT = "wait"


@dataclass
class PatternResult:
    """Result of pattern recognition."""
    pattern_type: PatternType
    confidence: float          # 0-100
    action: Action
    action_reason: str
    breakout_direction: str    # "up", "down", or "" if no breakout
    estimated_range_expansion: float  # Expected % move if breakout
    time_horizon: str          # "immediate", "short", "medium"
    features: Optional[MarketFeatures] = None


def detect_consolidation_pattern(features: MarketFeatures) -> Tuple[bool, float]:
    """
    Detect if price is in consolidation.

    Returns: (is_consolidation, consolidation_score)
    """
    # Multiple conditions for consolidation
    conditions_met = 0

    # 1. Range narrowing
    if features.range_narrowing < 0.8:
        conditions_met += 1

    # 2. High consolidation score
    if features.consolidation_score > 40:
        conditions_met += 1

    # 3. Volume uniformity (low volatility in volume)
    if features.volume_uniformity > 0.3:
        conditions_met += 1

    # 4. Low ATR ratio (stable volatility)
    if features.atr_ratio < 1.2:
        conditions_met += 1

    is_consolidation = conditions_met >= 2

    score = features.consolidation_score

    return is_consolidation, score


def detect_breakout_imminent(features: MarketFeatures, data: OHLCVData) -> Tuple[bool, float, str]:
    """
    Detect if breakout is imminent.

    Returns: (is_imminent, confidence, direction)
    """
    if len(data) < 20:
        return False, 0, ""

    conditions_met = 0
    direction = ""

    # 1. Consolidation with compression
    if features.range_narrowing < 0.7:
        conditions_met += 1

    # 2. Volume starting to build
    if features.volume_ratio > 1.2:
        conditions_met += 1

    # 3. ATR increasing (volatility picking up)
    if features.atr_ratio > 1.1:
        conditions_met += 1

    # 4. Symmetry breaking (asymmetry indicates direction)
    if features.symmetry_score < 60:
        conditions_met += 1

    # Determine direction from momentum and trend
    if features.momentum > 2 and features.trend_direction == "up":
        direction = "up"
        conditions_met += 1
    elif features.momentum < -2 and features.trend_direction == "down":
        direction = "down"
        conditions_met += 1

    is_imminent = conditions_met >= 3
    confidence = min(conditions_met * 20, 100)

    return is_imminent, confidence, direction


def detect_false_breakout(data: OHLCVData, features: MarketFeatures) -> Tuple[bool, float]:
    """
    Detect potential false breakout pattern.

    Returns: (is_false_breakout, confidence)
    """
    if len(data) < 10:
        return False, 0

    # Check for reversal after quick move
    recent_closes = data.closes[-5:]
    momentum_5 = ((recent_closes[-1] - recent_closes[0]) / recent_closes[0]) * 100 if recent_closes[0] != 0 else 0

    # If strong move but losing steam
    if abs(momentum_5) > 3:
        # Check for reversal in last 2 bars
        if len(recent_closes) >= 3:
            if momentum_5 > 0 and recent_closes[-1] < recent_closes[-2]:
                # Up move reversing
                return True, 60
            elif momentum_5 < 0 and recent_closes[-1] > recent_closes[-2]:
                # Down move reversing
                return True, 60

    # Volume divergence
    if features.volume_ratio > 1.8 and features.consolidation_score > 30:
        # High volume but still consolidating - potential trap
        return True, 50

    return False, 0


def detect_trend_continuation(features: MarketFeatures) -> Tuple[bool, float]:
    """
    Detect if current trend is likely to continue.

    Returns: (will_continue, confidence)
    """
    # Strong trend with healthy momentum
    if features.trend_strength > 40 and abs(features.momentum) > 1:
        return True, min(features.trend_strength, 80)

    # Low consolidation in strong trend
    if features.consolidation_score < 30 and features.trend_strength > 30:
        return True, features.trend_strength

    return False, 0


def analyze_pattern(data: OHLCVData, lookback: int = 50) -> PatternResult:
    """
    Analyze price data and determine current market pattern.

    Returns:
        PatternResult with pattern type, confidence, and suggested action
    """
    if len(data) < 20:
        return PatternResult(
            pattern_type=PatternType.UNKNOWN,
            confidence=0,
            action=Action.WAIT,
            action_reason="Insufficient data",
            breakout_direction="",
            estimated_range_expansion=0,
            time_horizon="short"
        )

    # Use last N bars for analysis
    window = data.last_n(lookback)

    # Extract features
    features = extract_all_features(window)

    # Run pattern detection checks
    is_consolidation, consol_score = detect_consolidation_pattern(features)
    breakout_imminent, breakout_conf, breakout_dir = detect_breakout_imminent(features, window)
    is_false_breakout, false_break_conf = detect_false_breakout(window, features)
    will_continue, continue_conf = detect_trend_continuation(features)

    # Determine pattern and action
    if is_false_breakout:
        pattern = PatternType.FALSE_BREAKOUT
        confidence = false_break_conf
        action = Action.SELL if breakout_dir == "up" else Action.BUY  # Opposite of failed direction
        reason = f"False breakout detected - reversal likely. Direction: {breakout_dir}"

    elif breakout_imminent:
        pattern = PatternType.BREAKOUT_IMMINENT
        confidence = breakout_conf
        if breakout_dir == "up":
            action = Action.BUY
            reason = "Breakout appears imminent to upside"
        else:
            action = Action.SELL
            reason = "Breakout appears imminent to downside"

    elif is_consolidation:
        pattern = PatternType.CONSOLIDATION
        confidence = consol_score
        action = Action.HOLD
        reason = f"Price consolidating. Consolidation score: {consol_score:.0f}"

    elif will_continue:
        pattern = PatternType.TREND_CONTINUATION
        confidence = continue_conf
        if features.trend_direction == "up":
            action = Action.BUY
            reason = "Trend continuation expected"
        else:
            action = Action.SELL
            reason = "Downtrend continuation expected"

    else:
        # Check for active breakout
        recent_range = (data.highs[-1] - data.lows[-1])
        avg_range = (data.highs[-20:] - data.lows[-20:]).mean()

        if recent_range > avg_range * 1.5:
            pattern = PatternType.BREAKOUT_ACTIVE
            confidence = 70
            action = Action.BUY if data.closes[-1] > data.opens[-1] else Action.SELL
            reason = "Active breakout in progress"
        else:
            pattern = PatternType.UNKNOWN
            confidence = 30
            action = Action.WAIT
            reason = "No clear pattern detected"

    # Estimate potential range expansion
    if pattern in [PatternType.BREAKOUT_IMMINENT, PatternType.CONSOLIDATION]:
        estimated_move = features.atr_current * 1.5
        current_price = data.closes[-1]
        range_expansion = (estimated_move / current_price) * 100 if current_price > 0 else 0
    elif pattern == PatternType.BREAKOUT_ACTIVE:
        range_expansion = features.atr_ratio * 50  # ATR ratio * base move
    else:
        range_expansion = 0

    # Time horizon
    if pattern == PatternType.BREAKOUT_ACTIVE:
        time_horizon = "immediate"
    elif is_consolidation and features.consolidation_score > 60:
        time_horizon = "medium"
    else:
        time_horizon = "short"

    return PatternResult(
        pattern_type=pattern,
        confidence=confidence,
        action=action,
        action_reason=reason,
        breakout_direction=breakout_dir,
        estimated_range_expansion=range_expansion,
        time_horizon=time_horizon,
        features=features
    )


def get_pattern_description(result: PatternResult) -> str:
    """Get a human-readable description of the pattern."""
    emoji_map = {
        PatternType.CONSOLIDATION: "📊",
        PatternType.BREAKOUT_IMMINENT: "⚡",
        PatternType.BREAKOUT_ACTIVE: "🚀",
        PatternType.FALSE_BREAKOUT: "⚠️",
        PatternType.TREND_CONTINUATION: "➡️",
        PatternType.TREND_REVERSAL: "🔄",
        PatternType.UNKNOWN: "❓",
    }

    emoji = emoji_map.get(result.pattern_type, "❓")

    return f"{emoji} {result.pattern_type.value.replace('_', ' ').title()}\n" \
           f"   Confidence: {result.confidence:.0f}%\n" \
           f"   Action: {result.action.value.upper()}\n" \
           f"   Reason: {result.action_reason}"