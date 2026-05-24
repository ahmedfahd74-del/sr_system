"""
Core Data Structures - Institutional Grade
==========================================
Immutable, validated data structures used across all modules.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Optional


# ================================================
# ENUMS
# ================================================

class LevelType(Enum):
    WEEKLY_PIVOT       = auto()
    DAILY_PIVOT        = auto()
    SESSION_HIGH_LOW   = auto()
    EQUAL_HIGHS        = auto()
    EQUAL_LOWS         = auto()
    SUPPLY_ZONE        = auto()
    DEMAND_ZONE        = auto()
    LIQUIDITY_SWEEP    = auto()
    DISPLACEMENT_ORIGIN = auto()
    FAIR_VALUE_GAP     = auto()
    ORDER_BLOCK        = auto()
    BREAKER_BLOCK      = auto()
    PSYCHOLOGICAL      = auto()
    FIBONACCI_LEVEL    = auto()

class LevelImportance(Enum):
    CRITICAL = auto()   # Monthly/Weekly
    HIGH     = auto()   # Daily
    MEDIUM   = auto()   # 4H
    LOW      = auto()   # 1H
    MINIMAL  = auto()   # LTF

class LevelReaction(Enum):
    STRONG_REJECTION = auto()
    CLEAN_REJECTION  = auto()
    WEAK_REJECTION   = auto()
    ABSORPTION       = auto()
    NO_REACTION      = auto()

class MarketEnvironment(Enum):
    TRENDING      = auto()
    RANGING       = auto()
    EXPANDING     = auto()
    CONTRACTING   = auto()
    MANIPULATIVE  = auto()
    LOW_LIQUIDITY = auto()
    DISTRIBUTION  = auto()
    ACCUMULATION  = auto()

class SessionType(Enum):
    ASIAN              = auto()
    LONDON             = auto()
    NEW_YORK           = auto()
    OVERLAP_LONDON_NY  = auto()
    OVERLAP_ASIAN_LONDON = auto()
    CLOSED             = auto()

class BiasDirection(Enum):
    BULLISH = auto()
    BEARISH = auto()
    NEUTRAL = auto()

class AssetClass(Enum):
    FOREX      = auto()
    CRYPTO     = auto()
    INDICES    = auto()
    COMMODITIES = auto()
    EQUITIES   = auto()

class SetupTier(Enum):
    TIER_1   = auto()   # Elite – full size, aggressive
    TIER_2   = auto()   # Good – reduced risk
    TIER_3   = auto()   # Marginal – watchlist only
    NO_TRADE = auto()


# ================================================
# CANDLE
# ================================================

@dataclass(frozen=True)
class Candle:
    """Immutable candle data structure with validation."""
    timestamp: datetime
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float

    def __post_init__(self):
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"Invalid candle: high {self.high} < max(o,c) {max(self.open, self.close)}"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"Invalid candle: low {self.low} > min(o,c) {min(self.open, self.close)}"
            )
        if self.volume < 0:
            raise ValueError(f"Invalid volume: {self.volume}")

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def wick_ratio(self) -> float:
        return (self.upper_wick + self.lower_wick) / self.range if self.range > 0 else 0


# ================================================
# LEVEL
# ================================================

@dataclass
class InstitutionalLevel:
    """
    Institutional-grade level with comprehensive scoring.
    Strength adapts dynamically based on market interaction.
    """
    price:              float
    level_type:         LevelType
    timeframe:          str
    creation_timestamp: datetime

    # Touch / reaction history
    touch_count:              int   = 0
    reaction_history:         List[LevelReaction] = field(default_factory=list)
    volume_at_touches:        List[float] = field(default_factory=list)
    displacement_after_touch: List[float] = field(default_factory=list)

    # Clustering & confluence
    cluster_size:       int  = 1
    confluence_factors: set  = field(default_factory=set)

    # Smart money
    sweep_count:          int   = 0
    false_break_count:    int   = 0
    institutional_volume: bool  = False

    # Adaptive state
    is_active:       bool  = True
    strength_score:  float = 50.0
    importance:      LevelImportance = LevelImportance.MEDIUM
    last_test_time:  Optional[datetime] = None

    # Supply / demand
    supply_strength:  float = 0.0
    demand_strength:  float = 0.0
    order_flow_bias:  str   = "neutral"

    # Weight
    tf_weight: float = 1.0

    def calculate_institutional_strength(self) -> float:
        """Compute composite 0-100 strength score."""
        tf_scores = {
            "Monthly": 40, "Weekly": 35, "Daily": 30,
            "4H": 25, "1H": 20, "15m": 15, "5m": 10, "1m": 5,
        }
        base = tf_scores.get(self.timeframe, 15)

        # Touch quality
        if self.touch_count > 0:
            strong = sum(
                1 for r in self.reaction_history
                if r in (LevelReaction.STRONG_REJECTION, LevelReaction.CLEAN_REJECTION)
            )
            base += (strong / len(self.reaction_history)) * 25

        if self.institutional_volume:
            base += 15
        base += min(self.sweep_count * 5, 15)
        base += min(self.cluster_size * 2, 10)
        base += min(len(self.confluence_factors) * 3, 12)

        type_bonus = {
            LevelType.WEEKLY_PIVOT: 10, LevelType.DAILY_PIVOT: 8,
            LevelType.EQUAL_HIGHS: 8,  LevelType.EQUAL_LOWS: 8,
            LevelType.SUPPLY_ZONE: 7,  LevelType.DEMAND_ZONE: 7,
            LevelType.LIQUIDITY_SWEEP: 6, LevelType.ORDER_BLOCK: 5,
            LevelType.DISPLACEMENT_ORIGIN: 5, LevelType.PSYCHOLOGICAL: 3,
        }
        base += type_bonus.get(self.level_type, 2)

        self.strength_score = min(base, 100)
        return self.strength_score

    def update_after_test(
        self,
        reaction: LevelReaction,
        volume: float,
        displacement: float,
        timestamp: datetime,
    ):
        import numpy as np
        self.touch_count += 1
        self.reaction_history.append(reaction)
        self.volume_at_touches.append(volume)
        self.displacement_after_touch.append(displacement)
        self.last_test_time = timestamp

        if len(self.volume_at_touches) >= 3:
            avg_vol = float(np.mean(self.volume_at_touches))
            if avg_vol > 0 and volume > avg_vol * 1.8:
                self.institutional_volume = True

        self.calculate_institutional_strength()


# ================================================
# SIGNAL
# ================================================

@dataclass
class Signal:
    """Trading signal with built-in validation."""
    symbol:    str
    direction: str          # "BUY" | "SELL"
    entry:     float
    stop:      float
    target:    float
    score:     float
    timestamp: datetime
    timeframe: str

    def __post_init__(self):
        if self.direction not in ("BUY", "SELL"):
            raise ValueError(f"Direction must be BUY/SELL, got {self.direction}")
        if not (0 <= self.score <= 100):
            raise ValueError(f"Score must be 0-100, got {self.score}")
        if self.direction == "BUY":
            if self.stop >= self.entry:
                raise ValueError("BUY stop must be below entry")
            if self.target <= self.entry:
                raise ValueError("BUY target must be above entry")
        else:
            if self.stop <= self.entry:
                raise ValueError("SELL stop must be above entry")
            if self.target >= self.entry:
                raise ValueError("SELL target must be below entry")
