# sr_system/data/sources/yahoo.py
"""Yahoo Finance data source implementation."""

from datetime import datetime
from typing import Optional
import yfinance as yf
from .base import DataSource
from ..ohlcv import OHLCV, OHLCVData


# Map our timeframe strings to yfinance intervals
TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1wk",
}


class YahooFinanceSource(DataSource):
    """Yahoo Finance data provider - free, no API key needed."""

    def fetch(
        self,
        ticker: str,
        start: datetime,
        end: Optional[datetime] = None,
        timeframe: str = "1D",
    ) -> OHLCVData:
        """Fetch historical data from Yahoo Finance."""
        interval = TF_MAP.get(timeframe, "1d")
        end_dt = end or datetime.now()

        yf_ticker = yf.Ticker(ticker)
        hist = yf_ticker.history(start=start, end=end_dt, interval=interval, auto_adjust=True)

        data = OHLCVData(ticker=ticker, timeframe=timeframe)
        for ts, row in hist.iterrows():
            bar = OHLCV(
                timestamp=ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                timeframe=timeframe,
                ticker=ticker,
            )
            data.add(bar)

        return data

    def fetch_recent(
        self, ticker: str, bars: int, timeframe: str = "1D"
    ) -> OHLCVData:
        """Fetch most recent N bars."""
        interval = TF_MAP.get(timeframe, "1d")
        yf_ticker = yf.Ticker(ticker)

        # period="max" with desired number of bars
        # yfinance doesn't directly support N bars, so we fetch period and slice
        hist = yf_ticker.history(period="2y", interval=interval, auto_adjust=True)

        data = OHLCVData(ticker=ticker, timeframe=timeframe)
        # Take last N bars
        for ts, row in hist.tail(bars).iterrows():
            bar = OHLCV(
                timestamp=ts.to_pydatetime(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                timeframe=timeframe,
                ticker=ticker,
            )
            data.add(bar)

        return data

    def get_live_bar(self, ticker: str, timeframe: str = "1D") -> Optional[OHLCVData]:
        """Get last available bar as 'live'."""
        data = self.fetch_recent(ticker, bars=1, timeframe=timeframe)
        return data if len(data) > 0 else None