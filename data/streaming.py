# sr_system/data/streaming.py
"""WebSocket streaming client for real-time market data."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
import json
import threading
import time
from collections import deque


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class StreamConfig:
    """Configuration for streaming connection."""
    # Data source
    source: str = "yahoo"  # "yahoo" or "alpaca"
    # Yahoo Finance WebSocket (doesn't need auth)
    yahoo_ws_url: str = "wss://streamer.finance.yahoo.com"
    # Alpaca WebSocket (requires API key)
    alpaca_ws_url: str = "wss://stream.data.alpaca.markets"
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    # Reconnection settings
    reconnect_delay: float = 1.0  # Initial delay in seconds
    max_reconnect_delay: float = 60.0  # Max delay
    reconnect_backoff_mult: float = 2.0  # Exponential backoff multiplier
    max_reconnect_attempts: int = 10
    # Heartbeat/ping settings
    ping_interval: float = 30.0  # Seconds between pings
    ping_timeout: float = 10.0  # Seconds to wait for pong
    # Rate limiting
    max_messages_per_second: int = 10
    # Subscription management
    batch_size: int = 5  # Max tickers per subscription message


@dataclass
class ConnectionStats:
    """Connection statistics."""
    connected_at: Optional[datetime] = None
    messages_received: int = 0
    messages_sent: int = 0
    reconnect_count: int = 0
    last_message_at: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "reconnect_count": self.reconnect_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "error_count": len(self.errors)
        }


@dataclass
class TickData:
    """Represents a single price tick."""
    ticker: str
    price: float
    volume: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "bid": self.bid,
            "ask": self.ask,
            "source": self.source
        }


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, max_per_second: int = 10):
        self.max_per_second = max_per_second
        self.tokens = max_per_second
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a token. Returns True if allowed."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.max_per_second, self.tokens + elapsed * self.max_per_second)
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def wait_time(self) -> float:
        """Get seconds to wait before next token available."""
        with self.lock:
            if self.tokens >= 1:
                return 0
            return (1 - self.tokens) / self.max_per_second


class DataStreamer:
    """
    WebSocket-based real-time data streamer.

    Supports Yahoo Finance (no auth) and Alpaca (API key required).
    Handles reconnection with exponential backoff.
    """

    def __init__(self, config: Optional[StreamConfig] = None):
        self.config = config or StreamConfig()
        self.state = ConnectionState.DISCONNECTED
        self.stats = ConnectionStats()
        self._ws = None  # WebSocket connection
        self._thread = None  # Connection thread
        self._running = False
        self._lock = threading.Lock()

        # Subscriptions
        self._subscriptions: Dict[str, List[str]] = {}  # ticker -> timeframes

        # Callbacks
        self._tick_callbacks: List[Callable[[TickData], None]] = []
        self._status_callbacks: List[Callable[[ConnectionState], None]] = []

        # Rate limiter
        self._rate_limiter = RateLimiter(self.config.max_messages_per_second)

        # Message buffer for batching
        self._message_buffer: deque = deque(maxlen=100)

    def add_tick_callback(self, callback: Callable[[TickData], None]):
        """Add callback for tick data."""
        self._tick_callbacks.append(callback)

    def add_status_callback(self, callback: Callable[[ConnectionState], None]):
        """Add callback for connection status changes."""
        self._status_callbacks.append(callback)

    def _set_state(self, new_state: ConnectionState):
        """Update connection state and notify callbacks."""
        with self._lock:
            if self.state != new_state:
                self.state = new_state
                for callback in self._status_callbacks:
                    try:
                        callback(new_state)
                    except Exception as e:
                        print(f"Status callback error: {e}")

    def subscribe(self, tickers: List[str], timeframes: List[str] = ["1m"]):
        """
        Subscribe to tick data for tickers.

        Args:
            tickers: List of ticker symbols
            timeframes: List of timeframes (e.g., ["1m", "5m"])
        """
        with self._lock:
            for ticker in tickers:
                self._subscriptions[ticker] = timeframes

        if self.state == ConnectionState.CONNECTED:
            self._send_subscription(tickers, timeframes)

    def unsubscribe(self, tickers: List[str]):
        """Unsubscribe from tickers."""
        with self._lock:
            for ticker in tickers:
                if ticker in self._subscriptions:
                    del self._subscriptions[ticker]

        if self.state == ConnectionState.CONNECTED:
            self._send_unsubscription(tickers)

    def _send_subscription(self, tickers: List[str], timeframes: List[str]):
        """Send subscription message to WebSocket."""
        if self.config.source == "yahoo":
            self._send_yahoo_subscription(tickers)
        elif self.config.source == "alpaca":
            self._send_alpaca_subscription(tickers)

    def _send_unsubscription(self, tickers: List[str]):
        """Send unsubscription message to WebSocket."""
        # Similar to subscription but with unsubscribe payload
        pass

    def _send_yahoo_subscription(self, tickers: List[str]):
        """Send subscription to Yahoo Finance WebSocket."""
        if not self._ws:
            return

        try:
            # Yahoo Finance uses simple format
            payload = {
                "subscribe": tickers,
                "threshold": 10000
            }
            self._ws.send(json.dumps(payload))
            self.stats.messages_sent += 1
        except Exception as e:
            self._handle_error(f"Failed to send Yahoo subscription: {e}")

    def _send_alpaca_subscription(self, tickers: List[str]):
        """Send subscription to Alpaca WebSocket."""
        if not self._ws:
            return

        try:
            payload = {
                "action": "subscribe",
                "trades": tickers,
                "quotes": tickers
            }
            self._ws.send(json.dumps(payload))
            self.stats.messages_sent += 1
        except Exception as e:
            self._handle_error(f"Failed to send Alpaca subscription: {e}")

    def connect(self):
        """Start the streaming connection."""
        if self.state in [ConnectionState.CONNECTING, ConnectionState.CONNECTED]:
            return

        self._running = True
        self._thread = threading.Thread(target=self._connection_loop, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Stop the streaming connection."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._set_state(ConnectionState.DISCONNECTED)

    def _connection_loop(self):
        """Main connection loop with reconnection logic."""
        delay = self.config.reconnect_delay
        attempts = 0

        while self._running and attempts < self.config.max_reconnect_attempts:
            self._set_state(ConnectionState.CONNECTING)

            try:
                self._establish_connection()
                delay = self.config.reconnect_delay  # Reset on successful connection
                attempts = 0
                self._set_state(ConnectionState.CONNECTED)
                self.stats.connected_at = datetime.now()
                self._listen_loop()
            except Exception as e:
                self._handle_error(f"Connection error: {e}")
                self._set_state(ConnectionState.RECONNECTING)

            if self._running:
                time.sleep(delay)
                delay = min(delay * self.config.reconnect_backoff_mult,
                           self.config.max_reconnect_delay)
                attempts += 1
                self.stats.reconnect_count = attempts

        if attempts >= self.config.max_reconnect_attempts:
            self._set_state(ConnectionState.ERROR)
            self._handle_error("Max reconnection attempts reached")

    def _establish_connection(self):
        """Establish WebSocket connection."""
        try:
            import websocket

            if self.config.source == "yahoo":
                url = self.config.yahoo_ws_url
            elif self.config.source == "alpaca":
                url = self.config.alpaca_ws_url
            else:
                raise ValueError(f"Unknown source: {self.config.source}")

            # Create WebSocket app
            self._ws = websocket.WebSocketApp(
                url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )

        except ImportError:
            raise RuntimeError("websocket-client library not installed. Run: pip install websocket-client")

    def _listen_loop(self):
        """Main listening loop."""
        while self._running and self._ws:
            try:
                # Use select-like approach with timeout for clean exit
                self._ws.sock.settimeout(1.0)
                # This will throw if connection is closed
                if self._ws.sock and self._ws.sock.connected:
                    # Keep connection alive - actual message handling is in on_message callback
                    pass
            except Exception:
                if self._running:
                    raise
                break

    def _on_open(self, ws):
        """Called when WebSocket is opened."""
        # Resubscribe to all tickers
        if self._subscriptions:
            for ticker, timeframes in self._subscriptions.items():
                self._send_subscription([ticker], timeframes)

    def _on_message(self, ws, message):
        """Called when WebSocket receives a message."""
        self.stats.messages_received += 1
        self.stats.last_message_at = datetime.now()

        try:
            data = json.loads(message)
            ticks = self._parse_message(data)
            for tick in ticks:
                self._dispatch_tick(tick)
        except Exception as e:
            self._handle_error(f"Failed to parse message: {e}")

    def _parse_message(self, data: dict) -> List[TickData]:
        """Parse WebSocket message into TickData objects."""
        ticks = []

        if self.config.source == "yahoo":
            # Yahoo Finance message format
            if "stream" in data:
                stream_data = data["stream"]
                if "data" in stream_data:
                    d = stream_data["data"]
                    tick = TickData(
                        ticker=d.get("symbol", ""),
                        price=float(d.get("price", 0)),
                        volume=float(d.get("volume", 0)),
                        timestamp=datetime.now(),
                        source="yahoo"
                    )
                    ticks.append(tick)

        elif self.config.source == "alpaca":
            # Alpaca message format
            if "data" in data:
                d = data["data"]
                tick = TickData(
                    ticker=d.get("S", ""),
                    price=float(d.get("p", 0)),
                    volume=float(d.get("v", 0)),
                    timestamp=datetime.fromtimestamp(d.get("t", 0) / 1000),
                    bid=float(d.get("b", 0)) if "b" in d else None,
                    ask=float(d.get("a", 0)) if "a" in d else None,
                    source="alpaca"
                )
                ticks.append(tick)

        return ticks

    def _dispatch_tick(self, tick: TickData):
        """Dispatch tick to callbacks with rate limiting."""
        # Rate limit check
        if not self._rate_limiter.acquire():
            # Buffer for later processing
            self._message_buffer.append(tick)
            return

        # Process buffered messages first
        while self._message_buffer and self._rate_limiter.acquire():
            buffered_tick = self._message_buffer.popleft()
            for callback in self._tick_callbacks:
                try:
                    callback(buffered_tick)
                except Exception as e:
                    self._handle_error(f"Tick callback error: {e}")

        # Process current tick
        for callback in self._tick_callbacks:
            try:
                callback(tick)
            except Exception as e:
                self._handle_error(f"Tick callback error: {e}")

    def _on_error(self, ws, error):
        """Called when WebSocket has an error."""
        self._handle_error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Called when WebSocket is closed."""
        self._ws = None

    def _handle_error(self, error_msg: str):
        """Handle errors and log."""
        print(f"Streaming error: {error_msg}")
        self.stats.errors.append(f"{datetime.now().isoformat()}: {error_msg}")

    def get_stats(self) -> dict:
        """Get connection statistics."""
        return self.stats.to_dict()

    def get_state(self) -> ConnectionState:
        """Get current connection state."""
        return self.state

    def is_connected(self) -> bool:
        """Check if connected."""
        return self.state == ConnectionState.CONNECTED


# Simulated streamer for testing without real WebSocket
class SimulatedStreamer:
    """Simulated data streamer for testing."""

    def __init__(self, tick_interval: float = 1.0):
        self.tick_interval = tick_interval
        self._running = False
        self._thread = None
        self._callbacks: List[Callable[[TickData], None]] = []
        self._tickers: List[str] = []

    def add_tick_callback(self, callback: Callable[[TickData], None]):
        self._callbacks.append(callback)

    def subscribe(self, tickers: List[str], timeframes: List[str] = None):
        self._tickers = tickers

    def unsubscribe(self, tickers: List[str]):
        self._tickers = [t for t in self._tickers if t not in tickers]

    def connect(self):
        self._running = True
        self._thread = threading.Thread(target=self._simulate, daemon=True)
        self._thread.start()

    def disconnect(self):
        self._running = False

    def _simulate(self):
        import random
        base_prices = {t: 100 + random.random() * 100 for t in self._tickers}

        while self._running:
            for ticker in self._tickers:
                # Simulate price movement
                change = random.uniform(-0.5, 0.5)
                base_prices[ticker] += change
                base_prices[ticker] = max(50, base_prices[ticker])  # Floor at 50

                tick = TickData(
                    ticker=ticker,
                    price=base_prices[ticker],
                    volume=random.randint(100000, 1000000),
                    timestamp=datetime.now(),
                    source="simulated"
                )

                for callback in self._callbacks:
                    try:
                        callback(tick)
                    except Exception:
                        pass

            time.sleep(self.tick_interval)

    def is_connected(self) -> bool:
        return self._running


def create_streamer(config: Optional[StreamConfig] = None, simulated: bool = False) -> Any:
    """
    Factory function to create a data streamer.

    Args:
        config: Stream configuration
        simulated: If True, return SimulatedStreamer for testing

    Returns:
        DataStreamer or SimulatedStreamer instance
    """
    if simulated:
        return SimulatedStreamer()
    return DataStreamer(config)