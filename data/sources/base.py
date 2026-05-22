# sr_system/data/sources/base.py
"""Base class for data sources."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List
from ..ohlcv import OHLCVData


class DataSource(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def fetch(
        self,
        ticker: str,
        start: datetime,
        end: Optional[datetime] = None,
        timeframe: str = "1D",
    ) -> OHLCVData:
        """Fetch historical OHLCV data."""
        pass

    @abstractmethod
    def fetch_recent(
        self, ticker: str, bars: int, timeframe: str = "1D"
    ) -> OHLCVData:
        """Fetch most recent N bars."""
        pass

    @abstractmethod
    def get_live_bar(self, ticker: str, timeframe: str = "1D") -> Optional[OHLCVData]:
        """Get current/live bar."""
        pass

    def support_timeframes(self) -> List[str]:
        """List of supported timeframes."""
        return ["1m", "5m", "15m", "1H", "4H", "1D", "1W"]