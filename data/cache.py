# sr_system/data/cache.py
"""In-memory caching for OHLCV and S/R levels."""

from datetime import datetime, timedelta
from typing import Dict, Optional
from threading import Lock
from .ohlcv import OHLCVData


class DataCache:
    """Thread-safe in-memory cache for OHLCV data and computed S/R levels."""

    def __init__(self, default_ttl: int = 60):
        self.default_ttl = default_ttl  # seconds
        self._ohlcv: Dict[str, tuple[OHLCVData, datetime]] = {}
        self._sr_levels: Dict[str, tuple[list, datetime]] = {}
        self._lock = Lock()

    def _key(self, ticker: str, timeframe: str, suffix: str = "") -> str:
        return f"{ticker}:{timeframe}:{suffix}"

    def get_ohlcv(self, ticker: str, timeframe: str) -> Optional[OHLCVData]:
        with self._lock:
            entry = self._ohlcv.get(self._key(ticker, timeframe))
            if entry is None:
                return None
            data, cached_at = entry
            if datetime.now() - cached_at > timedelta(seconds=self.default_ttl):
                del self._ohlcv[self._key(ticker, timeframe)]
                return None
            return data

    def set_ohlcv(self, ticker: str, timeframe: str, data: OHLCVData):
        with self._lock:
            self._ohlcv[self._key(ticker, timeframe)] = (data, datetime.now())

    def get_sr_levels(self, ticker: str, timeframe: str) -> Optional[list]:
        with self._lock:
            entry = self._sr_levels.get(self._key(ticker, timeframe, "sr"))
            if entry is None:
                return None
            levels, cached_at = entry
            if datetime.now() - cached_at > timedelta(seconds=self.default_ttl):
                del self._sr_levels[self._key(ticker, timeframe, "sr")]
                return None
            return levels

    def set_sr_levels(self, ticker: str, timeframe: str, levels: list):
        with self._lock:
            self._sr_levels[self._key(ticker, timeframe, "sr")] = (levels, datetime.now())

    def invalidate(self, ticker: str, timeframe: str):
        with self._lock:
            self._ohlcv.pop(self._key(ticker, timeframe), None)
            self._sr_levels.pop(self._key(ticker, timeframe, "sr"), None)

    def clear(self):
        with self._lock:
            self._ohlcv.clear()
            self._sr_levels.clear()


# Global cache instance
_cache = DataCache()


def get_cache() -> DataCache:
    return _cache