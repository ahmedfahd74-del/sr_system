# tests/test_ai_modules.py
"""Unit tests for AI modules (Phase 3)."""

import unittest
from datetime import datetime, timedelta
import numpy as np
from data.ohlcv import OHLCVData, OHLCV
from ai.features import (
    extract_all_features, compute_atr_features, compute_volume_features,
    compute_momentum, compute_range_narrowing, compute_adx,
    compute_consolidation_score, MarketFeatures
)
from ai.pattern import (
    analyze_pattern, PatternType, Action, PatternResult,
    detect_consolidation_pattern, detect_breakout_imminent,
    detect_false_breakout, detect_trend_continuation
)
from ai.signal_enhancer import (
    enhance_signal, EnhancedSignal, detect_candle_pattern_at_level,
    calculate_stop_loss, estimate_volatility_expansion
)


def create_test_data(num_bars=100, seed=42) -> OHLCVData:
    """Create test OHLCV data."""
    np.random.seed(seed)
    data = OHLCVData()
    base_price = 100.0
    base_time = datetime(2024, 1, 1)

    for i in range(num_bars):
        open_price = base_price + np.random.randn() * 0.5
        high = open_price + abs(np.random.randn()) * 1.0
        low = open_price - abs(np.random.randn()) * 1.0
        close = open_price + np.random.randn() * 0.5
        volume = 1000000 + np.random.randn() * 200000

        bar = OHLCV(
            timestamp=base_time + timedelta(hours=i),
            open=open_price, high=high, low=low,
            close=close, volume=volume
        )
        data.add(bar)
        base_price = close

    return data


def create_trending_data(num_bars=100) -> OHLCVData:
    """Create trending OHLCV data."""
    data = OHLCVData()
    base_price = 100.0
    base_time = datetime(2024, 1, 1)

    for i in range(num_bars):
        # Strong uptrend
        open_price = base_price
        close = open_price + 0.3 + np.random.randn() * 0.2
        high = max(open_price, close) + abs(np.random.randn()) * 0.3
        low = min(open_price, close) - abs(np.random.randn()) * 0.3
        volume = 1500000 + i * 1000

        bar = OHLCV(
            timestamp=base_time + timedelta(hours=i),
            open=open_price, high=high, low=low,
            close=close, volume=volume
        )
        data.add(bar)
        base_price = close

    return data


def create_consolidation_data(num_bars=60) -> OHLCVData:
    """Create consolidating OHLCV data (low range, stable volume)."""
    data = OHLCVData()
    base_price = 100.0
    base_time = datetime(2024, 1, 1)
    range_size = 1.0

    for i in range(num_bars):
        open_price = base_price + np.random.uniform(-range_size/4, range_size/4)
        close = base_price + np.random.uniform(-range_size/4, range_size/4)
        high = max(open_price, close) + np.random.uniform(0, range_size/4)
        low = min(open_price, close) - np.random.uniform(0, range_size/4)
        volume = 1000000  # Stable volume

        bar = OHLCV(
            timestamp=base_time + timedelta(hours=i),
            open=open_price, high=high, low=low,
            close=close, volume=volume
        )
        data.add(bar)

    return data


class TestMarketFeatures(unittest.TestCase):
    """Tests for MarketFeatures dataclass."""

    def test_features_extraction(self):
        """Test that features can be extracted from data."""
        data = create_test_data()
        features = extract_all_features(data)

        assert isinstance(features, MarketFeatures)
        assert features.atr_ratio >= 0
        assert features.volume_ratio >= 0
        assert isinstance(features.momentum, float)

    def test_trending_features(self):
        """Test features on trending data."""
        data = create_trending_data()
        features = extract_all_features(data)

        assert features.trend_direction == "up"
        assert features.momentum > 0

    def test_consolidation_features(self):
        """Test features on consolidating data."""
        data = create_consolidation_data()
        features = extract_all_features(data)

        assert features.consolidation_score > 0
        assert features.range_narrowing < 1.0  # Narrowing


class TestPatternDetection(unittest.TestCase):
    """Tests for pattern detection module."""

    def test_analyze_pattern_trending(self):
        """Test pattern analysis on trending data."""
        data = create_trending_data()
        result = analyze_pattern(data)

        assert isinstance(result, PatternResult)
        assert result.pattern_type in PatternType
        assert result.action in Action

    def test_analyze_pattern_consolidation(self):
        """Test pattern analysis on consolidating data."""
        data = create_consolidation_data()
        result = analyze_pattern(data)

        # Consolidation should be detected
        assert result.pattern_type in [PatternType.CONSOLIDATION, PatternType.BREAKOUT_IMMINENT]

    def test_analyze_pattern_insufficient_data(self):
        """Test pattern analysis with insufficient data."""
        data = create_test_data(num_bars=5)
        result = analyze_pattern(data)

        assert result.pattern_type == PatternType.UNKNOWN
        assert result.action == Action.WAIT

    def test_consolidation_detection(self):
        """Test consolidation pattern detection through analyze_pattern."""
        data = create_consolidation_data()
        result = analyze_pattern(data)

        assert isinstance(result, PatternResult)
        assert result.pattern_type in PatternType

    def test_breakout_imminent_detection(self):
        """Test breakout imminent detection through analyze_pattern."""
        # Create data that will trigger breakout imminent
        data = create_consolidation_data()
        result = analyze_pattern(data)

        assert isinstance(result, PatternResult)
        assert result.pattern_type in PatternType

    def test_trend_continuation_detection(self):
        """Test trend continuation detection through analyze_pattern."""
        data = create_trending_data()
        result = analyze_pattern(data)

        assert isinstance(result, PatternResult)
        # Trending data should either show trend continuation or breakout


class TestSignalEnhancer(unittest.TestCase):
    """Tests for signal enhancement module."""

    def test_enhance_signal_support(self):
        """Test signal enhancement for support level."""
        data = create_test_data()
        current_price = data.closes[-1]
        sr_level = current_price * 0.98  # Below current price

        signal = enhance_signal(data, sr_level, "support", current_price)

        assert isinstance(signal, EnhancedSignal)
        assert signal.base_action == "BUY"
        assert signal.entry_price > sr_level
        assert signal.stop_loss < sr_level
        assert signal.take_profit > signal.entry_price

    def test_enhance_signal_resistance(self):
        """Test signal enhancement for resistance level."""
        data = create_test_data()
        current_price = data.closes[-1]
        sr_level = current_price * 1.02  # Above current price

        signal = enhance_signal(data, sr_level, "resistance", current_price)

        assert isinstance(signal, EnhancedSignal)
        assert signal.base_action == "SELL"
        assert signal.entry_price < sr_level
        # For SELL, stop should be above entry (higher risk), TP below entry
        assert signal.take_profit < signal.entry_price

    def test_enhance_signal_insufficient_data(self):
        """Test signal enhancement with insufficient data."""
        data = create_test_data(num_bars=10)
        current_price = data.closes[-1]
        sr_level = current_price * 0.98

        signal = enhance_signal(data, sr_level, "support", current_price)

        assert signal.base_action == "HOLD"
        assert signal.entry_confidence == 0

    def test_calculate_stop_loss_long(self):
        """Test stop loss calculation for long positions."""
        entry_price = 100.0
        atr = 2.0
        recent_lows = np.array([95, 96, 97, 98, 99, 100, 101, 102])
        recent_highs = np.array([105, 106, 107, 108, 109, 110])

        stop = calculate_stop_loss(entry_price, "long", atr, recent_lows, recent_highs)

        assert stop < entry_price
        assert stop > entry_price - atr * 2

    def test_calculate_stop_loss_short(self):
        """Test stop loss calculation for short positions."""
        entry_price = 100.0
        atr = 2.0
        recent_lows = np.array([95, 96, 97, 98, 99, 100])
        recent_highs = np.array([105, 106, 107, 108, 109, 110])

        stop = calculate_stop_loss(entry_price, "short", atr, recent_lows, recent_highs)

        assert stop > entry_price
        assert stop < entry_price + atr * 2

    def test_candle_pattern_detection(self):
        """Test candle pattern detection."""
        data = create_test_data()
        level = data.closes[-10]

        result = detect_candle_pattern_at_level(data, level)

        assert "signal" in result
        assert "strength" in result
        assert result["signal"] in ["bullish", "bearish", "neutral"]

    def test_volatility_expansion_estimation(self):
        """Test volatility expansion estimation."""
        # Consolidation with high volume should indicate expansion
        consolidating = create_consolidation_data()
        expansion = estimate_volatility_expansion(consolidating)

        assert expansion >= 1.0
        assert expansion <= 2.5

    def test_risk_reward_calculation(self):
        """Test that risk/reward is calculated correctly."""
        data = create_test_data()
        current_price = data.closes[-1]
        sr_level = current_price * 0.99

        signal = enhance_signal(data, sr_level, "support", current_price)

        # Verify risk/reward ratio
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        calculated_rr = reward / risk if risk > 0 else 0

        assert abs(signal.risk_reward_ratio - calculated_rr) < 0.1

    def test_entry_confidence_range(self):
        """Test that entry confidence is within valid range."""
        data = create_test_data()
        current_price = data.closes[-1]
        sr_level = current_price * 0.995  # Very close to support

        signal = enhance_signal(data, sr_level, "support", current_price)

        assert 0 <= signal.entry_confidence <= 100


class TestFeaturesComputation(unittest.TestCase):
    """Tests for individual feature computation functions."""

    def test_atr_features(self):
        """Test ATR feature computation."""
        data = create_test_data()
        atr_current, atr_pct, atr_ratio = compute_atr_features(data)

        assert atr_current >= 0
        assert atr_ratio >= 0

    def test_volume_features(self):
        """Test volume feature computation."""
        data = create_test_data()
        vol_ratio, vol_cv, vol_uniform = compute_volume_features(data)

        assert vol_ratio >= 0
        assert vol_cv >= 0

    def test_momentum_computation(self):
        """Test momentum computation."""
        data = create_test_data()
        momentum = compute_momentum(data)

        assert isinstance(momentum, float)

    def test_range_narrowing(self):
        """Test range narrowing detection."""
        from ai.features import compute_range_narrowing
        data = create_consolidation_data()
        narrowing = compute_range_narrowing(data)

        assert narrowing < 1.0

    def test_adx_features(self):
        """Test ADX feature computation."""
        from ai.features import compute_adx
        data = create_test_data()
        adx_val, direction, strength = compute_adx(data)

        assert adx_val >= 0
        assert adx_val <= 100

    def test_consolidation_score(self):
        """Test consolidation score computation."""
        data = create_consolidation_data()
        score = compute_consolidation_score(data)

        assert 0 <= score <= 100


if __name__ == "__main__":
    unittest.main()
