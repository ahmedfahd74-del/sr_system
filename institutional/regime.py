"""
Market Regime Detection Engine
================================
Classifies the current market environment before ANY trade logic runs.
This is the first filter — determines if we should even look for trades.
"""

from __future__ import annotations
from collections import deque
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np

from .core_data import Candle, MarketEnvironment


class EnvironmentClassifier:
    """
    Classifies market environment with confidence score.
    Must run BEFORE any S/R or entry logic.
    """

    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        self.classification_history: deque = deque(maxlen=100)

    # ------------------------------------------------------------------
    def classify_environment(
        self,
        candles: List[Candle],
        volume_data: List[float] = None,
    ) -> Tuple[MarketEnvironment, float]:
        """
        Returns (Environment, Confidence 0-1).
        """
        if len(candles) < self.lookback:
            return MarketEnvironment.LOW_LIQUIDITY, 0.3

        window = candles[-self.lookback:]
        highs   = [c.high   for c in window]
        lows    = [c.low    for c in window]
        closes  = [c.close  for c in window]
        volumes = (volume_data[-self.lookback:] if volume_data
                   else [c.volume for c in window])

        metrics = self._calculate_metrics(highs, lows, closes, volumes)

        scores = {
            MarketEnvironment.TRENDING:      self._score_trending(metrics),
            MarketEnvironment.RANGING:       self._score_ranging(metrics),
            MarketEnvironment.EXPANDING:     self._score_expanding(metrics),
            MarketEnvironment.CONTRACTING:   self._score_contracting(metrics),
            MarketEnvironment.MANIPULATIVE:  self._score_manipulative(metrics),
            MarketEnvironment.LOW_LIQUIDITY: self._score_low_liquidity(metrics),
            MarketEnvironment.DISTRIBUTION:  self._score_distribution(metrics),
            MarketEnvironment.ACCUMULATION:  self._score_accumulation(metrics),
        }

        best = max(scores.items(), key=lambda x: x[1])
        env, confidence = best

        self.classification_history.append((datetime.now(), env, confidence))
        return env, confidence / 100.0          # normalise to 0-1

    # ------------------------------------------------------------------
    def _calculate_metrics(self, highs, lows, closes, volumes) -> Dict:
        price_range    = max(highs) - min(lows)
        recent_range   = max(highs[-10:]) - min(lows[-10:])
        range_ratio    = recent_range / price_range if price_range > 0 else 0

        returns        = np.diff(closes) / np.array(closes[:-1])
        volatility     = float(np.std(returns))
        recent_vol     = float(np.std(returns[-10:]))
        vol_ratio      = recent_vol / volatility if volatility > 0 else 1.0

        slope          = np.polyfit(range(len(closes)), closes, 1)[0]
        r2             = float(np.corrcoef(range(len(closes)), closes)[0, 1] ** 2)

        net_change     = abs(closes[-1] - closes[0])
        total_movement = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        efficiency     = net_change / total_movement if total_movement > 0 else 0

        avg_vol        = float(np.mean(volumes)) if volumes else 1
        recent_vol_v   = float(np.mean(volumes[-10:])) if volumes else 1
        vol_ratio_v    = recent_vol_v / avg_vol if avg_vol > 0 else 1

        peaks          = self._count_peaks(highs)
        troughs        = self._count_peaks([-x for x in lows])
        osc_freq       = (peaks + troughs) / len(closes)

        return {
            "range_ratio":   range_ratio,
            "vol_ratio":     vol_ratio,
            "trend_slope":   abs(float(slope)),
            "trend_strength": r2,
            "range_tightness": 1 - min(range_ratio, 1.0),
            "volume_ratio":  vol_ratio_v,
            "osc_freq":      osc_freq,
            "efficiency":    efficiency,
            "volatility":    volatility,
            "price_range":   price_range,
            "price_dir":     1 if slope > 0 else -1,
        }

    @staticmethod
    def _count_peaks(data: List[float]) -> int:
        count = 0
        for i in range(1, len(data) - 1):
            if data[i] > data[i - 1] and data[i] > data[i + 1]:
                count += 1
        return count

    # --- individual scorers (0-100) ---
    def _score_trending(self, m) -> float:
        s  = m["trend_strength"] * 30
        s += m["efficiency"] * 25
        s += min(m["trend_slope"] * 1000, 20)
        s -= m["osc_freq"] * 15
        s -= m["range_tightness"] * 10
        return max(0, min(s, 100))

    def _score_ranging(self, m) -> float:
        s  = m["range_tightness"] * 25
        s += m["osc_freq"] * 20
        s += (1 - m["efficiency"]) * 20
        s += (1 - m["trend_strength"]) * 15
        s -= m["trend_strength"] * 20
        return max(0, min(s, 100))

    def _score_expanding(self, m) -> float:
        s  = max(0, (m["vol_ratio"] - 1.5)) * 40
        s += max(0, (m["range_ratio"] - 0.8)) * 30
        s += m["volume_ratio"] * 10 if m["volume_ratio"] > 0 else 0
        return max(0, min(s, 100))

    def _score_contracting(self, m) -> float:
        s  = max(0, (0.5 - m["vol_ratio"])) * 40
        s += m["range_tightness"] * 30
        if m["volume_ratio"] < 0.8:
            s += 15
        return max(0, min(s, 100))

    def _score_manipulative(self, m) -> float:
        s = 0
        if m["volatility"] > 0.02 and m["efficiency"] < 0.3:
            s += 35
        if m["osc_freq"] > 0.15:
            s += 25
        if m["volume_ratio"] > 2.0:
            s += 20
        return max(0, min(s, 100))

    def _score_low_liquidity(self, m) -> float:
        s = 0
        if m["volume_ratio"] < 0.5:
            s += 40
        if m["volatility"] < 0.005:
            s += 30
        if m["price_range"] < 0.001:
            s += 20
        return max(0, min(s, 100))

    def _score_distribution(self, m) -> float:
        s = 0
        if m["volume_ratio"] > 1.3 and m["efficiency"] < 0.4:
            s += 30
        if m["osc_freq"] > 0.1:
            s += 20
        return max(0, min(s, 100))

    def _score_accumulation(self, m) -> float:
        s = 0
        if m["volume_ratio"] > 1.3 and 0.3 < m["efficiency"] < 0.6:
            s += 35
        if m["vol_ratio"] < 0.8 and m["volume_ratio"] > 1.1:
            s += 25
        return max(0, min(s, 100))

    # ------------------------------------------------------------------
    def get_environment_adjustments(self, env: MarketEnvironment) -> Dict:
        """
        Returns strategy multipliers for a given environment.
        size_multiplier == 0 means do NOT trade.
        """
        table = {
            MarketEnvironment.TRENDING:      dict(target=1.5, stop=1.2, aggression=1.3, size=1.2),
            MarketEnvironment.RANGING:       dict(target=0.7, stop=1.0, aggression=0.8, size=1.0),
            MarketEnvironment.EXPANDING:     dict(target=1.3, stop=1.4, aggression=1.1, size=0.9),
            MarketEnvironment.CONTRACTING:   dict(target=0.6, stop=0.8, aggression=0.6, size=0.7),
            MarketEnvironment.MANIPULATIVE:  dict(target=0.5, stop=1.5, aggression=0.3, size=0.4),
            MarketEnvironment.LOW_LIQUIDITY: dict(target=0.0, stop=0.0, aggression=0.0, size=0.0),
            MarketEnvironment.DISTRIBUTION:  dict(target=0.8, stop=1.1, aggression=0.7, size=0.8),
            MarketEnvironment.ACCUMULATION:  dict(target=1.1, stop=1.0, aggression=1.1, size=1.1),
        }
        return table.get(env, dict(target=0.0, stop=0.0, aggression=0.0, size=0.0))
