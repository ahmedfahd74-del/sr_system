"""
Institutional Levels Engine
=============================
Detects, weights, and manages institutional S/R levels across timeframes.
Levels are classified by actual institutional importance — not all are equal.
"""

from __future__ import annotations
import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from .core_data import (
    Candle,
    InstitutionalLevel,
    LevelImportance,
    LevelReaction,
    LevelType,
)

logger = logging.getLogger(__name__)


class InstitutionalLevelsEngine:
    """
    Core engine that identifies which levels matter MOST.
    Processes timeframes from HTF down, applies confluence weighting,
    decays stale levels, and deduplicates overlapping zones.
    """

    TF_WEIGHTS = {
        "Monthly": 10.0, "Weekly": 8.0,  "Daily": 6.0,
        "4H":       4.0, "1H":    2.5,   "15m":  1.5,
        "5m":       1.0, "1m":    0.5,
    }

    # Minimum distance between distinct levels (as % of price)
    CLUSTER_TOLERANCE = {
        "Monthly": 0.015, "Weekly": 0.008, "Daily": 0.005,
        "4H":      0.003, "1H":    0.002,  "15m":  0.001,
        "5m":      0.0008,"1m":    0.0005,
    }

    def __init__(self, max_levels: int = 100):
        self.levels: List[InstitutionalLevel] = []
        self.max_levels = max_levels
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_levels(
        self,
        mtf_data: Dict[str, List[Candle]],
        symbol: str,
    ) -> List[InstitutionalLevel]:
        """Detect institutional levels across all available timeframes."""
        new_levels: List[InstitutionalLevel] = []

        for tf in ["Monthly", "Weekly", "Daily", "4H", "1H", "15m", "5m", "1m"]:
            if tf not in mtf_data or len(mtf_data[tf]) < 20:
                continue
            try:
                tf_levels = self._detect_tf_levels(mtf_data[tf], tf, symbol)
                new_levels.extend(tf_levels)
            except Exception as exc:
                logger.error("Level detection error %s %s: %s", symbol, tf, exc)

        with self._lock:
            self._add_new_levels(new_levels)
            self._cleanup_levels()
            self._update_clusters()
            self._rank_levels()

        return self.get_active_levels()

    def get_active_levels(
        self, importance_filter: Optional[LevelImportance] = None
    ) -> List[InstitutionalLevel]:
        with self._lock:
            active = [l for l in self.levels if l.is_active]
            if importance_filter:
                active = [l for l in active if l.importance.value <= importance_filter.value]
            return active

    def get_levels_near_price(
        self,
        price: float,
        distance_pct: float = 0.02,
        importance_filter: Optional[LevelImportance] = None,
    ) -> List[InstitutionalLevel]:
        levels = self.get_active_levels(importance_filter)
        nearby = [l for l in levels if abs(l.price - price) / price <= distance_pct]
        return sorted(nearby, key=lambda l: abs(l.price - price))

    def update_on_candle(self, candle: Candle, tolerance_pct: float = 0.001):
        """Update level states based on a new candle close."""
        with self._lock:
            for level in self.levels:
                tol = level.price * tolerance_pct
                touched = (
                    candle.low  <= level.price + tol and
                    candle.high >= level.price - tol
                )
                if not touched:
                    continue

                # Determine reaction type
                if candle.high > level.price + tol and candle.close < level.price:
                    reaction = LevelReaction.STRONG_REJECTION
                elif candle.low < level.price - tol and candle.close > level.price:
                    reaction = LevelReaction.STRONG_REJECTION
                elif abs(candle.close - level.price) < tol:
                    reaction = LevelReaction.ABSORPTION
                else:
                    reaction = LevelReaction.WEAK_REJECTION

                displacement = abs(candle.close - level.price)
                level.update_after_test(reaction, candle.volume, displacement, candle.timestamp)

                # Mark broken if close significantly through
                if abs(candle.close - level.price) > level.price * 0.005:
                    if reaction in (LevelReaction.ABSORPTION, LevelReaction.WEAK_REJECTION):
                        level.is_active = False
                        level.false_break_count += 1

                # Count sweeps
                if (
                    (candle.high > level.price * 1.002 and candle.close < level.price) or
                    (candle.low  < level.price * 0.998 and candle.close > level.price)
                ):
                    level.sweep_count += 1

    # ------------------------------------------------------------------
    # Internal: detection helpers
    # ------------------------------------------------------------------

    def _detect_tf_levels(
        self,
        candles: List[Candle],
        timeframe: str,
        symbol: str,
    ) -> List[InstitutionalLevel]:
        all_levels: List[InstitutionalLevel] = []

        all_levels.extend(self._detect_pivot_levels(candles, timeframe))
        all_levels.extend(self._detect_equal_levels(candles, timeframe))
        all_levels.extend(self._detect_order_blocks(candles, timeframe))
        all_levels.extend(self._detect_fvg_levels(candles, timeframe))
        all_levels.extend(self._detect_displacement_origins(candles, timeframe))

        if timeframe in ("4H", "1H", "15m", "5m"):
            all_levels.extend(self._detect_session_levels(candles, timeframe))

        all_levels.extend(self._detect_psychological_levels(candles, timeframe, symbol))
        return all_levels

    def _detect_pivot_levels(
        self, candles: List[Candle], tf: str
    ) -> List[InstitutionalLevel]:
        levels = []
        lb = min(len(candles) // 4, 50)

        for i in range(lb, len(candles) - lb):
            cur = candles[i]
            is_sh = all(cur.high > candles[j].high for j in range(i - lb, i + lb + 1) if j != i)
            is_sl = all(cur.low  < candles[j].low  for j in range(i - lb, i + lb + 1) if j != i)

            if is_sh:
                quality = self._pivot_quality(candles, i, "high", lb)
                if quality >= 0.6:
                    lv = InstitutionalLevel(
                        price=cur.high,
                        level_type=LevelType.WEEKLY_PIVOT if tf in ("Monthly", "Weekly") else LevelType.DAILY_PIVOT,
                        timeframe=tf,
                        creation_timestamp=cur.timestamp,
                        tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
                    )
                    lv.supply_strength = quality
                    lv.confluence_factors.add("swing_high")
                    levels.append(lv)

            if is_sl:
                quality = self._pivot_quality(candles, i, "low", lb)
                if quality >= 0.6:
                    lv = InstitutionalLevel(
                        price=cur.low,
                        level_type=LevelType.WEEKLY_PIVOT if tf in ("Monthly", "Weekly") else LevelType.DAILY_PIVOT,
                        timeframe=tf,
                        creation_timestamp=cur.timestamp,
                        tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
                    )
                    lv.demand_strength = quality
                    lv.confluence_factors.add("swing_low")
                    levels.append(lv)

        return levels

    def _pivot_quality(
        self, candles: List[Candle], idx: int, kind: str, lb: int
    ) -> float:
        c = candles[idx]
        score = 0.0

        # Wick quality
        wick = c.upper_wick if kind == "high" else c.lower_wick
        if c.range > 0:
            ratio = wick / c.range
            score += 0.3 if ratio > 0.4 else (0.2 if ratio > 0.2 else 0)

        # Volume
        if c.volume > 0:
            ctx = [x.volume for x in candles[max(0, idx-10):idx+11] if x.volume > 0]
            if ctx:
                score += 0.25 if c.volume > np.mean(ctx) * 1.5 else 0.15

        # Displacement after pivot
        if idx < len(candles) - 5:
            nxt = candles[idx+1:idx+6]
            if kind == "high":
                disp = c.high - min(x.low for x in nxt)
            else:
                disp = max(x.high for x in nxt) - c.low
            avg_r = np.mean([x.range for x in candles[max(0, idx-20):idx+1]]) or 1
            score += min(disp / (avg_r * 5), 0.3)

        return min(score, 1.0)

    def _detect_equal_levels(
        self, candles: List[Candle], tf: str
    ) -> List[InstitutionalLevel]:
        tol = self.CLUSTER_TOLERANCE.get(tf, 0.002)
        levels = []

        highs = [(i, c.high) for i, c in enumerate(candles)]
        lows  = [(i, c.low)  for i, c in enumerate(candles)]

        for groups, kind, ltype in [
            (self._group_equal(highs, tol), "high", LevelType.EQUAL_HIGHS),
            (self._group_equal(lows,  tol), "low",  LevelType.EQUAL_LOWS),
        ]:
            for group in groups:
                if len(group) < 2:
                    continue
                price   = float(np.mean([p for _, p in group]))
                indices = [i for i, _ in group]
                quality = self._equal_level_quality(candles, indices, price, kind)
                if quality < 0.5:
                    continue
                lv = InstitutionalLevel(
                    price=price,
                    level_type=ltype,
                    timeframe=tf,
                    creation_timestamp=candles[indices[-1]].timestamp,
                    cluster_size=len(group),
                    tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
                )
                lv.confluence_factors.add("equal_highs" if kind == "high" else "equal_lows")
                lv.confluence_factors.add("liquidity_cluster")
                if kind == "high":
                    lv.supply_strength = quality
                else:
                    lv.demand_strength = quality
                levels.append(lv)

        return levels

    @staticmethod
    def _group_equal(
        price_data: List[Tuple[int, float]], tol: float
    ) -> List[List[Tuple[int, float]]]:
        if not price_data:
            return []
        sorted_data = sorted(price_data, key=lambda x: x[1])
        groups, cur = [], [sorted_data[0]]
        for item in sorted_data[1:]:
            if abs(item[1] - cur[0][1]) / cur[0][1] <= tol:
                cur.append(item)
            else:
                if len(cur) >= 2:
                    groups.append(cur)
                cur = [item]
        if len(cur) >= 2:
            groups.append(cur)
        return groups

    def _equal_level_quality(
        self, candles, indices, price, kind
    ) -> float:
        q = 0.0
        q += min(len(indices) / 5, 0.3)
        if len(indices) > 1:
            q += min((indices[-1] - indices[0]) / 100, 0.2)
        strengths = []
        for idx in indices:
            if 0 <= idx < len(candles):
                c = candles[idx]
                wick = c.upper_wick if kind == "high" else c.lower_wick
                strengths.append(wick / c.range if c.range > 0 else 0)
        if strengths:
            q += float(np.mean(strengths)) * 0.3
        return min(q, 1.0)

    def _detect_order_blocks(
        self, candles: List[Candle], tf: str
    ) -> List[InstitutionalLevel]:
        levels = []
        min_move = 3

        for i in range(len(candles) - min_move - 1):
            c = candles[i]
            nxt = candles[i+1:i+1+min_move]

            bull_ob = not c.is_bullish and self._strong_move(nxt, "bullish")
            bear_ob = c.is_bullish     and self._strong_move(nxt, "bearish")

            if not (bull_ob or bear_ob):
                continue

            lv = InstitutionalLevel(
                price=(c.high + c.low) / 2,
                level_type=LevelType.ORDER_BLOCK,
                timeframe=tf,
                creation_timestamp=c.timestamp,
                tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
            )
            if bull_ob:
                lv.demand_strength = self._ob_strength(c, nxt, "bullish")
                lv.order_flow_bias = "bullish"
            else:
                lv.supply_strength = self._ob_strength(c, nxt, "bearish")
                lv.order_flow_bias = "bearish"
            lv.confluence_factors.add("order_block")
            levels.append(lv)

        return levels

    @staticmethod
    def _strong_move(candles: List[Candle], direction: str) -> bool:
        if len(candles) < 3:
            return False
        if direction == "bullish":
            ratio = sum(1 for c in candles if c.is_bullish) / len(candles)
            net   = candles[-1].close - candles[0].open
        else:
            ratio = sum(1 for c in candles if not c.is_bullish) / len(candles)
            net   = candles[0].open - candles[-1].close
        return ratio >= 0.6 and net > 0

    def _ob_strength(self, ob: Candle, nxt: List[Candle], direction: str) -> float:
        s = 0.0
        if ob.range > 0:
            s += (ob.body / ob.range) * 0.3
        if ob.volume > 0 and nxt:
            vols = [c.volume for c in nxt if c.volume > 0]
            if vols:
                s += min(ob.volume / np.mean(vols) / 2, 0.3)
        s += self._move_strength(nxt, direction) * 0.4
        return min(s, 1.0)

    @staticmethod
    def _move_strength(candles: List[Candle], direction: str) -> float:
        if not candles:
            return 0.0
        if direction == "bullish":
            return sum(1 for c in candles if c.is_bullish) / len(candles)
        return sum(1 for c in candles if not c.is_bullish) / len(candles)

    def _detect_fvg_levels(
        self, candles: List[Candle], tf: str
    ) -> List[InstitutionalLevel]:
        levels = []
        avg_r = float(np.mean([c.range for c in candles[-50:]])) if len(candles) >= 50 else 1

        for i in range(1, len(candles) - 1):
            c1, c3 = candles[i - 1], candles[i + 1]
            bull_gap = c1.high < c3.low
            bear_gap = c3.high < c1.low

            if not (bull_gap or bear_gap):
                continue

            if bull_gap:
                gap_size = c3.low - c1.high
                if gap_size < avg_r * 0.1:
                    continue
                lv = InstitutionalLevel(
                    price=(c1.high + c3.low) / 2,
                    level_type=LevelType.FAIR_VALUE_GAP,
                    timeframe=tf,
                    creation_timestamp=c3.timestamp,
                    tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
                )
                lv.demand_strength = min(gap_size / avg_r, 1.0)
                lv.order_flow_bias = "bullish"
            else:
                gap_size = c1.low - c3.high
                if gap_size < avg_r * 0.1:
                    continue
                lv = InstitutionalLevel(
                    price=(c3.high + c1.low) / 2,
                    level_type=LevelType.FAIR_VALUE_GAP,
                    timeframe=tf,
                    creation_timestamp=c3.timestamp,
                    tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
                )
                lv.supply_strength = min(gap_size / avg_r, 1.0)
                lv.order_flow_bias = "bearish"

            lv.confluence_factors.add("fair_value_gap")
            levels.append(lv)

        return levels

    def _detect_displacement_origins(
        self, candles: List[Candle], tf: str
    ) -> List[InstitutionalLevel]:
        if len(candles) < 15:
            return []
        atr = float(np.mean([c.range for c in candles[-14:]]))
        levels = []

        for i, c in enumerate(candles[:-3]):
            if not (c.body > atr * 1.5 and c.range > 0 and c.body / c.range > 0.7):
                continue
            nxt = candles[i+1:i+4]
            if c.is_bullish:
                follow = all(x.low >= c.low * 0.999 for x in nxt)
            else:
                follow = all(x.high <= c.high * 1.001 for x in nxt)
            if not follow:
                continue

            lv = InstitutionalLevel(
                price=c.open,
                level_type=LevelType.DISPLACEMENT_ORIGIN,
                timeframe=tf,
                creation_timestamp=c.timestamp,
                tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
            )
            strength = min(c.body / atr / 2, 1.0)
            if c.is_bullish:
                lv.demand_strength = strength
                lv.order_flow_bias = "bullish"
            else:
                lv.supply_strength = strength
                lv.order_flow_bias = "bearish"
            vols = [x.volume for x in candles[max(0, i-10):i+11] if x.volume > 0]
            lv.institutional_volume = bool(vols and c.volume > np.mean(vols) * 1.5)
            lv.confluence_factors.add("displacement_origin")
            levels.append(lv)

        return levels

    def _detect_session_levels(
        self, candles: List[Candle], tf: str
    ) -> List[InstitutionalLevel]:
        if len(candles) < 24:
            return []
        recent = candles[-24:]
        s_high = max(c.high for c in recent)
        s_low  = min(c.low  for c in recent)
        levels = []

        for price, kind, attr in [
            (s_high, "session_high", "supply_strength"),
            (s_low,  "session_low",  "demand_strength"),
        ]:
            c = next((x for x in recent if (x.high == s_high if kind == "session_high" else x.low == s_low)), None)
            if not c:
                continue
            lv = InstitutionalLevel(
                price=price,
                level_type=LevelType.SESSION_HIGH_LOW,
                timeframe=tf,
                creation_timestamp=c.timestamp,
                tf_weight=self.TF_WEIGHTS.get(tf, 1.0),
            )
            setattr(lv, attr, 0.7)
            lv.confluence_factors.add(kind)
            levels.append(lv)

        return levels

    def _detect_psychological_levels(
        self, candles: List[Candle], tf: str, symbol: str
    ) -> List[InstitutionalLevel]:
        if not candles:
            return []
        price = candles[-1].close
        price_range = (max(c.high for c in candles[-50:]) - min(c.low for c in candles[-50:])) if len(candles) >= 50 else price * 0.05

        if "JPY" in symbol:
            intervals = [100, 50, 20, 10]
        elif price < 2.0:
            intervals = [0.1, 0.05, 0.02, 0.01]
        elif price < 100:
            intervals = [10, 5, 2, 1]
        else:
            intervals = [1000, 500, 100, 50]

        levels = []
        for iv in intervals:
            if iv >= price_range * 0.1:
                continue
            for p in [int(price / iv + 1) * iv, int(price / iv) * iv]:
                if abs(p - price) >= price_range:
                    continue
                lv = InstitutionalLevel(
                    price=float(p),
                    level_type=LevelType.PSYCHOLOGICAL,
                    timeframe=tf,
                    creation_timestamp=candles[-1].timestamp,
                    tf_weight=self.TF_WEIGHTS.get(tf, 1.0) * 0.7,
                )
                if p > price:
                    lv.supply_strength = 0.5
                else:
                    lv.demand_strength = 0.5
                lv.confluence_factors.add("psychological")
                levels.append(lv)

        return levels

    # ------------------------------------------------------------------
    # Internal: management
    # ------------------------------------------------------------------

    def _add_new_levels(self, new_levels: List[InstitutionalLevel]):
        for nl in new_levels:
            tol = self.CLUSTER_TOLERANCE.get(nl.timeframe, 0.002)
            duplicate = False
            for ex in self.levels:
                if abs(nl.price - ex.price) / nl.price <= tol:
                    if nl.strength_score > ex.strength_score:
                        ex.price = nl.price
                        ex.level_type = nl.level_type
                    ex.confluence_factors.update(nl.confluence_factors)
                    duplicate = True
                    break
            if not duplicate:
                nl.calculate_institutional_strength()
                self.levels.append(nl)

    def _cleanup_levels(self):
        now = datetime.now()
        max_age = {
            "Monthly": 365, "Weekly": 180, "Daily": 90,
            "4H": 30, "1H": 14, "15m": 7, "5m": 3, "1m": 1,
        }
        self.levels = [
            l for l in self.levels
            if (now - l.creation_timestamp).days <= max_age.get(l.timeframe, 7)
            and l.strength_score >= 20
            and l.is_active
        ]
        if len(self.levels) > self.max_levels:
            self.levels.sort(key=lambda l: l.strength_score, reverse=True)
            self.levels = self.levels[:self.max_levels]

    def _update_clusters(self):
        from collections import defaultdict
        buckets: Dict[str, list] = defaultdict(list)
        for lv in self.levels:
            key = str(round(lv.price, 4))
            buckets[key].append(lv)
        for group in buckets.values():
            sz = len(group)
            for lv in group:
                lv.cluster_size = sz

    def _rank_levels(self):
        for lv in self.levels:
            lv.calculate_institutional_strength()
            if lv.strength_score >= 80 and lv.timeframe in ("Monthly", "Weekly"):
                lv.importance = LevelImportance.CRITICAL
            elif lv.strength_score >= 70 and lv.timeframe in ("Weekly", "Daily"):
                lv.importance = LevelImportance.HIGH
            elif lv.strength_score >= 60:
                lv.importance = LevelImportance.MEDIUM
            elif lv.strength_score >= 40:
                lv.importance = LevelImportance.LOW
            else:
                lv.importance = LevelImportance.MINIMAL
        self.levels.sort(key=lambda l: (l.importance.value, l.strength_score), reverse=False)
