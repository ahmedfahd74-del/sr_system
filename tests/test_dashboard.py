# tests/test_dashboard.py
"""Tests for the dashboard module."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import time
import threading
import os

# Mock matplotlib for headless testing
os.environ['DISPLAY'] = ':99'
import matplotlib
matplotlib.use('Agg')

from notebooks.dashboard import (
    PriceChart,
    AlertPanel,
    Dashboard
)


class TestPriceChart(unittest.TestCase):
    """Tests for PriceChart class."""

    def test_init(self):
        """Test PriceChart initialization."""
        chart = PriceChart("AMD", "1D", lookback_bars=50)
        self.assertEqual(chart.ticker, "AMD")
        self.assertEqual(chart.timeframe, "1D")
        self.assertEqual(chart.lookback_bars, 50)

    def test_add_bar(self):
        """Test adding bars to the chart."""
        chart = PriceChart("AMD", "1D")
        ts = datetime.now()
        chart.add_bar(ts, 100.0, 101.0, 99.0, 100.5, 1000000)

        self.assertEqual(len(chart.closes), 1)
        self.assertEqual(chart.opens[0], 100.0)
        self.assertEqual(chart.highs[0], 101.0)
        self.assertEqual(chart.lows[0], 99.0)
        self.assertEqual(chart.closes[0], 100.5)

    def test_lookback_limit(self):
        """Test that lookback limit is enforced."""
        chart = PriceChart("AMD", "1D", lookback_bars=3)
        ts = datetime.now()

        for i in range(5):
            chart.add_bar(ts + timedelta(minutes=i), 100 + i, 101 + i, 99 + i, 100.5 + i, 1000000)

        self.assertEqual(len(chart.closes), 3)
        self.assertAlmostEqual(chart.closes[-1], 100.5 + 4)

    def test_update_levels(self):
        """Test updating S/R levels."""
        chart = PriceChart("AMD", "1D")
        support = [(95.0, 75), (92.0, 60)]
        resistance = [(105.0, 80), (110.0, 65)]

        chart.update_levels(support, resistance)

        self.assertEqual(chart.support_levels, [95.0, 92.0])
        self.assertEqual(chart.support_confidences, [75, 60])
        self.assertEqual(chart.resistance_levels, [105.0, 110.0])
        self.assertEqual(chart.resistance_confidences, [80, 65])

    def test_update_regime(self):
        """Test updating regime info."""
        chart = PriceChart("AMD", "1D")
        chart.update_regime("trending", "breakout", "bullish")

        self.assertEqual(chart.regime, "trending")
        self.assertEqual(chart.current_pattern, "breakout")
        self.assertEqual(chart.signal, "bullish")


class TestAlertPanel(unittest.TestCase):
    """Tests for AlertPanel class."""

    def test_init(self):
        """Test AlertPanel initialization."""
        panel = AlertPanel(max_alerts=10)
        self.assertEqual(panel.max_alerts, 10)
        self.assertEqual(len(panel.alerts), 0)

    def test_add_alert(self):
        """Test adding alerts."""
        panel = AlertPanel(max_alerts=5)
        panel.add_alert({
            'alert_type': 'APPROACH_SUPPORT',
            'message': 'AMD approaching support at $95',
            'severity': 'high'
        })

        self.assertEqual(len(panel.alerts), 1)
        self.assertEqual(panel.alerts[0]['alert_type'], 'APPROACH_SUPPORT')

    def test_max_alerts_limit(self):
        """Test that max alerts limit is enforced."""
        panel = AlertPanel(max_alerts=3)

        for i in range(5):
            panel.add_alert({
                'alert_type': f'test_{i}',
                'message': f'Alert {i}',
                'severity': 'low'
            })

        self.assertEqual(len(panel.alerts), 3)

    def test_get_recent(self):
        """Test getting recent alerts."""
        panel = AlertPanel(max_alerts=10)

        for i in range(5):
            panel.add_alert({
                'alert_type': f'test_{i}',
                'message': f'Alert {i}',
                'severity': 'low'
            })

        recent = panel.get_recent(3)
        self.assertEqual(len(recent), 3)


class TestDashboard(unittest.TestCase):
    """Tests for Dashboard class."""

    def test_init(self):
        """Test Dashboard initialization."""
        dashboard = Dashboard(["AMD", "AAPL"], "1D", refresh_rate=0.5)

        self.assertEqual(dashboard.tickers, ["AMD", "AAPL"])
        self.assertEqual(dashboard.timeframe, "1D")
        self.assertEqual(dashboard.refresh_rate, 0.5)
        self.assertIn("AMD", dashboard.charts)
        self.assertIn("AAPL", dashboard.charts)

    def test_update_price(self):
        """Test updating price data."""
        dashboard = Dashboard(["AMD"], "1D")
        ts = datetime.now()

        dashboard.update_price("AMD", ts, 100.0, 101.0, 99.0, 100.5, 1000000)

        chart = dashboard.charts["AMD"]
        self.assertEqual(len(chart.closes), 1)

    def test_update_levels(self):
        """Test updating S/R levels."""
        dashboard = Dashboard(["AMD"], "1D")
        support = [(95.0, 75)]
        resistance = [(105.0, 80)]

        dashboard.update_levels("AMD", support, resistance)

        chart = dashboard.charts["AMD"]
        self.assertEqual(chart.support_levels, [95.0])
        self.assertEqual(chart.resistance_levels, [105.0])

    def test_update_regime(self):
        """Test updating regime info."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.update_regime("AMD", "trending", "breakout", "bullish")

        chart = dashboard.charts["AMD"]
        self.assertEqual(chart.regime, "trending")
        self.assertEqual(chart.signal, "bullish")

    def test_add_alert(self):
        """Test adding alerts to dashboard."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.add_alert({
            'alert_type': 'APPROACH_SUPPORT',
            'message': 'Test alert',
            'severity': 'high'
        })

        self.assertEqual(len(dashboard.alert_panel.alerts), 1)

    def test_add_update_callback(self):
        """Test adding update callbacks."""
        dashboard = Dashboard(["AMD"], "1D")
        callback_called = [False]

        def callback(d):
            callback_called[0] = True

        dashboard.add_update_callback(callback)
        dashboard.render()

        self.assertTrue(callback_called[0])

    @patch('matplotlib.pyplot.show')
    def test_setup_plot(self, mock_show):
        """Test plot setup."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.setup_plot()

        self.assertIsNotNone(dashboard._fig)
        self.assertIsNotNone(dashboard._axes)

    @patch('matplotlib.pyplot.show')
    def test_render_without_setup(self, mock_show):
        """Test that render sets up plot if not done."""
        dashboard = Dashboard(["AMD"], "1D")

        # Add some data
        ts = datetime.now()
        dashboard.update_price("AMD", ts, 100.0, 101.0, 99.0, 100.5, 1000000)

        # Render should auto-setup
        dashboard.render()

        self.assertIsNotNone(dashboard._fig)

    @patch('matplotlib.pyplot.show')
    def test_render_chart(self, mock_show):
        """Test rendering the chart."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.setup_plot()

        # Add some price data
        ts = datetime.now()
        for i in range(10):
            dashboard.update_price("AMD", ts + timedelta(minutes=i), 100 + i, 101 + i, 99 + i, 100.5 + i, 1000000)

        # Add levels
        dashboard.update_levels("AMD", [(95.0, 75)], [(105.0, 80)])

        # Render should not raise
        dashboard.render()

    @patch('matplotlib.pyplot.show')
    def test_render_alerts(self, mock_show):
        """Test rendering alerts panel."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.setup_plot()

        # Add some alerts
        for i in range(5):
            dashboard.add_alert({
                'alert_type': f'test_{i}',
                'message': f'Alert message {i}',
                'severity': 'high' if i < 2 else 'low'
            })

        dashboard.render()

    def test_start_stop(self):
        """Test starting and stopping the dashboard."""
        dashboard = Dashboard(["AMD"], "1D", refresh_rate=0.1)

        dashboard.start()
        self.assertTrue(dashboard._running)

        # Let it run briefly
        time.sleep(0.3)

        dashboard.stop()
        self.assertFalse(dashboard._running)

    @patch('matplotlib.figure.Figure.savefig')
    def test_save(self, mock_save):
        """Test saving dashboard to file."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.setup_plot()

        dashboard.save("/tmp/test_dashboard.png")

        mock_save.assert_called_once()

    @patch('matplotlib.pyplot.show')
    def test_show_non_blocking(self, mock_show):
        """Test showing dashboard non-blocking."""
        dashboard = Dashboard(["AMD"], "1D")
        dashboard.show(block=False)

        self.assertTrue(dashboard._running)

        dashboard.stop()


class TestDashboardIntegration(unittest.TestCase):
    """Integration tests for Dashboard with other components."""

    @patch('matplotlib.pyplot.show')
    def test_with_price_chart_data(self, mock_show):
        """Test dashboard with realistic price data."""
        dashboard = Dashboard(["AMD"], "1H")

        # Simulate intraday data
        base_price = 100.0
        ts = datetime.now()

        for i in range(100):
            change = -0.5 + (i % 10) * 0.1
            base_price += change

            open_p = base_price + 0.2
            close_p = base_price
            high_p = max(open_p, close_p) + 0.5
            low_p = min(open_p, close_p) - 0.5

            dashboard.update_price("AMD", ts + timedelta(minutes=i), open_p, high_p, low_p, close_p, 1000000)

        # Add S/R levels
        support = [(base_price - 5, 70), (base_price - 10, 55)]
        resistance = [(base_price + 5, 75), (base_price + 10, 60)]
        dashboard.update_levels("AMD", support, resistance)

        # Set regime
        dashboard.update_regime("AMD", "trending", "ascending_triangle", "bullish")

        # Render should handle all this data
        dashboard.setup_plot()
        dashboard.render()

        chart = dashboard.charts["AMD"]
        self.assertEqual(len(chart.closes), 100)
        self.assertEqual(len(chart.support_levels), 2)
        self.assertEqual(chart.signal, "bullish")

    @patch('matplotlib.pyplot.show')
    def test_alert_flow(self, mock_show):
        """Test full alert flow."""
        dashboard = Dashboard(["AMD"], "1D")

        # Add prices
        ts = datetime.now()
        for i in range(10):
            dashboard.update_price("AMD", ts + timedelta(hours=i), 100, 101, 99, 100, 1000000)

        # Add multiple alerts
        alerts = [
            {'alert_type': 'APPROACH_SUPPORT', 'message': 'AMD approaching $95 support', 'severity': 'high'},
            {'alert_type': 'BOUNCE_SUPPORT', 'message': 'AMD bounced from $95', 'severity': 'medium'},
            {'alert_type': 'BREAKOUT_ABOVE', 'message': 'AMD broke above $105', 'severity': 'high'},
        ]

        for alert in alerts:
            dashboard.add_alert(alert)

        self.assertEqual(len(dashboard.alert_panel.alerts), 3)

        # Get recent
        recent = dashboard.alert_panel.get_recent(2)
        self.assertEqual(len(recent), 2)


if __name__ == "__main__":
    unittest.main()