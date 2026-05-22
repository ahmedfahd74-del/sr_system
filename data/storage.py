# sr_system/data/storage.py
"""SQLite persistence for OHLCV and S/R levels."""

import sqlite3
import os
from datetime import datetime
from typing import List, Optional
from .ohlcv import OHLCV, OHLCVData


DB_PATH = os.path.join(os.path.dirname(__file__), "sr_system.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema."""
    conn = _get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL, high REAL, low REAL,
            close REAL, volume REAL,
            UNIQUE(ticker, timeframe, timestamp)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sr_levels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            price REAL NOT NULL,
            level_type TEXT NOT NULL,  -- 'support' or 'resistance'
            confidence REAL DEFAULT 0,
            touch_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'horizontal',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT
        )
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_ohlcv_lookup
        ON ohlcv(ticker, timeframe, timestamp)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_sr_lookup
        ON sr_levels(ticker, timeframe, price)
    """)

    conn.commit()
    conn.close()


def save_ohlcv(data: OHLCVData):
    """Persist OHLCV bars to database."""
    if len(data) == 0:
        return

    conn = _get_connection()
    c = conn.cursor()

    for bar in data.bars:
        c.execute("""
            INSERT OR REPLACE INTO ohlcv
            (ticker, timeframe, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bar.ticker, bar.timeframe,
            bar.timestamp.isoformat(),
            bar.open, bar.high, bar.low, bar.close, bar.volume
        ))

    conn.commit()
    conn.close()


def load_ohlcv(ticker: str, timeframe: str,
               start: Optional[datetime] = None,
               end: Optional[datetime] = None) -> OHLCVData:
    """Load OHLCV data from database."""
    conn = _get_connection()
    c = conn.cursor()

    query = "SELECT * FROM ohlcv WHERE ticker=? AND timeframe=?"
    params = [ticker, timeframe]

    if start:
        query += " AND timestamp >= ?"
        params.append(start.isoformat())
    if end:
        query += " AND timestamp <= ?"
        params.append(end.isoformat())

    query += " ORDER BY timestamp ASC"

    rows = c.execute(query, params).fetchall()
    conn.close()

    data = OHLCVData(ticker=ticker, timeframe=timeframe)
    for row in rows:
        bar = OHLCV(
            timestamp=datetime.fromisoformat(row["timestamp"]),
            open=row["open"], high=row["high"], low=row["low"],
            close=row["close"], volume=row["volume"],
            timeframe=timeframe, ticker=ticker,
        )
        data.add(bar)

    return data


def save_sr_level(ticker: str, timeframe: str, price: float,
                  level_type: str, confidence: float = 0,
                  touch_count: int = 0, source: str = "horizontal",
                  expires_at: Optional[datetime] = None):
    """Persist an S/R level."""
    conn = _get_connection()
    c = conn.cursor()

    c.execute("""
        INSERT INTO sr_levels
        (ticker, timeframe, price, level_type, confidence, touch_count, source, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, timeframe, price, level_type,
        confidence, touch_count, source,
        expires_at.isoformat() if expires_at else None
    ))

    conn.commit()
    conn.close()


def load_sr_levels(ticker: str, timeframe: str,
                   min_confidence: float = 0) -> List[dict]:
    """Load active S/R levels."""
    conn = _get_connection()
    c = conn.cursor()

    rows = c.execute("""
        SELECT * FROM sr_levels
        WHERE ticker=? AND timeframe=? AND confidence >= ?
        ORDER BY price ASC
    """, [ticker, timeframe, min_confidence]).fetchall()

    conn.close()
    return [dict(row) for row in rows]


# Initialize on import
init_db()