# tests/test_alerts.py
"""Unit tests for alert system (Phase 4)."""

import unittest
from datetime import datetime
from signals.alerts import (
    Alert, AlertType, AlertSeverity, AlertConfig,
    AlertHistory, AlertNotifier, SRAlertDetector,
    load_alerts_from_log, get_alert_summary
)


class TestAlertTypes(unittest.TestCase):
    """Tests for Alert enums and dataclass."""

    def test_alert_type_values(self):
        """Test alert type enum values."""
        self.assertEqual(AlertType.APPROACH_SUPPORT.value, "approach_support")
        self.assertEqual(AlertType.BREAKOUT_ABOVE.value, "breakout_above")
        self.assertEqual(AlertType.FALSE_BREAKOUT_BELOW.value, "false_breakout_below")

    def test_alert_severity_values(self):
        """Test alert severity enum values."""
        self.assertEqual(AlertSeverity.LOW.value, "low")
        self.assertEqual(AlertSeverity.CRITICAL.value, "critical")

    def test_alert_creation(self):
        """Test alert dataclass creation."""
        alert = Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AMD",
            level_price=100.0,
            current_price=100.5,
            distance_pct=0.5,
            severity=AlertSeverity.MEDIUM,
            timestamp=datetime.now(),
            message="AMD approaching support at $100.00"
        )
        self.assertEqual(alert.ticker, "AMD")
        self.assertEqual(alert.level_price, 100.0)

    def test_alert_to_dict(self):
        """Test alert serialization."""
        alert = Alert(
            alert_type=AlertType.BREAKOUT_ABOVE,
            ticker="AMD",
            level_price=105.0,
            current_price=106.0,
            distance_pct=0.95,
            severity=AlertSeverity.HIGH,
            timestamp=datetime.now(),
            message="AMD broke above resistance"
        )
        d = alert.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["alert_type"], "breakout_above")
        self.assertEqual(d["ticker"], "AMD")


class TestAlertConfig(unittest.TestCase):
    """Tests for alert configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AlertConfig()
        self.assertEqual(config.approach_threshold_pct, 0.5)
        self.assertEqual(config.breakout_atr_mult, 1.5)
        self.assertEqual(config.cooldown_seconds, 300)
        self.assertEqual(config.max_history, 100)

    def test_custom_config(self):
        """Test custom configuration."""
        config = AlertConfig(
            approach_threshold_pct=1.0,
            breakout_atr_mult=2.0,
            cooldown_seconds=600
        )
        self.assertEqual(config.approach_threshold_pct, 1.0)
        self.assertEqual(config.breakout_atr_mult, 2.0)
        self.assertEqual(config.cooldown_seconds, 600)


class TestAlertHistory(unittest.TestCase):
    """Tests for alert history tracking."""

    def setUp(self):
        self.history = AlertHistory(max_size=10)

    def test_add_alert(self):
        """Test adding alerts to history."""
        alert = Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AMD",
            level_price=100.0,
            current_price=100.5,
            distance_pct=0.5,
            severity=AlertSeverity.MEDIUM,
            timestamp=datetime.now(),
            message="Test alert"
        )
        self.history.add(alert)
        self.assertEqual(len(self.history.alerts), 1)

    def test_get_recent(self):
        """Test getting recent alerts."""
        for i in range(5):
            alert = Alert(
                alert_type=AlertType.APPROACH_SUPPORT,
                ticker="AMD",
                level_price=100.0,
                current_price=100.0 + i * 0.1,
                distance_pct=0.5,
                severity=AlertSeverity.LOW,
                timestamp=datetime.now(),
                message=f"Alert {i}"
            )
            self.history.add(alert)
        recent = self.history.get_recent(3)
        self.assertEqual(len(recent), 3)

    def test_get_by_type(self):
        """Test filtering alerts by type."""
        self.history.add(Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AMD", level_price=100.0, current_price=100.5,
            distance_pct=0.5, severity=AlertSeverity.LOW,
            timestamp=datetime.now(), message="Support approach"
        ))
        self.history.add(Alert(
            alert_type=AlertType.APPROACH_RESISTANCE,
            ticker="AMD", level_price=105.0, current_price=104.5,
            distance_pct=0.5, severity=AlertSeverity.LOW,
            timestamp=datetime.now(), message="Resistance approach"
        ))
        support_alerts = self.history.get_by_type(AlertType.APPROACH_SUPPORT)
        self.assertEqual(len(support_alerts), 1)

    def test_get_by_ticker(self):
        """Test filtering alerts by ticker."""
        self.history.add(Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AMD", level_price=100.0, current_price=100.5,
            distance_pct=0.5, severity=AlertSeverity.LOW,
            timestamp=datetime.now(), message="AMD alert"
        ))
        self.history.add(Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AAPL", level_price=150.0, current_price=150.5,
            distance_pct=0.33, severity=AlertSeverity.LOW,
            timestamp=datetime.now(), message="AAPL alert"
        ))
        amd_alerts = self.history.get_by_ticker("AMD")
        self.assertEqual(len(amd_alerts), 1)

    def test_is_in_cooldown(self):
        """Test cooldown detection."""
        alert = Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AMD", level_price=100.0, current_price=100.5,
            distance_pct=0.5, severity=AlertSeverity.LOW,
            timestamp=datetime.now(), message="Test"
        )
        self.history.add(alert)
        # Should be in cooldown immediately after
        self.assertTrue(self.history.is_in_cooldown(AlertType.APPROACH_SUPPORT, 300))

    def test_get_stats(self):
        """Test alert statistics."""
        self.history.add(Alert(
            alert_type=AlertType.APPROACH_SUPPORT,
            ticker="AMD", level_price=100.0, current_price=100.5,
            distance_pct=0.5, severity=AlertSeverity.LOW,
            timestamp=datetime.now(), message="Test"
        ))
        stats = self.history.get_stats()
        self.assertEqual(stats["total_alerts"], 1)
        self.assertIn("AMD", stats["by_ticker"])


class TestSRAlertDetector(unittest.TestCase):
    """Tests for S/R alert detection."""

    def setUp(self):
        self.detector = SRAlertDetector()

    def test_approach_support_alert(self):
        """Test detection of support approach alert."""
        alerts = self.detector.check_alerts(
            ticker="AMD",
            current_price=100.5,
            support_levels=[100.0],
            resistance_levels=[],
            atr=2.0
        )
        # Should trigger approach alert
        approach_alerts = [a for a in alerts if a.alert_type == AlertType.APPROACH_SUPPORT]
        self.assertEqual(len(approach_alerts), 1)
        self.assertEqual(approach_alerts[0].level_price, 100.0)

    def test_approach_resistance_alert(self):
        """Test detection of resistance approach alert."""
        # Price above resistance but within threshold (approach from above)
        alerts = self.detector.check_alerts(
            ticker="AMD",
            current_price=105.4,  # 0.38% above resistance at 105.0
            support_levels=[],
            resistance_levels=[105.0],
            atr=2.0
        )
        # Should trigger approach alert - price above but close
        approach_alerts = [a for a in alerts if a.alert_type == AlertType.APPROACH_RESISTANCE]
        self.assertEqual(len(approach_alerts), 1)
        self.assertEqual(approach_alerts[0].level_price, 105.0)

    def test_breakout_above_alert(self):
        """Test detection of breakout above resistance."""
        # Price must be above resistance by more than ATR threshold
        # distance = current_price - level_price > atr_distance_threshold
        alerts = self.detector.check_alerts(
            ticker="AMD",
            current_price=110.0,  # 5.0 above resistance at 105.0, ATR=2.0, 1.5*ATR=3.0
            support_levels=[],
            resistance_levels=[105.0],
            atr=2.0
        )
        breakout_alerts = [a for a in alerts if a.alert_type == AlertType.BREAKOUT_ABOVE]
        self.assertEqual(len(breakout_alerts), 1)

    def test_breakout_below_alert(self):
        """Test detection of breakout below support."""
        # distance = current_price - level_price < -atr_distance_threshold
        alerts = self.detector.check_alerts(
            ticker="AMD",
            current_price=95.0,  # 5.0 below support at 100.0, ATR=2.0, 1.5*ATR=3.0
            support_levels=[100.0],
            resistance_levels=[],
            atr=2.0
        )
        breakout_alerts = [a for a in alerts if a.alert_type == AlertType.BREAKOUT_BELOW]
        self.assertEqual(len(breakout_alerts), 1)

    def test_no_alert_when_far_from_level(self):
        """Test that no alert is triggered when far from levels."""
        alerts = self.detector.check_alerts(
            ticker="AMD",
            current_price=110.0,  # Far from support at 100
            support_levels=[100.0],
            resistance_levels=[150.0],  # Far from resistance
            atr=2.0
        )
        # No approach alerts since we're far from both levels
        self.assertEqual(len(alerts), 0)

    def test_severity_calculation(self):
        """Test alert severity calculation."""
        # Very close (< 0.2%)
        alert_close = self.detector._check_level("AMD", 100.1, 100.0, 1.0, "support")
        self.assertEqual(alert_close.severity, AlertSeverity.HIGH)

        # Medium distance (0.2-0.5%)
        alert_med = self.detector._check_level("AMD", 100.4, 100.0, 1.0, "support")
        self.assertEqual(alert_med.severity, AlertSeverity.MEDIUM)

    def test_get_history(self):
        """Test getting alert history."""
        self.detector.check_alerts(
            ticker="AMD",
            current_price=100.5,
            support_levels=[100.0],
            resistance_levels=[],
            atr=2.0
        )
        history = self.detector.get_history(5)
        self.assertGreater(len(history), 0)

    def test_get_stats(self):
        """Test getting alert statistics."""
        self.detector.check_alerts(
            ticker="AMD",
            current_price=100.5,
            support_levels=[100.0],
            resistance_levels=[],
            atr=2.0
        )
        stats = self.detector.get_stats()
        self.assertIn("total_alerts", stats)

    def test_callback_on_alert(self):
        """Test that callbacks are called on alert."""
        callback_called = []
        def callback(alert):
            callback_called.append(alert)

        self.detector.add_notification_callback(callback)
        self.detector.check_alerts(
            ticker="AMD",
            current_price=100.5,
            support_levels=[100.0],
            resistance_levels=[],
            atr=2.0
        )
        self.assertEqual(len(callback_called), 1)


class TestAlertSummary(unittest.TestCase):
    """Tests for alert summary utility."""

    def test_empty_alerts_summary(self):
        """Test summary with no alerts."""
        summary = get_alert_summary([])
        self.assertEqual(summary, "No recent alerts")

    def test_alerts_summary(self):
        """Test summary with alerts."""
        alerts = [
            Alert(
                alert_type=AlertType.APPROACH_SUPPORT,
                ticker="AMD", level_price=100.0, current_price=100.5,
                distance_pct=0.5, severity=AlertSeverity.LOW,
                timestamp=datetime(2024, 1, 1, 10, 30, 0),
                message="AMD approaching support"
            )
        ]
        summary = get_alert_summary(alerts)
        self.assertIn("AMD approaching support", summary)


if __name__ == "__main__":
    unittest.main()