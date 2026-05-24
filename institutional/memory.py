"""
Market Memory System — AI Learning Layer
==========================================
Remembers what works in which conditions and continuously adapts thresholds.
This is the self-optimisation layer of the institutional brain.
"""

from __future__ import annotations
import logging
import pickle
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from .core_data import MarketEnvironment

logger = logging.getLogger(__name__)


class MarketMemorySystem:
    """
    Tracks trade outcomes per market condition, session, and symbol.
    Adapts minimum score thresholds and aggression levels over time.
    """

    def __init__(self, memory_depth: int = 10_000):
        self._records: deque  = deque(maxlen=memory_depth)

        # Per-condition performance buckets
        self._condition:  Dict[str, List[float]] = defaultdict(list)
        self._setup:      Dict[str, List[float]] = defaultdict(list)
        self._symbol:     Dict[str, List[float]] = defaultdict(list)
        self._session:    Dict[str, List[float]] = defaultdict(list)

        # Dynamic thresholds (updated automatically)
        self.thresholds: Dict[str, float] = {
            "min_trade_score":       70.0,
            "environment_confidence": 0.6,
            "liquidity_threshold":   50.0,
            "structure_strength":    0.6,
        }

        self._learning_rate = 0.1
        self.consecutive_losses: int = 0

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        pnl: float,
        symbol: str,
        session: str,
        environment: MarketEnvironment,
        setup_type: str = "generic",
        entry_score: float = 0.0,
        duration_hours: float = 0.0,
    ):
        """Record a single trade outcome."""
        rec = {
            "timestamp":    datetime.now(),
            "pnl":          pnl,
            "win":          pnl > 0,
            "symbol":       symbol,
            "session":      session,
            "environment":  environment,
            "setup_type":   setup_type,
            "entry_score":  entry_score,
            "duration_h":   duration_hours,
        }
        self._records.append(rec)

        condition_key = f"{environment.name}_{session}"
        self._condition[condition_key].append(pnl)
        self._setup[setup_type].append(pnl)
        self._symbol[symbol].append(pnl)
        self._session[session].append(pnl)

        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # Adapt thresholds every 10 trades
        if len(self._records) % 10 == 0:
            self._adapt_thresholds()

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_condition_quality(
        self,
        environment: MarketEnvironment,
        session: str,
        symbol: str,
    ) -> float:
        """Returns a 0-100 quality score for current conditions."""
        scores: List[tuple] = []

        condition_key = f"{environment.name}_{session}"
        cond_outs = self._condition.get(condition_key, [])
        if cond_outs:
            recent = cond_outs[-20:]
            wr     = sum(1 for x in recent if x > 0) / len(recent)
            avg    = float(np.mean(recent))
            scores.append(((wr * 50) + min(avg / 100, 0.5) * 100, 0.4))

        sym_outs = self._symbol.get(symbol, [])
        if sym_outs:
            recent = sym_outs[-15:]
            wr     = sum(1 for x in recent if x > 0) / len(recent)
            scores.append((wr * 100, 0.3))

        ses_outs = self._session.get(session, [])
        if ses_outs:
            recent = ses_outs[-25:]
            wr     = sum(1 for x in recent if x > 0) / len(recent)
            scores.append((wr * 100, 0.3))

        if not scores:
            return 50.0

        total_w = sum(w for _, w in scores)
        return sum(s * w for s, w in scores) / total_w

    def should_reduce_aggression(self, symbol: str, environment: MarketEnvironment) -> bool:
        """True if recent performance signals caution."""
        candidates = [
            r for r in list(self._records)[-50:]
            if r["symbol"] == symbol or r["environment"] == environment
        ]
        if len(candidates) < 5:
            return False

        wins = sum(1 for r in candidates if r["win"])
        wr   = wins / len(candidates)
        avg  = float(np.mean([r["pnl"] for r in candidates]))

        return wr < 0.4 or self.consecutive_losses >= 4 or avg < -50

    def get_best_setup_types(self, environment: MarketEnvironment) -> List[str]:
        """Return setup types that perform best in the given environment."""
        env_recs = [r for r in self._records if r["environment"] == environment]
        if len(env_recs) < 10:
            return ["continuation", "reversal"]

        perf: Dict[str, List[float]] = defaultdict(list)
        for r in env_recs[-50:]:
            perf[r["setup_type"]].append(r["pnl"])

        ranked = []
        for st, outs in perf.items():
            if len(outs) < 3:
                continue
            wr  = sum(1 for x in outs if x > 0) / len(outs)
            avg = float(np.mean(outs))
            ranked.append((st, wr * avg))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in ranked[:3]] or ["continuation"]

    # ------------------------------------------------------------------
    # Internal: adaptation
    # ------------------------------------------------------------------

    def _adapt_thresholds(self):
        recent = list(self._records)[-20:]
        if len(recent) < 20:
            return

        wr  = sum(1 for r in recent if r["win"]) / len(recent)
        avg = float(np.mean([r["pnl"] for r in recent]))

        if wr < 0.45:
            self.thresholds["min_trade_score"] = min(
                self.thresholds["min_trade_score"] + self._learning_rate * 5, 85.0
            )
        elif wr > 0.65:
            self.thresholds["min_trade_score"] = max(
                self.thresholds["min_trade_score"] - self._learning_rate * 2, 60.0
            )

        logger.debug("Memory thresholds updated: %s", self.thresholds)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, filepath: str):
        data = {
            "records":    list(self._records),
            "condition":  dict(self._condition),
            "setup":      dict(self._setup),
            "symbol":     dict(self._symbol),
            "session":    dict(self._session),
            "thresholds": self.thresholds,
        }
        with open(filepath, "wb") as f:
            pickle.dump(data, f)
        logger.info("Memory saved to %s", filepath)

    def load(self, filepath: str):
        try:
            with open(filepath, "rb") as f:
                data = pickle.load(f)
            self._records   = deque(data["records"],   maxlen=10_000)
            self._condition = defaultdict(list, data["condition"])
            self._setup     = defaultdict(list, data["setup"])
            self._symbol    = defaultdict(list, data["symbol"])
            self._session   = defaultdict(list, data["session"])
            self.thresholds = data["thresholds"]
            logger.info("Memory loaded from %s", filepath)
        except Exception as exc:
            logger.error("Failed to load memory: %s", exc)
