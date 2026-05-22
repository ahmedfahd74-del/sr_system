# sr_system/core/engine.py
"""Main S/R detection engine - orchestrates all components."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import numpy as np

from core.config import Config, get_config, update_config
from data.ohlcv import OHLCVData
from data.sources.yahoo_direct import YahooFinanceSource
from data.cache import get_cache
from data.storage import save_sr_level, load_sr_levels
from detection.horizontal import SRLevel, detect_horizontal_sr, atr
from detection.trendline import (
    TrendlineLevel, detect_trendline_sr, merge_trendlines,
    get_trendline_price_at_bar
)
from detection.fractal import (
    FractalLevel, detect_fractal_sr, merge_fractal_levels, get_fractal_channels
)
from ai.pattern import analyze_pattern, PatternResult
from ai.signal_enhancer import enhance_signal as enhance_sr_signal, EnhancedSignal
from ai.features import extract_all_features


# Unified S/R level type for combined output
@dataclass
class UnifiedSRLevel:
    """A unified S/R level from any detection method."""
    price: float
    level_type: str         # "support" or "resistance"
    confidence: float       # 0-100
    source: str             # "horizontal", "trendline", "fractal", "confluence"
    touch_count: int
    timeframe: str
    extra_data: dict = field(default_factory=dict)  # Method-specific data

    @property
    def is_support(self) -> bool:
        return self.level_type == "support"

    @property
    def is_resistance(self) -> bool:
        return self.level_type == "resistance"


@dataclass
class MarketRegime:
    """Current market regime classification."""
    name: str           # "trending", "ranging", "volatile", "low_vol"
    strength: float     # 0-100
    trend_direction: str  # "up", "down", "neutral"


class SREngine:
    """Main engine for S/R detection across multiple timeframes."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        self.data_source = YahooFinanceSource()
        self.cache = get_cache()

        # Per-ticker metadata for auto-calibration
        self.ticker_metadata: Dict[str, dict] = {}

        # Computed S/R levels by ticker+timeframe
        self._levels_cache: Dict[str, Tuple[List[SRLevel], List[SRLevel]]] = {}

    def _get_mtf_data(self, ticker: str, timeframes: List[str] = None) -> Dict[str, OHLCVData]:
        """Fetch data for multiple timeframes."""
        if timeframes is None:
            timeframes = self.config.timeframe.timeframes

        mtf_data = {}
        for tf in timeframes:
            # Check cache first
            cached = self.cache.get_ohlcv(ticker, tf)
            if cached:
                mtf_data[tf] = cached
            else:
                # Fetch recent bars
                bars = 500 if tf in ["1D", "4H", "1H"] else 1000
                data = self.data_source.fetch_recent(ticker, bars=bars, timeframe=tf)
                if len(data) > 0:
                    mtf_data[tf] = data
                    self.cache.set_ohlcv(ticker, tf, data)
        return mtf_data

    def classify_regime(self, data: OHLCVData) -> MarketRegime:
        """Classify current market regime using ATR, ADX, volume."""
        if len(data) < 20:
            return MarketRegime(name="unknown", strength=0, trend_direction="neutral")

        closes = data.closes
        atr_vals = atr(data)
        current_atr = atr_vals[-1]
        avg_atr = atr_vals[-20:].mean() if len(atr_vals) >= 20 else atr_vals.mean()
        atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1

        # ADX-like trend strength
        adx_period = 14
        if len(closes) >= adx_period + 1:
            deltas = np.diff(closes)
            pos_dm = np.maximum(deltas, 0)
            neg_dm = np.maximum(-deltas, 0)
            smoothed_pos = np.convolve(pos_dm, np.ones(adx_period)/adx_period, mode='valid').mean()
            smoothed_neg = np.convolve(neg_dm, np.ones(adx_period)/adx_period, mode='valid').mean()
            di_sum = smoothed_pos + smoothed_neg
            trend_strength = (smoothed_pos - smoothed_neg) / di_sum * 100 if di_sum > 0 else 0
        else:
            trend_strength = 0

        # Volume analysis
        recent_vol = data.volumes[-10:].mean()
        older_vol = data.volumes[-50:-10].mean() if len(data) > 50 else recent_vol
        vol_ratio = recent_vol / older_vol if older_vol > 0 else 1

        # Classify
        if atr_ratio > 1.5 and vol_ratio > 1.3:
            regime = "volatile"
            strength = min(atr_ratio * 40, 100)
        elif abs(trend_strength) < 20 and vol_ratio < 0.8:
            regime = "low_vol"
            strength = 100 - abs(trend_strength)
        elif abs(trend_strength) > 40:
            regime = "trending"
            strength = abs(trend_strength)
        else:
            regime = "ranging"
            strength = 50

        direction = "up" if trend_strength > 20 else "down" if trend_strength < -20 else "neutral"
        return MarketRegime(name=regime, strength=strength, trend_direction=direction)

    def get_adaptive_params(self, regime: MarketRegime, ticker: str = "") -> dict:
        """Get detection parameters adapted to current regime."""
        reg_params = self.config.adaptive.regimes.get(regime.name, {})
        return {
            "lookback": reg_params.get("lookback", 100),
            "min_touches": reg_params.get("min_touches", 2),
            "atr_multiplier": reg_params.get("atr_mult", 2.0),
            "merge_threshold_pct": self.config.detection.horizontal.get("merge_threshold_pct", 0.5),
        }

    def detect_mtf_sr(self, ticker: str, primary_tf: str = "1D") -> Dict[str, Tuple[List[SRLevel], List[SRLevel]]]:
        """Run S/R detection across multiple timeframes."""
        mtf_data = self._get_mtf_data(ticker)

        if primary_tf not in mtf_data:
            return {}

        # Classify regime on primary TF
        primary_data = mtf_data[primary_tf]
        regime = self.classify_regime(primary_data)
        params = self.get_adaptive_params(regime, ticker)

        results = {}
        all_support = []
        all_resistance = []

        for tf, data in mtf_data.items():
            if len(data) < 30:
                continue

            # Weight by timeframe importance
            tf_weight = self.config.timeframe.tf_weights.get(tf, 0.1)

            support, resistance = detect_horizontal_sr(
                data,
                lookback=int(params["lookback"] * tf_weight * 2),
                min_touches=params["min_touches"],
                atr_multiplier=params["atr_multiplier"],
                merge_threshold_pct=params["merge_threshold_pct"],
                timeframe=tf,
            )

            results[tf] = (support, resistance)
            all_support.extend(support)
            all_resistance.extend(resistance)

        self._levels_cache[ticker] = (all_support, all_resistance)
        return results

    def detect_unified(self, ticker: str, primary_tf: str = "1D") -> Dict[str, Dict[str, List[UnifiedSRLevel]]]:
        """
        Run ALL S/R detection methods (horizontal, trendline, fractal)
        and return unified results.

        Returns:
            Dict with structure: {tf: {"support": [UnifiedSRLevel, ...],
                                     "resistance": [UnifiedSRLevel, ...]}}
        """
        mtf_data = self._get_mtf_data(ticker)

        if primary_tf not in mtf_data:
            return {}

        # Classify regime on primary TF
        primary_data = mtf_data[primary_tf]
        regime = self.classify_regime(primary_data)
        params = self.get_adaptive_params(regime, ticker)

        unified_results = {}

        for tf, data in mtf_data.items():
            if len(data) < 30:
                continue

            tf_weight = self.config.timeframe.tf_weights.get(tf, 0.1)
            lookback = int(params["lookback"] * tf_weight * 2)

            all_levels = []

            # 1. Horizontal S/R
            h_support, h_resistance = detect_horizontal_sr(
                data,
                lookback=lookback,
                min_touches=params["min_touches"],
                atr_multiplier=params["atr_multiplier"],
                merge_threshold_pct=params["merge_threshold_pct"],
                timeframe=tf,
            )
            for s in h_support:
                all_levels.append(UnifiedSRLevel(
                    price=s.price, level_type="support",
                    confidence=s.confidence, source="horizontal",
                    touch_count=s.touch_count, timeframe=tf
                ))
            for r in h_resistance:
                all_levels.append(UnifiedSRLevel(
                    price=r.price, level_type="resistance",
                    confidence=r.confidence, source="horizontal",
                    touch_count=r.touch_count, timeframe=tf
                ))

            # 2. Trendline S/R
            tl_config = self.config.detection.trendline
            tl_support, tl_resistance = detect_trendline_sr(
                data,
                lookback=int(tl_config.get("lookback", 50) * tf_weight),
                min_touches=tl_config.get("min_touches", 2),
                slope_sensitivity=tl_config.get("slope_sensitivity", 0.001),
                swing_window=3,
                timeframe=tf,
            )
            for s in tl_support:
                all_levels.append(UnifiedSRLevel(
                    price=s.current_price, level_type="support",
                    confidence=s.confidence, source="trendline",
                    touch_count=s.touch_count, timeframe=tf,
                    extra_data={"slope": s.slope, "start_price": s.price_start}
                ))
            for r in tl_resistance:
                all_levels.append(UnifiedSRLevel(
                    price=r.current_price, level_type="resistance",
                    confidence=r.confidence, source="trendline",
                    touch_count=r.touch_count, timeframe=tf,
                    extra_data={"slope": r.slope, "start_price": r.price_start}
                ))

            # 3. Fractal S/R
            fr_config = self.config.detection.fractal
            fr_support, fr_resistance = detect_fractal_sr(
                data,
                period=fr_config.get("fractal_period", 2),
                lookback=lookback,
                timeframe=tf,
            )
            for s in fr_support:
                all_levels.append(UnifiedSRLevel(
                    price=s.price, level_type="support",
                    confidence=s.confidence, source="fractal",
                    touch_count=1, timeframe=tf,
                    extra_data={"fractal_type": s.fractal_type}
                ))
            for r in fr_resistance:
                all_levels.append(UnifiedSRLevel(
                    price=r.price, level_type="resistance",
                    confidence=r.confidence, source="fractal",
                    touch_count=1, timeframe=tf,
                    extra_data={"fractal_type": r.fractal_type}
                ))

            # Separate by type
            support_levels = [l for l in all_levels if l.level_type == "support"]
            resistance_levels = [l for l in all_levels if l.level_type == "resistance"]

            # Sort by confidence
            support_levels.sort(key=lambda x: x.confidence, reverse=True)
            resistance_levels.sort(key=lambda x: x.confidence, reverse=True)

            unified_results[tf] = {
                "support": support_levels,
                "resistance": resistance_levels
            }

        return unified_results

    def detect_all_mtf_unified(self, ticker: str, primary_tf: str = "1D") -> Tuple[List[UnifiedSRLevel], List[UnifiedSRLevel]]:
        """Run unified detection across all timeframes and return aggregated levels."""
        results = self.detect_unified(ticker, primary_tf)

        all_support = []
        all_resistance = []

        for tf, levels in results.items():
            all_support.extend(levels["support"])
            all_resistance.extend(levels["resistance"])

        # Sort by confidence
        all_support.sort(key=lambda x: x.confidence, reverse=True)
        all_resistance.sort(key=lambda x: x.confidence, reverse=True)

        return all_support, all_resistance

    def get_confluence_levels(self, ticker: str, price_range: float = 0.01) -> List[SRLevel]:
        """Find S/R levels that appear across multiple timeframes (confluence)."""
        if ticker not in self._levels_cache:
            self.detect_mtf_sr(ticker)

        all_support, all_resistance = self._levels_cache.get(ticker, ([], []))
        all_levels = all_support + all_resistance

        if not all_levels:
            return []

        # Group levels by price proximity
        confluence = []
        sorted_levels = sorted(all_levels, key=lambda x: x.confidence, reverse=True)

        i = 0
        while i < len(sorted_levels):
            group = [sorted_levels[i]]
            j = i + 1
            while j < len(sorted_levels):
                price_diff_pct = abs(sorted_levels[j].price - sorted_levels[i].price) / sorted_levels[i].price
                if price_diff_pct <= price_range * 100:  # price_range as percentage
                    group.append(sorted_levels[j])
                j += 1

            if len(group) >= self.config.adaptive.confluence_min_tfs:
                # Create a confluence level
                avg_price = sum(l.price for l in group) / len(group)
                max_conf = max(l.confidence for l in group)
                combined_touches = []
                for l in group:
                    combined_touches.extend(l.touch_bars)

                conf_level = SRLevel(
                    price=avg_price,
                    level_type=group[0].level_type,
                    confidence=max_conf + len(group) * 10,  # Boost for confluence
                    touch_count=len(set(combined_touches)),
                    touch_bars=sorted(set(combined_touches)),
                    source=f"confluence_{len(group)}tf",
                    timeframe=group[0].timeframe,
                )
                confluence.append(conf_level)
            i += 1

        return confluence

    def get_nearest_levels(self, ticker: str, current_price: float,
                           direction: str = "both") -> Tuple[List[SRLevel], List[SRLevel]]:
        """Get nearest support and resistance levels to current price."""
        if ticker not in self._levels_cache:
            self.detect_mtf_sr(ticker)

        support, resistance = self._levels_cache.get(ticker, ([], []))

        if direction == "above" or direction == "support":
            support = [s for s in support if s.price < current_price]
            resistance = []
        elif direction == "below" or direction == "resistance":
            resistance = [r for r in resistance if r.price > current_price]
            support = []
        else:
            # Both - sort by proximity
            support = sorted(support, key=lambda x: abs(x.price - current_price))
            resistance = sorted(resistance, key=lambda x: abs(x.price - current_price))

        return support[:5], resistance[:5]

    def analyze_price_action(self, ticker: str, current_price: float,
                             primary_tf: str = "1D") -> dict:
        """Analyze current price action relative to S/R levels."""
        support, resistance = self.get_nearest_levels(ticker, current_price)

        nearest_support = support[0] if support else None
        nearest_resistance = resistance[0] if resistance else None

        analysis = {
            "current_price": current_price,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "distance_to_support_pct": 0,
            "distance_to_resistance_pct": 0,
            "regime": None,
            "signal": "neutral",  # "bullish", "bearish", "neutral"
            "signal_reason": "",
        }

        if nearest_support:
            analysis["distance_to_support_pct"] = (current_price - nearest_support.price) / current_price * 100

        if nearest_resistance:
            analysis["distance_to_resistance_pct"] = (nearest_resistance.price - current_price) / current_price * 100

        # Detect signals
        if nearest_support and analysis["distance_to_support_pct"] < 1.0:
            if nearest_support.confidence > 60:
                analysis["signal"] = "bullish"
                analysis["signal_reason"] = f"Approaching strong support at {nearest_support.price:.2f}"
        elif nearest_resistance and analysis["distance_to_resistance_pct"] < 1.0:
            if nearest_resistance.confidence > 60:
                analysis["signal"] = "bearish"
                analysis["signal_reason"] = f"Approaching strong resistance at {nearest_resistance.price:.2f}"

        # Get regime
        mtf_data = self._get_mtf_data(ticker, [primary_tf])
        if primary_tf in mtf_data:
            regime = self.classify_regime(mtf_data[primary_tf])
            analysis["regime"] = regime.name

        return analysis

    def analyze_pattern(self, ticker: str, primary_tf: str = "1D") -> PatternResult:
        """Analyze market for pattern detection (AI Phase 3)."""
        mtf_data = self._get_mtf_data(ticker)

        if primary_tf not in mtf_data:
            return PatternResult(
                pattern_type="UNKNOWN",
                confidence=0,
                action="WAIT",
                reasoning="No data available",
                additional_data={}
            )

        data = mtf_data[primary_tf]
        return analyze_pattern(data)

    def enhance_signal(self, ticker: str, direction: str,
                       primary_tf: str = "1D") -> EnhancedSignal:
        """Enhance a trading signal with entry timing (AI Phase 3)."""
        mtf_data = self._get_mtf_data(ticker)

        if primary_tf not in mtf_data:
            return EnhancedSignal(
                base_action="HOLD",
                entry_price=0, stop_loss=0, take_profit=0,
                risk_reward_ratio=0, entry_confidence=0,
                entry_zone_low=0, entry_zone_high=0,
                reasoning="No data available",
                warnings=["No market data"]
            )

        data = mtf_data[primary_tf]

        # Get nearest level based on direction
        current_price = data.closes[-1]
        support, resistance = self.get_nearest_levels(ticker, current_price)

        if direction == "support" and support:
            sr_level = support[0].price
        elif direction == "resistance" and resistance:
            sr_level = resistance[0].price
        else:
            return EnhancedSignal(
                base_action="HOLD",
                entry_price=0, stop_loss=0, take_profit=0,
                risk_reward_ratio=0, entry_confidence=0,
                entry_zone_low=0, entry_zone_high=0,
                reasoning=f"No {direction} levels found",
                warnings=["No relevant S/R level"]
            )

        # Get ATR for the data
        from detection.horizontal import atr as compute_atr
        atr_vals = compute_atr(data)
        atr = atr_vals[-1] if len(atr_vals) > 0 else (data.highs[-1] - data.lows[-1])

        return enhance_sr_signal(data, sr_level, direction, current_price, atr)


# Singleton instance
_engine = None


def get_engine() -> SREngine:
    global _engine
    if _engine is None:
        _engine = SREngine()
    return _engine