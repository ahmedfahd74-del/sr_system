# sr_system/data/sources/yahoo_direct.py
"""Direct Yahoo Finance API using requests (avoids curl_cffi issues)."""

from datetime import datetime
from typing import Optional
import requests
import numpy as np
from .base import DataSource
from ..ohlcv import OHLCV, OHLCVData


# Map our timeframe strings to Yahoo intervals
TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1wk",
}


def _get_yahoo_chart_url(ticker: str, period: str = "2y", interval: str = "1d") -> str:
    """Build Yahoo Finance chart URL."""
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1=0&period2=0&interval={interval}"


def _parse_yahoo_json(ticker: str, timeframe: str, json_data: dict) -> OHLCVData:
    """Parse Yahoo Finance JSON response into OHLCVData."""
    data = OHLCVData(ticker=ticker, timeframe=timeframe)
    
    try:
        result = json_data.get("chart", {}).get("result", [{}])[0]
        timestamps = result.get("timestamp", [])
        ohlcv = result.get("indicators", {}).get("quote", [{}])[0]
        
        opens = ohlcv.get("open", [])
        highs = ohlcv.get("high", [])
        lows = ohlcv.get("low", [])
        closes = ohlcv.get("close", [])
        volumes = result.get("indicators", {}).get("quote", [{}])[0].get("volume", [])
        
        for i, ts in enumerate(timestamps):
            if i >= len(opens) or opens[i] is None:
                continue
            bar = OHLCV(
                timestamp=datetime.fromtimestamp(ts),
                open=float(opens[i]),
                high=float(highs[i]) if i < len(highs) and highs[i] else float(opens[i]),
                low=float(lows[i]) if i < len(lows) and lows[i] else float(opens[i]),
                close=float(closes[i]) if i < len(closes) and closes[i] else float(opens[i]),
                volume=float(volumes[i]) if i < len(volumes) and volumes[i] else 0,
                timeframe=timeframe,
                ticker=ticker,
            )
            data.add(bar)
    except (KeyError, IndexError, TypeError) as e:
        print(f"Parse error: {e}")
    
    return data


class YahooFinanceSource(DataSource):
    """Yahoo Finance data provider - direct HTTP requests."""

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
        
        period1 = int(start.timestamp())
        period2 = int(end_dt.timestamp())
        
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?period1={period1}&period2={period2}&interval={interval}"
        )
        
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            json_data = resp.json()
            return _parse_yahoo_json(ticker, timeframe, json_data)
        except Exception as e:
            print(f"Yahoo fetch error: {e}")
            return OHLCVData(ticker=ticker, timeframe=timeframe)

    def fetch_recent(
        self, ticker: str, bars: int, timeframe: str = "1D"
    ) -> OHLCVData:
        """Fetch most recent N bars."""
        interval = TF_MAP.get(timeframe, "1d")
        
        # Use range endpoint for recent data
        range_map = {
            "1m": "1d", "5m": "5d", "15m": "5d",
            "1H": "1mo", "4H": "1mo", "1D": "2y", "1W": "5y"
        }
        period = range_map.get(timeframe, "2y")
        
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?range={period}&interval={interval}"
        )
        
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = _parse_yahoo_json(ticker, timeframe, resp.json())
            # Trim to last N bars
            if len(data) > bars:
                data.bars = data.bars[-bars:]
            return data
        except Exception as e:
            print(f"Yahoo fetch_recent error: {e}")
            return OHLCVData(ticker=ticker, timeframe=timeframe)

    def get_live_bar(self, ticker: str, timeframe: str = "1D") -> Optional[OHLCVData]:
        """Get last available bar as 'live'."""
        data = self.fetch_recent(ticker, bars=1, timeframe=timeframe)
        return data if len(data) > 0 else None