# sr_system/ai/signal_enhancer.py
"""Signal enhancement for entry timing and stop loss recommendations."""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from data.ohlcv import OHLCVData
from ai.features import extract_all_features, MarketFeatures


@dataclass
class EnhancedSignal:
    """Enhanced trading signal with entry/exit recommendations."""
    base_action: str           # BUY, SELL, HOLD
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    entry_confidence: float    # 0-100
    entry_zone_low: float
    entry_zone_high: float
    reasoning: str
    warnings: list             # Potential risks


def detect_candle_pattern_at_level(data: OHLCVData, level: float, lookback: int = 5) -> dict:
    """
    Analyze candle patterns when price approaches a level.

    Returns dict with pattern signals.
    """
    if len(data) < lookback:
        return {"signal": "neutral", "strength": 0}

    patterns = {
        "bullish_engulf": False,
        "bearish_engulf": False,
        "hammer": False,
        "shooting_star": False,
        "doji": False,
        "inside_bar": False,
    }

    # Check last few bars for patterns
    for i in range(-lookback, 0):
        idx = i if i != -1 else -1
        idx_prev = i - 1 if i > -lookback else -2

        if len(data) < abs(i) + 1:
            continue

        current_bar = data[-1] if i == -1 else data[i]
        prev_bar = data[idx_prev]

        # Simple engulfing detection
        if prev_bar.is_bearish and current_bar.is_bullish:
            if current_bar.close > prev_bar.open and current_bar.open < prev_bar.close:
                patterns["bullish_engulf"] = True
        elif prev_bar.is_bullish and current_bar.is_bearish:
            if current_bar.close < prev_bar.open and current_bar.open > prev_bar.close:
                patterns["bearish_engulf"] = True

        # Hammer / Shooting star (long wick relative to body)
        body = abs(current_bar.close - current_bar.open)
        upper_wick = current_bar.high - max(current_bar.open, current_bar.close)
        lower_wick = min(current_bar.open, current_bar.close) - current_bar.low

        if lower_wick > body * 2 and upper_wick < body:
            patterns["hammer"] = True
        elif upper_wick > body * 2 and lower_wick < body:
            patterns["shooting_star"] = True

        # Doji (very small body)
        if body < (current_bar.high - current_bar.low) * 0.1:
            patterns["doji"] = True

    # Aggregate signal
    signal_strength = 0
    if patterns["bullish_engulf"] or patterns["hammer"]:
        signal_strength = 70
    elif patterns["bearish_engulf"] or patterns["shooting_star"]:
        signal_strength = 70
    elif patterns["doji"]:
        signal_strength = 40

    signal = "bullish" if patterns["bullish_engulf"] or patterns["hammer"] else \
             "bearish" if patterns["bearish_engulf"] or patterns["shooting_star"] else \
             "neutral"

    return {
        "signal": signal,
        "strength": signal_strength,
        "patterns": patterns
    }


def estimate_volatility_expansion(data: OHLCVData) -> float:
    """
    Estimate potential volatility expansion after consolidation.

    Returns multiplier for expected range.
    """
    features = extract_all_features(data)

    # High compression followed by buildup = potential expansion
    if features.range_narrowing < 0.6 and features.volume_ratio > 1.3:
        return 2.0  # Expect 2x current range

    if features.range_narrowing < 0.8 and features.volume_ratio > 1.1:
        return 1.5

    return 1.2  # Normal expansion


def calculate_stop_loss(
    entry_price: float,
    direction: str,
    atr: float,
    recent_lows: np.ndarray,
    recent_highs: np.ndarray
) -> float:
    """
    Calculate stop loss based on recent structure.

    Args:
        entry_price: Proposed entry price
        direction: "long" or "short"
        atr: Current ATR value
        recent_lows: Recent low prices
        recent_highs: Recent high prices

    Returns:
        Stop loss price
    """
    if direction == "long":
        # For long, stop below recent lows or 1-1.5 ATR
        recent_swing_low = recent_lows[-20:].min()
        atr_stop = entry_price - atr * 1.5

        # Use whichever is closer (more conservative)
        return max(recent_swing_low, atr_stop)

    else:  # short
        recent_swing_high = recent_highs[-20:].max()
        atr_stop = entry_price + atr * 1.5

        return min(recent_swing_high, atr_stop)


def calculate_take_profit(
    entry_price: float,
    stop_loss: float,
    risk_reward_target: float = 2.0
) -> float:
    """
    Calculate take profit based on risk/reward ratio.

    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        risk_reward_target: Desired R:R ratio

    Returns:
        Take profit price
    """
    risk = abs(entry_price - stop_loss)
    reward = risk * risk_reward_target

    return entry_price + reward  # Assuming long direction, adjust as needed


def enhance_signal(
    data: OHLCVData,
    sr_level: float,
    direction: str,  # "support" or "resistance"
    current_price: float,
    atr: Optional[float] = None
) -> EnhancedSignal:
    """
    Enhance a trading signal with entry timing and risk management.

    Args:
        data: OHLCV price data
        sr_level: S/R level price
        direction: "support" or "resistance"
        current_price: Current market price
        atr: ATR value (computed if not provided)

    Returns:
        EnhancedSignal with entry/exit recommendations
    """
    if len(data) < 20:
        return EnhancedSignal(
            base_action="HOLD",
            entry_price=0,
            stop_loss=0,
            take_profit=0,
            risk_reward_ratio=0,
            entry_confidence=0,
            entry_zone_low=0,
            entry_zone_high=0,
            reasoning="Insufficient data",
            warnings=["Not enough price history"]
        )

    # Compute ATR if not provided
    from detection.horizontal import atr as compute_atr
    if atr is None:
        atr_vals = compute_atr(data)
        atr = atr_vals[-1] if len(atr_vals) > 0 else (data.highs[-1] - data.lows[-1])

    # Extract features
    features = extract_all_features(data)

    # Determine base action based on S/R type and price position
    if direction == "support":
        base_action = "BUY"
        entry_offset = atr * 0.3  # Buy slightly above support
        expected_move = "up"
    else:  # resistance
        base_action = "SELL"
        entry_offset = atr * 0.3  # Sell slightly below resistance
        expected_move = "down"

    # Entry price
    if direction == "support":
        entry_price = sr_level + entry_offset
        entry_zone_low = sr_level
        entry_zone_high = entry_price + atr * 0.2
    else:
        entry_price = sr_level - entry_offset
        entry_zone_low = entry_price - atr * 0.2
        entry_zone_high = sr_level

    # Stop loss
    if base_action == "BUY":
        stop_loss = calculate_stop_loss(
            entry_price, "long", atr,
            data.lows, data.highs
        )
    else:
        stop_loss = calculate_stop_loss(
            entry_price, "short", atr,
            data.lows, data.highs
        )

    # Take profit
    risk = abs(entry_price - stop_loss)
    # Use ATR-based expansion estimate
    expansion_mult = estimate_volatility_expansion(data)
    expected_move_size = atr * expansion_mult * 2  # 2x expansion for target

    if base_action == "BUY":
        take_profit = entry_price + expected_move_size
    else:
        take_profit = entry_price - expected_move_size

    # Risk/Reward ratio
    reward = abs(take_profit - entry_price)
    risk_reward = reward / risk if risk > 0 else 0

    # Entry confidence
    confidence_factors = []

    # Distance from level
    distance_pct = abs(current_price - sr_level) / current_price * 100
    if distance_pct < 1.0:
        confidence_factors.append(20)
    elif distance_pct < 2.0:
        confidence_factors.append(10)

    # Candle pattern at level
    candle_signal = detect_candle_pattern_at_level(data, sr_level)
    confidence_factors.append(candle_signal["strength"])

    # Volume confirmation
    if features.volume_ratio > 1.2:
        confidence_factors.append(15)

    # Trend alignment
    if (base_action == "BUY" and features.trend_direction == "up") or \
       (base_action == "SELL" and features.trend_direction == "down"):
        confidence_factors.append(15)

    entry_confidence = min(sum(confidence_factors), 100)

    # Warnings
    warnings = []

    if features.atr_ratio > 1.5:
        warnings.append("High volatility - wider stops recommended")

    if features.consolidation_score > 50:
        warnings.append("Consolidation phase - breakout may be imminent")

    if candle_signal["patterns"].get("doji"):
        warnings.append("Doji candle - uncertainty at level")

    # Reasoning
    reasoning = f"{base_action} at {direction} level ${sr_level:.2f}. "
    reasoning += f"ATR: ${atr:.2f}, Risk/Reward: {risk_reward:.1f}:1. "
    reasoning += f"Pattern: {candle_signal['signal']}"

    return EnhancedSignal(
        base_action=base_action,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward_ratio=risk_reward,
        entry_confidence=entry_confidence,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        reasoning=reasoning,
        warnings=warnings
    )


def get_signal_summary(signal: EnhancedSignal) -> str:
    """Get a formatted summary of the enhanced signal."""
    return f"""
📋 SIGNAL ENHANCEMENT SUMMARY
{'='*40}
Action: {signal.base_action}
Entry Zone: ${signal.entry_zone_low:.2f} - ${signal.entry_zone_high:.2f}
Entry Price: ${signal.entry_price:.2f}
Stop Loss: ${signal.stop_loss:.2f}
Take Profit: ${signal.take_profit:.2f}
Risk/Reward: {signal.risk_reward_ratio:.1f}:1
Confidence: {signal.entry_confidence:.0f}%

Reasoning: {signal.reasoning}
""" + (f"\n⚠️  Warnings: {', '.join(signal.warnings)}" if signal.warnings else "")