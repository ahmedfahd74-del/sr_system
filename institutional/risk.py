"""
Institutional Risk Intelligence Engine
========================================
Manages EXPOSURE, not just individual trades.
Handles dynamic position sizing, drawdown protection,
correlation limits, and defensive mode triggers.
"""

from __future__ import annotations
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .core_data import AssetClass, MarketEnvironment

logger = logging.getLogger(__name__)


class RiskIntelligenceEngine:
    """
    Portfolio-level risk management system.
    Every new position must pass through this engine before execution.
    """

    # Correlation groupings
    CORRELATION_GROUPS: Dict[str, List[str]] = {
        "USD_MAJORS":  ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
        "USD_OTHERS":  ["USDJPY", "USDCHF", "USDCAD"],
        "CRYPTO_MAJOR": ["BTCUSD", "ETHUSD"],
        "CRYPTO_ALT":  ["ADAUSD", "DOTUSD", "LINKUSD"],
        "INDICES":     ["SPX500", "NAS100", "GER40", "US30"],
        "COMMODITIES": ["XAUUSD", "XAGUSD", "WTIUSD"],
    }

    def __init__(
        self,
        max_risk_per_trade: float = 0.01,   # 1 %
        max_portfolio_risk:  float = 0.05,   # 5 %
        max_daily_loss:      float = 0.02,   # 2 %
        max_consecutive_losses: int = 5,
    ):
        self.max_risk_per_trade = max_risk_per_trade
        self.max_portfolio_risk  = max_portfolio_risk
        self.max_daily_loss      = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses

        self._lock = threading.RLock()

        # Live state
        self.current_risk:      float = 0.0
        self.daily_pnl:         float = 0.0
        self.daily_loss:        float = 0.0
        self.consecutive_losses: int  = 0
        self.dynamic_risk_multiplier: float = 1.0
        self.defensive_mode:    bool  = False

        # Exposure by group
        self._correlation_exposure: Dict[str, float] = defaultdict(float)
        self._asset_class_exposure: Dict[str, float] = defaultdict(float)

        # Alert queue
        self.risk_alerts: deque = deque(maxlen=100)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def can_take_position(
        self,
        symbol: str,
        risk_amount: float,
        account_equity: float,
        environment: Optional[MarketEnvironment] = None,
    ) -> Tuple[bool, List[str]]:
        """Returns (can_trade, list_of_blocking_reasons)."""
        issues: List[str] = []

        with self._lock:
            # Daily loss guard
            if self.daily_loss >= account_equity * self.max_daily_loss:
                issues.append("Daily loss limit reached")

            # Portfolio heat guard
            if self.current_risk + risk_amount > account_equity * self.max_portfolio_risk:
                issues.append("Portfolio risk limit exceeded")

            # Consecutive losses guard
            if self.consecutive_losses >= self.max_consecutive_losses:
                issues.append("Consecutive loss limit reached — trading suspended")

            # Correlation guard
            group = self._get_correlation_group(symbol)
            group_exposure = self._correlation_exposure.get(group, 0.0)
            if group_exposure + risk_amount > account_equity * 0.03:
                issues.append(f"Correlation group '{group}' exposure limit exceeded")

            # Environment guard
            if environment == MarketEnvironment.LOW_LIQUIDITY:
                issues.append("Low liquidity environment — no new positions")

        return (len(issues) == 0, issues)

    def calculate_position_size(
        self,
        account_equity: float,
        entry_price: float,
        stop_price: float,
        signal_score: float = 75.0,
        environment: Optional[MarketEnvironment] = None,
    ) -> float:
        """Returns units to trade (0 = do not trade)."""
        with self._lock:
            risk_per_unit = abs(entry_price - stop_price)
            if risk_per_unit <= 0:
                return 0.0

            base_risk = account_equity * self.max_risk_per_trade

            # Score multiplier
            if signal_score >= 90:
                score_mult = 1.3
            elif signal_score >= 80:
                score_mult = 1.1
            elif signal_score >= 75:
                score_mult = 1.0
            elif signal_score >= 70:
                score_mult = 0.8
            else:
                score_mult = 0.5

            # Environment multiplier
            env_mult = {
                MarketEnvironment.TRENDING:      1.2,
                MarketEnvironment.RANGING:       0.9,
                MarketEnvironment.EXPANDING:     1.0,
                MarketEnvironment.CONTRACTING:   0.6,
                MarketEnvironment.MANIPULATIVE:  0.4,
                MarketEnvironment.LOW_LIQUIDITY: 0.0,
            }.get(environment, 1.0)

            # Consecutive loss mult
            loss_mult = max(1.0 - self.consecutive_losses * 0.15, 0.3)

            final_risk = (
                base_risk
                * score_mult
                * env_mult
                * loss_mult
                * self.dynamic_risk_multiplier
            )

            return max(final_risk / risk_per_unit, 0.0)

    def register_open_position(self, symbol: str, risk_amount: float, account_equity: float):
        """Call when a position is opened."""
        with self._lock:
            self.current_risk += risk_amount
            group = self._get_correlation_group(symbol)
            self._correlation_exposure[group] += risk_amount
            asset_class = self._classify_asset(symbol)
            self._asset_class_exposure[asset_class] += risk_amount

    def record_trade_close(
        self,
        symbol: str,
        pnl: float,
        risk_amount: float,
    ):
        """Call when a position is closed."""
        with self._lock:
            self.daily_pnl  += pnl
            self.current_risk = max(0.0, self.current_risk - risk_amount)

            group = self._get_correlation_group(symbol)
            self._correlation_exposure[group] = max(
                0.0, self._correlation_exposure[group] - risk_amount
            )
            asset_class = self._classify_asset(symbol)
            self._asset_class_exposure[asset_class] = max(
                0.0, self._asset_class_exposure[asset_class] - risk_amount
            )

            if pnl < 0:
                self.daily_loss += abs(pnl)
                self.consecutive_losses += 1
                if self.consecutive_losses >= 3:
                    self.defensive_mode = True
                    self.dynamic_risk_multiplier = max(self.dynamic_risk_multiplier * 0.8, 0.4)
                    logger.warning("Defensive mode activated — risk reduced")
            else:
                self.consecutive_losses = 0
                if self.defensive_mode and self.daily_pnl > 0:
                    self.defensive_mode = False
                    self.dynamic_risk_multiplier = min(self.dynamic_risk_multiplier * 1.05, 1.3)
                    logger.info("Defensive mode deactivated")

    def reset_daily(self):
        with self._lock:
            self.daily_pnl  = 0.0
            self.daily_loss = 0.0

    def get_status(self) -> dict:
        with self._lock:
            return {
                "current_risk":          round(self.current_risk, 4),
                "daily_pnl":             round(self.daily_pnl, 4),
                "daily_loss":            round(self.daily_loss, 4),
                "consecutive_losses":    self.consecutive_losses,
                "defensive_mode":        self.defensive_mode,
                "dynamic_risk_mult":     round(self.dynamic_risk_multiplier, 3),
                "correlation_exposure":  dict(self._correlation_exposure),
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_correlation_group(self, symbol: str) -> str:
        for group, symbols in self.CORRELATION_GROUPS.items():
            if symbol in symbols:
                return group
        return "OTHER"

    @staticmethod
    def _classify_asset(symbol: str) -> str:
        if any(x in symbol for x in ("BTC", "ETH", "ADA", "DOT", "LINK")):
            return "CRYPTO"
        if symbol in ("SPX500", "NAS100", "GER40", "US30"):
            return "INDICES"
        if symbol in ("XAUUSD", "XAGUSD", "WTIUSD"):
            return "COMMODITIES"
        return "FOREX"
