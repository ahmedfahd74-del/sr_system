"""
Institutional Trading Brain
=============================
Unified integration layer that coordinates all engines.
This is the DECISION LAYER — the brain of the system.

Pipeline (in order):
    1. Environment classification  — first filter
    2. Regime adjustments          — size/stop/target multipliers
    3. Level detection             — institutional S/R
    4. Risk intelligence           — portfolio exposure check
    5. Probability scoring         — 0-100 weighted score
    6. Memory filtering            — adaptive caution
    7. Signal generation           — entry, stop, target
    8. Execution tier              — TIER_1 / TIER_2 / TIER_3 / NO_TRADE
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

from .core_data import (
    Candle,
    InstitutionalLevel,
    LevelImportance,
    MarketEnvironment,
    SetupTier,
    Signal,
)
from .levels  import InstitutionalLevelsEngine
from .memory  import MarketMemorySystem
from .regime  import EnvironmentClassifier
from .risk    import RiskIntelligenceEngine

logger = logging.getLogger(__name__)


# ================================================
# OUTPUT DATA CLASS
# ================================================

@dataclass
class AnalysisResult:
    symbol:           str
    timestamp:        datetime

    # Environment
    environment:      MarketEnvironment = MarketEnvironment.RANGING
    env_confidence:   float = 0.5

    # Signal
    signal:           Optional[Signal] = None
    execution_tier:   SetupTier = SetupTier.NO_TRADE
    raw_score:        float = 0.0
    adjusted_score:   float = 0.0

    # Supporting context
    active_levels:    List[InstitutionalLevel] = field(default_factory=list)
    condition_quality: float = 50.0
    risk_status:      dict  = field(default_factory=dict)
    filter_reason:    str   = ""

    def to_dict(self) -> dict:
        return {
            "symbol":           self.symbol,
            "timestamp":        self.timestamp.isoformat(),
            "environment":      self.environment.name,
            "env_confidence":   round(self.env_confidence, 3),
            "execution_tier":   self.execution_tier.name,
            "raw_score":        round(self.raw_score, 2),
            "adjusted_score":   round(self.adjusted_score, 2),
            "filter_reason":    self.filter_reason,
            "condition_quality": round(self.condition_quality, 2),
            "signal": {
                "direction": self.signal.direction,
                "entry":     round(self.signal.entry,  5),
                "stop":      round(self.signal.stop,   5),
                "target":    round(self.signal.target, 5),
                "score":     round(self.signal.score,  2),
            } if self.signal else None,
            "risk_status": self.risk_status,
        }


# ================================================
# BRAIN
# ================================================

class InstitutionalTradingBrain:
    """
    Unified institutional decision engine.

    Usage::

        brain = InstitutionalTradingBrain()
        result = brain.analyze(symbol="EURUSD", mtf_data={...}, account_equity=100_000)
        if result.signal:
            size = brain.risk.calculate_position_size(...)
    """

    # Score thresholds for tier classification
    TIER_THRESHOLDS = {
        SetupTier.TIER_1: 85.0,
        SetupTier.TIER_2: 75.0,
        SetupTier.TIER_3: 65.0,
    }

    def __init__(self, account_equity: float = 100_000.0):
        self.account_equity = account_equity

        # Sub-engines
        self.classifier = EnvironmentClassifier()
        self.levels_engine = InstitutionalLevelsEngine()
        self.risk     = RiskIntelligenceEngine()
        self.memory   = MarketMemorySystem()

        self._last_result: Optional[AnalysisResult] = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        mtf_data: Dict[str, List[Candle]],
        session: str = "UNKNOWN",
    ) -> AnalysisResult:
        """
        Run the full institutional analysis pipeline.
        Returns an AnalysisResult; check result.signal for the trade.
        """
        result = AnalysisResult(symbol=symbol, timestamp=datetime.now())

        # ── 1. Environment ────────────────────────────────────────────
        primary_tf  = self._pick_primary_tf(mtf_data)
        if not primary_tf:
            result.filter_reason = "INSUFFICIENT_DATA"
            return result

        primary_candles = mtf_data[primary_tf]
        env, env_conf   = self.classifier.classify_environment(primary_candles)
        result.environment    = env
        result.env_confidence = env_conf

        adjustments = self.classifier.get_environment_adjustments(env)
        if adjustments["size"] == 0.0:
            result.filter_reason = f"ENVIRONMENT_FILTERED:{env.name}"
            return result

        # ── 2. Level detection ────────────────────────────────────────
        active_levels = self.levels_engine.detect_levels(mtf_data, symbol)
        result.active_levels = active_levels

        current_price = primary_candles[-1].close
        nearby = self.levels_engine.get_levels_near_price(current_price, distance_pct=0.015)
        if not nearby:
            result.filter_reason = "NO_NEARBY_LEVELS"
            return result

        # ── 3. Score ──────────────────────────────────────────────────
        raw_score = self._calculate_score(
            nearby, primary_candles, env, env_conf, session
        )
        result.raw_score = raw_score

        # ── 4. Memory adjustment ──────────────────────────────────────
        cond_quality = self.memory.get_condition_quality(env, session, symbol)
        result.condition_quality = cond_quality

        memory_mult = cond_quality / 100.0
        if self.memory.should_reduce_aggression(symbol, env):
            memory_mult *= 0.7

        adjusted_score = raw_score * memory_mult
        result.adjusted_score = adjusted_score

        # ── 5. Tier classification ────────────────────────────────────
        tier = self._classify_tier(adjusted_score, env)
        result.execution_tier = tier

        if tier == SetupTier.NO_TRADE:
            result.filter_reason = f"BELOW_THRESHOLD:{adjusted_score:.1f}"
            return result

        # ── 6. Risk check ─────────────────────────────────────────────
        estimated_risk = self.account_equity * 0.01
        can_trade, issues = self.risk.can_take_position(
            symbol, estimated_risk, self.account_equity, env
        )
        result.risk_status = self.risk.get_status()
        if not can_trade:
            result.filter_reason = "RISK_FILTERED:" + "; ".join(issues)
            return result

        # ── 7. Build signal ───────────────────────────────────────────
        direction = self._determine_direction(nearby, primary_candles)
        if not direction:
            result.filter_reason = "NO_CLEAR_DIRECTION"
            return result

        atr    = self._atr(primary_candles)
        entry  = current_price
        stop   = entry - atr * 1.5 if direction == "BUY" else entry + atr * 1.5
        target = entry + atr * 2.5 if direction == "BUY" else entry - atr * 2.5

        # Validate R:R
        risk   = abs(entry - stop)
        reward = abs(target - entry)
        if risk <= 0 or reward / risk < 1.5:
            result.filter_reason = "POOR_RR"
            return result

        try:
            result.signal = Signal(
                symbol=symbol,
                direction=direction,
                entry=entry,
                stop=stop,
                target=target,
                score=adjusted_score,
                timestamp=datetime.now(),
                timeframe=primary_tf,
            )
        except ValueError as exc:
            result.filter_reason = f"SIGNAL_INVALID:{exc}"
            return result

        self._last_result = result
        return result

    # ------------------------------------------------------------------
    # Record outcome (for memory learning)
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        symbol: str,
        pnl: float,
        session: str,
        environment: MarketEnvironment,
        setup_type: str = "generic",
        entry_score: float = 0.0,
        duration_hours: float = 0.0,
    ):
        self.memory.record_outcome(
            pnl=pnl,
            symbol=symbol,
            session=session,
            environment=environment,
            setup_type=setup_type,
            entry_score=entry_score,
            duration_hours=duration_hours,
        )
        self.risk.record_trade_close(
            symbol=symbol,
            pnl=pnl,
            risk_amount=self.account_equity * 0.01,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_primary_tf(mtf_data: Dict[str, List[Candle]]) -> Optional[str]:
        priority = ["1H", "4H", "15m", "Daily"]
        for tf in priority:
            if tf in mtf_data and len(mtf_data[tf]) >= 20:
                return tf
        return None

    def _calculate_score(
        self,
        levels: List[InstitutionalLevel],
        candles: List[Candle],
        env: MarketEnvironment,
        env_conf: float,
        session: str,
    ) -> float:
        score = 0.0

        # Strongest nearby level (0-30)
        if levels:
            best = max(levels, key=lambda l: l.strength_score)
            score += best.strength_score * 0.30

        # Environment confidence (0-20)
        score += env_conf * 20

        # Momentum (0-20)
        rsi = self._rsi(candles)
        if 40 <= rsi <= 70:
            score += 20
        elif 30 <= rsi <= 80:
            score += 13

        # Session bonus (0-15)
        session_bonus = {
            "OVERLAP_LONDON_NY": 15, "NEW_YORK": 13, "LONDON": 11,
            "OVERLAP_ASIAN_LONDON": 7, "ASIAN": 4,
        }
        score += session_bonus.get(session, 5)

        # Trend confirmation (0-15)
        if len(candles) >= 20:
            ma20   = float(np.mean([c.close for c in candles[-20:]]))
            price  = candles[-1].close
            trend_bonus = 15 if (price > ma20 and price > candles[-3].close) or \
                                 (price < ma20 and price < candles[-3].close) else 5
            score += trend_bonus

        return min(score, 100.0)

    @staticmethod
    def _classify_tier(score: float, env: MarketEnvironment) -> SetupTier:
        # Hard restrictions
        if env == MarketEnvironment.LOW_LIQUIDITY:
            return SetupTier.NO_TRADE
        if env == MarketEnvironment.MANIPULATIVE and score >= 85:
            score = 84  # cap at TIER_2 max

        if score >= 85.0:
            return SetupTier.TIER_1
        elif score >= 75.0:
            return SetupTier.TIER_2
        elif score >= 65.0:
            return SetupTier.TIER_3
        return SetupTier.NO_TRADE

    @staticmethod
    def _determine_direction(
        levels: List[InstitutionalLevel], candles: List[Candle]
    ) -> Optional[str]:
        price = candles[-1].close
        support    = [l for l in levels if l.price < price and l.demand_strength > l.supply_strength]
        resistance = [l for l in levels if l.price > price and l.supply_strength > l.demand_strength]

        if support and not resistance:
            return "BUY"
        if resistance and not support:
            return "SELL"

        if len(candles) >= 10:
            recent = [c.close for c in candles[-10:]]
            return "BUY" if recent[-1] > recent[0] else "SELL"

        return None

    @staticmethod
    def _atr(candles: List[Candle], period: int = 14) -> float:
        if len(candles) < period + 1:
            return candles[-1].range if candles else 0.001
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
    def _rsi(candles: List[Candle], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 50.0
        closes = [c.close for c in candles]
        diffs  = np.diff(closes)
        gains  = np.where(diffs > 0, diffs, 0)
        losses = np.where(diffs < 0, -diffs, 0)
        avg_g  = float(np.mean(gains[-period:]))
        avg_l  = float(np.mean(losses[-period:]))
        if avg_l == 0:
            return 100.0
        rs  = avg_g / avg_l
        return 100 - (100 / (1 + rs))
