"""
Liquidity Zone Detector
========================
Detects true institutional liquidity events:
  - Equal highs / equal lows (stop clusters)
  - Liquidity sweeps and stop hunts
  - Fair Value Gaps (FVGs / imbalances)
  - Displacement candles
  - Trapped trader scenarios
  - Auction efficiency analysis

This module classifies WHY price moved, not just that it moved.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────

@dataclass
class LiquidityEvent:
    """A single detected liquidity event."""
    timestamp:        datetime
    price:            float
    event_type:       str       # 'upward_sweep' | 'downward_sweep' | 'upper_rejection' |
                                # 'lower_rejection' | 'displacement_candle' |
                                # 'inefficiency_gap_up' | 'inefficiency_gap_down'
    strength:         float     # 0-1
    volume:           float
    displacement_size: float
    efficiency:       float     # 0-1  (clean move = 1)


@dataclass
class Inefficiency:
    """Market inefficiency: FVG, displacement candle, gap, or liquidity void."""
    inefficiency_type: str      # 'bullish_fvg' | 'bearish_fvg' | 'gap_up' | 'gap_down' |
                                # 'bullish_displacement' | 'bearish_displacement' | 'liquidity_void'
    upper_level:      float
    lower_level:      float
    timestamp:        datetime
    strength:         float     # 0-1
    filled:           bool = False
    fill_timestamp:   Optional[datetime] = None

    @property
    def mid(self) -> float:
        return (self.upper_level + self.lower_level) / 2

    @property
    def size(self) -> float:
        return self.upper_level - self.lower_level


# ──────────────────────────────────────────────
# Main class
# ──────────────────────────────────────────────

class LiquidityZoneDetector:
    """
    Identifies and classifies institutional liquidity behaviour.

    Parameters
    ----------
    max_events : int
        Maximum number of events to retain in memory.
    max_inefficiencies : int
        Maximum number of inefficiencies to retain.
    """

    def __init__(self, max_events: int = 200, max_inefficiencies: int = 100):
        self.events:         List[LiquidityEvent] = []
        self.inefficiencies: List[Inefficiency]   = []
        self._max_events     = max_events
        self._max_ineff      = max_inefficiencies

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, candles: List) -> Dict:
        """
        Run full liquidity analysis on a candle list.

        Parameters
        ----------
        candles : list
            Each element must expose .open, .high, .low, .close, .volume,
            .timestamp, .body, .range, .upper_wick, .lower_wick, .is_bullish

        Returns
        -------
        dict with keys:
            events, inefficiencies, equal_levels, trapped,
            movement_classification, auction_analysis, liquidity_score
        """
        if len(candles) < 5:
            return {}

        # Detect events
        new_events = self._detect_events(candles)
        self.events.extend(new_events)
        self.events = self.events[-self._max_events:]

        # Detect inefficiencies
        new_ineff = self._detect_inefficiencies(candles)
        self.inefficiencies.extend(new_ineff)
        self.inefficiencies = self.inefficiencies[-self._max_ineff:]
        self._update_fill_status(candles[-1])

        return {
            "events":                  self.events[-20:],
            "inefficiencies":          [i for i in self.inefficiencies if not i.filled][:20],
            "equal_levels":            self._detect_equal_levels(candles),
            "trapped":                 self._detect_trapped(candles),
            "movement_classification": self._classify_movement(candles),
            "auction_analysis":        self._auction_efficiency(candles),
            "liquidity_score":         self._liquidity_score(),
        }

    def get_active_inefficiencies(
        self,
        current_price: float,
        direction: Optional[str] = None,  # 'bullish' | 'bearish' | None
    ) -> List[Inefficiency]:
        """Return unfilled inefficiencies relevant to the current price and direction."""
        active = [i for i in self.inefficiencies if not i.filled]

        if direction == "bullish":
            active = [
                i for i in active
                if i.upper_level < current_price
                and "bullish" in i.inefficiency_type
            ]
        elif direction == "bearish":
            active = [
                i for i in active
                if i.lower_level > current_price
                and "bearish" in i.inefficiency_type
            ]

        return sorted(active, key=lambda x: x.strength, reverse=True)[:10]

    # ------------------------------------------------------------------
    # Event detection
    # ------------------------------------------------------------------

    def _detect_events(self, candles: List) -> List[LiquidityEvent]:
        events = []
        if len(candles) < 3:
            return events

        for i in range(2, len(candles)):
            cur, prev, prev2 = candles[i], candles[i - 1], candles[i - 2]
            atr = self._atr(candles[max(0, i - 14): i + 1])

            sweep = self._check_sweep(cur, prev, prev2, atr)
            if sweep:
                events.append(sweep)

            rej = self._check_rejection(cur, atr)
            if rej:
                events.append(rej)

            ineff = self._check_displacement(cur, prev, prev2, atr)
            if ineff:
                events.append(ineff)

        return events

    @staticmethod
    def _check_sweep(cur, prev, prev2, atr: float) -> Optional[LiquidityEvent]:
        # Upward sweep
        if (
            cur.high > prev.high and cur.high > prev2.high
            and cur.close < cur.high - cur.range * 0.3
            and cur.range > atr * 0.8
        ):
            disp = cur.high - max(prev.high, prev2.high)
            return LiquidityEvent(
                timestamp=cur.timestamp, price=cur.high,
                event_type="upward_sweep",
                strength=min(disp / atr, 1.0),
                volume=cur.volume, displacement_size=disp,
                efficiency=disp / cur.range if cur.range else 0,
            )
        # Downward sweep
        if (
            cur.low < prev.low and cur.low < prev2.low
            and cur.close > cur.low + cur.range * 0.3
            and cur.range > atr * 0.8
        ):
            disp = min(prev.low, prev2.low) - cur.low
            return LiquidityEvent(
                timestamp=cur.timestamp, price=cur.low,
                event_type="downward_sweep",
                strength=min(disp / atr, 1.0),
                volume=cur.volume, displacement_size=disp,
                efficiency=disp / cur.range if cur.range else 0,
            )
        return None

    @staticmethod
    def _check_rejection(cur, atr: float) -> Optional[LiquidityEvent]:
        thr = atr * 0.5

        # Upper rejection
        uw = cur.upper_wick
        if uw > thr and cur.body > 0 and uw > cur.body * 2:
            return LiquidityEvent(
                timestamp=cur.timestamp, price=cur.high,
                event_type="upper_rejection",
                strength=min(uw / atr, 1.0),
                volume=cur.volume, displacement_size=uw,
                efficiency=uw / cur.range if cur.range else 0,
            )

        # Lower rejection
        lw = cur.lower_wick
        if lw > thr and cur.body > 0 and lw > cur.body * 2:
            return LiquidityEvent(
                timestamp=cur.timestamp, price=cur.low,
                event_type="lower_rejection",
                strength=min(lw / atr, 1.0),
                volume=cur.volume, displacement_size=lw,
                efficiency=lw / cur.range if cur.range else 0,
            )

        return None

    @staticmethod
    def _check_displacement(cur, prev, prev2, atr: float) -> Optional[LiquidityEvent]:
        # Gap up
        if cur.low > prev.high:
            gap = cur.low - prev.high
            if gap > atr * 0.3:
                return LiquidityEvent(
                    timestamp=cur.timestamp, price=(cur.low + prev.high) / 2,
                    event_type="inefficiency_gap_up",
                    strength=min(gap / atr, 1.0),
                    volume=cur.volume, displacement_size=gap, efficiency=1.0,
                )

        # Gap down
        if cur.high < prev.low:
            gap = prev.low - cur.high
            if gap > atr * 0.3:
                return LiquidityEvent(
                    timestamp=cur.timestamp, price=(prev.low + cur.high) / 2,
                    event_type="inefficiency_gap_down",
                    strength=min(gap / atr, 1.0),
                    volume=cur.volume, displacement_size=gap, efficiency=1.0,
                )

        # Large displacement candle
        if (
            cur.body > atr * 1.2
            and cur.range > 0
            and cur.body / cur.range > 0.85
        ):
            return LiquidityEvent(
                timestamp=cur.timestamp, price=cur.close,
                event_type="displacement_candle",
                strength=min(cur.body / atr, 1.0),
                volume=cur.volume, displacement_size=cur.body,
                efficiency=cur.body / cur.range,
            )

        return None

    # ------------------------------------------------------------------
    # Inefficiency detection
    # ------------------------------------------------------------------

    def _detect_inefficiencies(self, candles: List) -> List[Inefficiency]:
        result = []
        result.extend(self._detect_fvgs(candles))
        result.extend(self._detect_gaps(candles))
        result.extend(self._detect_large_candles(candles))
        result.extend(self._detect_voids(candles))
        return result

    def _detect_fvgs(self, candles: List) -> List[Inefficiency]:
        fvgs = []
        avg_r = self._mean_range(candles)
        for i in range(1, len(candles) - 1):
            c1, c3 = candles[i - 1], candles[i + 1]
            if c1.high < c3.low:
                size = c3.low - c1.high
                if size > avg_r * 0.1:
                    fvgs.append(Inefficiency(
                        "bullish_fvg", c3.low, c1.high,
                        c3.timestamp, self._gap_strength(size, candles, i),
                    ))
            elif c3.high < c1.low:
                size = c1.low - c3.high
                if size > avg_r * 0.1:
                    fvgs.append(Inefficiency(
                        "bearish_fvg", c1.low, c3.high,
                        c3.timestamp, self._gap_strength(size, candles, i),
                    ))
        return fvgs

    def _detect_gaps(self, candles: List) -> List[Inefficiency]:
        gaps = []
        for i in range(1, len(candles)):
            cur, prev = candles[i], candles[i - 1]
            atr = self._atr(candles[max(0, i - 14): i + 1])
            if cur.low > prev.high:
                size = cur.low - prev.high
                if size > atr * 0.3:
                    gaps.append(Inefficiency(
                        "gap_up", cur.low, prev.high,
                        cur.timestamp, min(size / atr, 1.0),
                    ))
            elif cur.high < prev.low:
                size = prev.low - cur.high
                if size > atr * 0.3:
                    gaps.append(Inefficiency(
                        "gap_down", prev.low, cur.high,
                        cur.timestamp, min(size / atr, 1.0),
                    ))
        return gaps

    def _detect_large_candles(self, candles: List) -> List[Inefficiency]:
        if len(candles) < 10:
            return []
        result = []
        avg_r = float(np.mean([c.range for c in candles[-20:]]))
        for c in candles:
            if c.body > avg_r * 2 and c.range > 0 and c.body / c.range > 0.8:
                if c.is_bullish:
                    top  = c.open + c.body * 0.4
                    bot  = c.open + c.body * 0.1
                    kind = "bullish_displacement"
                else:
                    top  = c.open - c.body * 0.1
                    bot  = c.open - c.body * 0.4
                    kind = "bearish_displacement"
                result.append(Inefficiency(
                    kind, top, bot,
                    c.timestamp, min(c.body / avg_r / 3, 1.0),
                ))
        return result

    def _detect_voids(self, candles: List) -> List[Inefficiency]:
        voids = []
        avg_r = self._mean_range(candles)
        for i in range(len(candles) - 4):
            seq = candles[i: i + 5]
            small_body = sum(
                1 for c in seq if c.range > 0 and c.body / c.range < 0.3
            )
            if small_body >= 4:
                sh = max(c.high for c in seq)
                sl = min(c.low  for c in seq)
                rng = sh - sl
                strength = max(0.2, 1.0 - rng / (avg_r * 5)) if avg_r > 0 else 0.2
                voids.append(Inefficiency(
                    "liquidity_void", sh, sl, seq[-1].timestamp, strength,
                ))
        return voids

    def _update_fill_status(self, current_candle):
        p = current_candle.close
        for ineff in self.inefficiencies:
            if not ineff.filled:
                if (
                    ineff.lower_level <= p <= ineff.upper_level
                    or current_candle.low  <= ineff.lower_level <= current_candle.high
                    or current_candle.low  <= ineff.upper_level <= current_candle.high
                ):
                    ineff.filled = True
                    ineff.fill_timestamp = current_candle.timestamp

    # ------------------------------------------------------------------
    # Equal levels
    # ------------------------------------------------------------------

    def _detect_equal_levels(self, candles: List) -> Dict[str, List[float]]:
        avg_r = self._mean_range(candles)
        tol   = avg_r * 0.1

        highs = [c.high for c in candles]
        lows  = [c.low  for c in candles]

        eq_highs = list({
            h for i, h in enumerate(highs)
            if any(abs(h - highs[j]) < tol for j in range(i + 1, len(highs)))
        })
        eq_lows  = list({
            l for i, l in enumerate(lows)
            if any(abs(l - lows[j]) < tol for j in range(i + 1, len(lows)))
        })

        return {"equal_highs": eq_highs, "equal_lows": eq_lows}

    # ------------------------------------------------------------------
    # Trapped traders
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_trapped(candles: List) -> Dict[str, int]:
        trapped_longs = trapped_shorts = 0
        for i in range(1, len(candles)):
            cur, prev = candles[i], candles[i - 1]
            if (
                prev.is_bullish
                and cur.low  < prev.low
                and cur.close < prev.open
            ):
                trapped_longs += 1
            elif (
                not prev.is_bullish
                and cur.high > prev.high
                and cur.close > prev.open
            ):
                trapped_shorts += 1
        return {"trapped_longs": trapped_longs, "trapped_shorts": trapped_shorts}

    # ------------------------------------------------------------------
    # Movement classification
    # ------------------------------------------------------------------

    def _classify_movement(self, candles: List) -> Dict:
        if len(candles) < 10:
            return {}
        recent = candles[-10:]
        closes = [c.close for c in recent]
        net    = abs(closes[-1] - closes[0])
        total  = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        efficiency = net / total if total > 0 else 0

        vols = [c.volume for c in recent if c.volume > 0]
        vol_cv = float(np.std(vols) / np.mean(vols)) if vols else 1.0

        avg_wick = float(np.mean([
            (c.upper_wick + c.lower_wick) / c.range if c.range > 0 else 0
            for c in recent
        ]))

        genuine = 0
        manip   = 0
        if efficiency > 0.6:   genuine += 30
        if vol_cv < 0.8:       genuine += 20
        if avg_wick < 0.4:     genuine += 20
        if efficiency < 0.3:   manip   += 25
        if vol_cv > 1.2:       manip   += 20
        if avg_wick > 0.6:     manip   += 25

        return {
            "genuine_participation": genuine,
            "manipulation":          manip,
            "efficiency":            round(efficiency, 3),
            "volume_consistency":    round(1 - vol_cv, 3),
            "wick_ratio":            round(avg_wick, 3),
        }

    # ------------------------------------------------------------------
    # Auction efficiency
    # ------------------------------------------------------------------

    @staticmethod
    def _auction_efficiency(candles: List) -> Dict:
        if len(candles) < 5:
            return {}
        recent = candles[-5:]
        closes = [c.close for c in recent]
        net    = abs(closes[-1] - closes[0])
        total  = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
        return {
            "auction_efficiency": round(net / total if total > 0 else 0, 3),
            "net_movement":       round(net, 5),
            "total_movement":     round(total, 5),
        }

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def _liquidity_score(self) -> float:
        base = 50.0
        mc   = self._classify_movement(
            # dummy call — score from cached events only if no candles
            []
        )
        # Count clean vs messy events (last 20)
        recent_events = self.events[-20:]
        clean = sum(1 for e in recent_events if e.efficiency > 0.7)
        messy = sum(1 for e in recent_events if e.efficiency < 0.3)
        base += clean * 5
        base -= messy * 3
        return max(0.0, min(base, 100.0))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _atr(candles: List, period: int = 14) -> float:
        if len(candles) < 2:
            return 0.001
        trs = [
            max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i - 1].close),
                abs(candles[i].low  - candles[i - 1].close),
            )
            for i in range(1, len(candles))
        ]
        return float(np.mean(trs[-period:]))

    @staticmethod
    def _mean_range(candles: List) -> float:
        if not candles:
            return 0.001
        rngs = [c.range for c in candles if c.range > 0]
        return float(np.mean(rngs)) if rngs else 0.001

    def _gap_strength(self, gap_size: float, candles: List, idx: int) -> float:
        avg_r = self._mean_range(candles[max(0, idx - 10): idx + 1])
        return min(gap_size / avg_r if avg_r > 0 else 0, 1.0)
