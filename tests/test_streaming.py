# tests/test_streaming.py
"""Unit tests for WebSocket streaming module (Phase 4)."""

import unittest
from datetime import datetime
import time
import threading
from data.streaming import (
    StreamConfig, ConnectionStats, TickData, RateLimiter,
    DataStreamer, SimulatedStreamer, create_streamer,
    ConnectionState
)


class TestStreamConfig(unittest.TestCase):
    """Tests for stream configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = StreamConfig()
        self.assertEqual(config.source, "yahoo")
        self.assertEqual(config.max_messages_per_second, 10)
        self.assertEqual(config.reconnect_delay, 1.0)
        self.assertEqual(config.max_reconnect_attempts, 10)

    def test_custom_config(self):
        """Test custom configuration."""
        config = StreamConfig(
            source="alpaca",
            alpaca_api_key="test_key",
            reconnect_delay=2.0,
            max_messages_per_second=20
        )
        self.assertEqual(config.source, "alpaca")
        self.assertEqual(config.alpaca_api_key, "test_key")
        self.assertEqual(config.reconnect_delay, 2.0)
        self.assertEqual(config.max_messages_per_second, 20)


class TestConnectionStats(unittest.TestCase):
    """Tests for connection statistics."""

    def test_initial_stats(self):
        """Test initial statistics are zeroed."""
        stats = ConnectionStats()
        self.assertIsNone(stats.connected_at)
        self.assertEqual(stats.messages_received, 0)
        self.assertEqual(stats.messages_sent, 0)
        self.assertEqual(stats.reconnect_count, 0)

    def test_to_dict(self):
        """Test statistics serialization."""
        stats = ConnectionStats()
        stats.connected_at = datetime.now()
        stats.messages_received = 100
        stats.messages_sent = 50

        d = stats.to_dict()
        self.assertIn("messages_received", d)
        self.assertEqual(d["messages_received"], 100)


class TestTickData(unittest.TestCase):
    """Tests for tick data."""

    def test_tick_creation(self):
        """Test tick data creation."""
        tick = TickData(
            ticker="AMD",
            price=150.5,
            volume=1000000,
            timestamp=datetime.now(),
            source="test"
        )
        self.assertEqual(tick.ticker, "AMD")
        self.assertEqual(tick.price, 150.5)
        self.assertEqual(tick.volume, 1000000)

    def test_tick_with_bid_ask(self):
        """Test tick data with bid/ask."""
        tick = TickData(
            ticker="AMD",
            price=150.5,
            volume=1000000,
            timestamp=datetime.now(),
            bid=150.4,
            ask=150.6,
            source="test"
        )
        self.assertEqual(tick.bid, 150.4)
        self.assertEqual(tick.ask, 150.6)

    def test_tick_to_dict(self):
        """Test tick serialization."""
        tick = TickData(
            ticker="AMD",
            price=150.5,
            volume=1000000,
            timestamp=datetime.now(),
            source="test"
        )
        d = tick.to_dict()
        self.assertEqual(d["ticker"], "AMD")
        self.assertEqual(d["price"], 150.5)


class TestRateLimiter(unittest.TestCase):
    """Tests for rate limiter."""

    def test_initial_tokens(self):
        """Test initial token count."""
        limiter = RateLimiter(max_per_second=10)
        self.assertEqual(limiter.max_per_second, 10)

    def test_acquire_token(self):
        """Test acquiring a token."""
        limiter = RateLimiter(max_per_second=10)
        # Should be able to acquire immediately
        result = limiter.acquire()
        self.assertTrue(result)

    def test_rate_limiting(self):
        """Test rate limiting kicks in."""
        limiter = RateLimiter(max_per_second=2)

        # Acquire all tokens
        limiter.acquire()
        limiter.acquire()

        # Should be rate limited
        result = limiter.acquire()
        self.assertFalse(result)

    def test_token_refill(self):
        """Test tokens refill over time."""
        limiter = RateLimiter(max_per_second=10)

        # Exhaust tokens
        for _ in range(10):
            limiter.acquire()

        # Should be rate limited
        self.assertFalse(limiter.acquire())

        # Wait for refill
        time.sleep(0.15)  # 1.5 tokens should have refilled

        # Should be able to acquire
        result = limiter.acquire()
        self.assertTrue(result)

    def test_wait_time(self):
        """Test wait time calculation."""
        limiter = RateLimiter(max_per_second=10)

        # Exhaust tokens
        for _ in range(10):
            limiter.acquire()

        wait = limiter.wait_time()
        self.assertGreater(wait, 0)


class TestSimulatedStreamer(unittest.TestCase):
    """Tests for simulated streamer."""

    def setUp(self):
        self.streamer = SimulatedStreamer(tick_interval=0.1)
        self.received_ticks = []
        self.streamer.add_tick_callback(lambda t: self.received_ticks.append(t))

    def tearDown(self):
        self.streamer.disconnect()

    def test_subscribe(self):
        """Test subscription."""
        self.streamer.subscribe(["AMD", "AAPL"])
        self.assertEqual(len(self.streamer._tickers), 2)

    def test_unsubscribe(self):
        """Test unsubscription."""
        self.streamer.subscribe(["AMD", "AAPL", "GOOG"])
        self.streamer.unsubscribe(["AAPL"])
        self.assertEqual(len(self.streamer._tickers), 2)
        self.assertIn("AMD", self.streamer._tickers)
        self.assertIn("GOOG", self.streamer._tickers)
        self.assertNotIn("AAPL", self.streamer._tickers)

    def test_connect_disconnect(self):
        """Test connection lifecycle."""
        self.streamer.connect()
        self.assertTrue(self.streamer.is_connected())

        self.streamer.disconnect()
        self.assertFalse(self.streamer.is_connected())

    def test_receives_ticks(self):
        """Test receiving simulated ticks."""
        self.streamer.subscribe(["AMD"])
        self.streamer.connect()

        # Wait for ticks
        time.sleep(0.35)

        self.assertGreater(len(self.received_ticks), 0)
        self.assertEqual(self.received_ticks[0].ticker, "AMD")

    def test_tick_data_format(self):
        """Test tick data has expected fields."""
        self.streamer.subscribe(["AMD"])
        self.streamer.connect()

        # Wait for ticks
        time.sleep(0.35)

        self.assertGreater(len(self.received_ticks), 0)
        tick = self.received_ticks[0]
        self.assertIsNotNone(tick.price)
        self.assertIsNotNone(tick.volume)
        self.assertIsNotNone(tick.timestamp)
        self.assertEqual(tick.source, "simulated")


class TestCreateStreamer(unittest.TestCase):
    """Tests for streamer factory function."""

    def test_create_simulated_streamer(self):
        """Test creating simulated streamer."""
        streamer = create_streamer(simulated=True)
        self.assertIsInstance(streamer, SimulatedStreamer)

    def test_create_real_streamer(self):
        """Test creating real streamer."""
        streamer = create_streamer(simulated=False)
        self.assertIsInstance(streamer, DataStreamer)

    def test_create_with_config(self):
        """Test creating streamer with config."""
        config = StreamConfig(source="alpaca")
        streamer = create_streamer(config=config, simulated=False)
        self.assertIsInstance(streamer, DataStreamer)
        self.assertEqual(streamer.config.source, "alpaca")


class TestDataStreamerBasics(unittest.TestCase):
    """Tests for DataStreamer basic functionality."""

    def test_initial_state(self):
        """Test initial connection state."""
        streamer = DataStreamer()
        self.assertEqual(streamer.get_state(), ConnectionState.DISCONNECTED)
        self.assertFalse(streamer.is_connected())

    def test_add_callback(self):
        """Test adding callbacks."""
        streamer = DataStreamer()
        callback_calls = []

        def callback(tick):
            callback_calls.append(tick)

        streamer.add_tick_callback(callback)
        streamer.add_status_callback(lambda state: None)

        # Callbacks are registered (can't easily test invocation without connection)
        self.assertEqual(len(streamer._tick_callbacks), 1)

    def test_get_stats(self):
        """Test getting statistics."""
        streamer = DataStreamer()
        stats = streamer.get_stats()
        self.assertIn("messages_received", stats)
        self.assertIn("connected_at", stats)

    def test_subscribe_before_connect(self):
        """Test subscribing before connecting."""
        streamer = DataStreamer()
        streamer.subscribe(["AMD", "AAPL"], ["1m"])

        # Subscription stored but not sent
        self.assertIn("AMD", streamer._subscriptions)


if __name__ == "__main__":
    unittest.main()