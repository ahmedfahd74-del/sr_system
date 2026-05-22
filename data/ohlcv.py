# sr_system/data/ohlcv.py
"""OHLCV data structures."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import numpy as np


@dataclass
class OHLCV:
    """Single OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str = "1D"
    ticker: str = ""

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


class OHLCVData:
    """In-memory collection of OHLCV bars with computed metrics."""

    def __init__(self, ticker: str = "", timeframe: str = "1D"):
        self.ticker = ticker
        self.timeframe = timeframe
        self.bars: list[OHLCV] = []

    def add(self, bar: OHLCV):
        self.bars.append(bar)

    def __len__(self) -> int:
        return len(self.bars)

    def __getitem__(self, i) -> OHLCV:
        return self.bars[i]

    @property
    def closes(self) -> np.ndarray:
        return np.array([b.close for b in self.bars])

    @property
    def opens(self) -> np.ndarray:
        return np.array([b.open for b in self.bars])

    @property
    def highs(self) -> np.ndarray:
        return np.array([b.high for b in self.bars])

    @property
    def lows(self) -> np.ndarray:
        return np.array([b.low for b in self.bars])

    @property
    def volumes(self) -> np.ndarray:
        return np.array([b.volume for b in self.bars])

    @property
    def timestamps(self) -> list[datetime]:
        return [b.timestamp for b in self.bars]

    def last_n(self, n: int) -> "OHLCVData":
        """Return a new OHLCVData with last n bars."""
        data = OHLCVData(self.ticker, self.timeframe)
        data.bars = self.bars[-n:]
        return data

    def tail(self, n: int) -> "OHLCVData":
        return self.last_n(n)