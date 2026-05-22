# sr_system/signals/alerts.py
"""Alert system for S/R level notifications."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional
from collections import deque
import json
import os


class AlertType(Enum):
    """Types of S/R alerts."""
    APPROACH_SUPPORT = "approach_support"      # Price approaching support
    APPROACH_RESISTANCE = "approach_resistance"  # Price approaching resistance
    BOUNCE_SUPPORT = "bounce_support"          # Price bounced from support
    BOUNCE_RESISTANCE = "bounce_resistance"    # Price rejected at resistance
    BREAKOUT_ABOVE = "breakout_above"          # Price broke above resistance
    BREAKOUT_BELOW = "breakout_below"          # Price broke below support
    FALSE_BREAKOUT_ABOVE = "false_breakout_above"  # Failed breakout up
    FALSE_BREAKOUT_BELOW = "false_breakout_below"  # Failed breakout down


class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Alert:
    """An S/R level alert."""
    alert_type: AlertType
    ticker: str
    level_price: float
    current_price: float
    distance_pct: float
    severity: AlertSeverity
    timestamp: datetime
    message: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert alert to dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "ticker": self.ticker,
            "level_price": self.level_price,
            "current_price": self.current_price,
            "distance_pct": self.distance_pct,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "metadata": self.metadata
        }


@dataclass
class AlertConfig:
    """Configuration for alert detection."""
    # Distance threshold (% of price) to trigger approach alert
    approach_threshold_pct: float = 0.5
    # ATR multiplier for breakout detection
    breakout_atr_mult: float = 1.5
    # Cooldown period in seconds between same-type alerts
    cooldown_seconds: float = 300
    # Maximum alerts to keep in history
    max_history: int = 100
    # Enable webhook notifications
    webhook_enabled: bool = False
    webhook_url: str = ""
    # Enable file logging
    file_log_enabled: bool = True
    log_file_path: str = "alerts.log"


class AlertHistory:
    """Track alert history and statistics."""

    def __init__(self, max_size: int = 100):
        self.alerts: deque = deque(maxlen=max_size)
        self.alert_counts: Dict[AlertType, int] = {at: 0 for at in AlertType}
        self.last_alert_time: Dict[AlertType, datetime] = {}

    def add(self, alert: Alert):
        """Add an alert to history."""
        self.alerts.append(alert)
        self.alert_counts[alert.alert_type] += 1
        self.last_alert_time[alert.alert_type] = alert.timestamp

    def get_recent(self, count: int = 10) -> List[Alert]:
        """Get recent alerts."""
        return list(self.alerts)[-count:]

    def get_by_type(self, alert_type: AlertType) -> List[Alert]:
        """Get alerts by type."""
        return [a for a in self.alerts if a.alert_type == alert_type]

    def get_by_ticker(self, ticker: str) -> List[Alert]:
        """Get alerts for a specific ticker."""
        return [a for a in self.alerts if a.ticker == ticker]

    def is_in_cooldown(self, alert_type: AlertType, cooldown_seconds: float) -> bool:
        """Check if alert type is in cooldown period."""
        if alert_type not in self.last_alert_time:
            return False
        elapsed = (datetime.now() - self.last_alert_time[alert_type]).total_seconds()
        return elapsed < cooldown_seconds

    def get_stats(self) -> dict:
        """Get alert statistics."""
        return {
            "total_alerts": len(self.alerts),
            "by_type": {at.value: self.alert_counts[at] for at in AlertType},
            "by_ticker": self._count_by_ticker()
        }

    def _count_by_ticker(self) -> Dict[str, int]:
        """Count alerts by ticker."""
        counts: Dict[str, int] = {}
        for alert in self.alerts:
            counts[alert.ticker] = counts.get(alert.ticker, 0) + 1
        return counts


class AlertNotifier:
    """Handles alert notifications via various channels."""

    def __init__(self, config: AlertConfig):
        self.config = config
        self.callbacks: List[Callable[[Alert], None]] = []

    def add_callback(self, callback: Callable[[Alert], None]):
        """Add a callback function for notifications."""
        self.callbacks.append(callback)

    def notify(self, alert: Alert):
        """Send alert notification through all channels."""
        # Console output
        self._notify_console(alert)

        # File log
        if self.config.file_log_enabled:
            self._notify_file(alert)

        # Webhook
        if self.config.webhook_enabled and self.config.webhook_url:
            self._notify_webhook(alert)

        # Callbacks
        for callback in self.callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"Callback error: {e}")

    def _notify_console(self, alert: Alert):
        """Print alert to console."""
        severity_icon = {
            AlertSeverity.LOW: "🔵",
            AlertSeverity.MEDIUM: "🟡",
            AlertSeverity.HIGH: "🟠",
            AlertSeverity.CRITICAL: "🔴"
        }.get(alert.severity, "⚪")

        print(f"{severity_icon} [{alert.severity.value.upper()}] {alert.message}")

    def _notify_file(self, alert: Alert):
        """Write alert to log file."""
        try:
            with open(self.config.log_file_path, "a") as f:
                f.write(json.dumps(alert.to_dict()) + "\n")
        except Exception as e:
            print(f"Failed to write alert to file: {e}")

    def _notify_webhook(self, alert: Alert):
        """Send alert to webhook URL."""
        try:
            import requests
            response = requests.post(
                self.config.webhook_url,
                json=alert.to_dict(),
                timeout=5
            )
            if response.status_code != 200:
                print(f"Webhook failed: {response.status_code}")
        except ImportError:
            print("requests library not installed, webhook disabled")
        except Exception as e:
            print(f"Webhook error: {e}")


class SRAlertDetector:
    """Detects S/R level alerts."""

    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig()
        self.history = AlertHistory(self.config.max_history)
        self.notifier = AlertNotifier(self.config)

    def add_notification_callback(self, callback: Callable[[Alert], None]):
        """Add callback for alert notifications."""
        self.notifier.add_callback(callback)

    def check_alerts(
        self,
        ticker: str,
        current_price: float,
        support_levels: List[float],
        resistance_levels: List[float],
        atr: float
    ) -> List[Alert]:
        """
        Check for S/R level alerts.

        Args:
            ticker: Stock ticker symbol
            current_price: Current market price
            support_levels: List of support level prices
            resistance_levels: List of resistance level prices
            atr: Current ATR value

        Returns:
            List of triggered alerts
        """
        alerts = []

        # Check support levels
        for level in support_levels:
            alert = self._check_level(
                ticker, current_price, level, atr, "support"
            )
            if alert:
                # Check cooldown
                if not self.history.is_in_cooldown(alert.alert_type, self.config.cooldown_seconds):
                    alerts.append(alert)
                    self.history.add(alert)
                    self.notifier.notify(alert)

        # Check resistance levels
        for level in resistance_levels:
            alert = self._check_level(
                ticker, current_price, level, atr, "resistance"
            )
            if alert:
                # Check cooldown
                if not self.history.is_in_cooldown(alert.alert_type, self.config.cooldown_seconds):
                    alerts.append(alert)
                    self.history.add(alert)
                    self.notifier.notify(alert)

        return alerts

    def _check_level(
        self,
        ticker: str,
        current_price: float,
        level_price: float,
        atr: float,
        level_type: str
    ) -> Optional[Alert]:
        """Check a single S/R level for alerts."""
        distance = current_price - level_price
        distance_pct = abs(distance / current_price) * 100

        # Calculate distance threshold in ATR terms
        atr_distance_threshold = atr * self.config.breakout_atr_mult

        if level_type == "support":
            # Check approach
            if 0 < distance < current_price * (self.config.approach_threshold_pct / 100):
                severity = self._calculate_severity(distance_pct, current_price, level_price)
                return Alert(
                    alert_type=AlertType.APPROACH_SUPPORT,
                    ticker=ticker,
                    level_price=level_price,
                    current_price=current_price,
                    distance_pct=distance_pct,
                    severity=severity,
                    timestamp=datetime.now(),
                    message=f"{ticker} approaching support at ${level_price:.2f} ({distance_pct:.2f}% away)",
                    metadata={"atr": atr, "level_type": "support"}
                )

            # Check breakout below
            if distance < -atr_distance_threshold:
                return Alert(
                    alert_type=AlertType.BREAKOUT_BELOW,
                    ticker=ticker,
                    level_price=level_price,
                    current_price=current_price,
                    distance_pct=distance_pct,
                    severity=AlertSeverity.HIGH,
                    timestamp=datetime.now(),
                    message=f"{ticker} broke below support at ${level_price:.2f}",
                    metadata={"atr": atr, "level_type": "support", "breakout_size": abs(distance)}
                )

            # Check bounce (price moved below then recovered)
            # This would require tracking previous state - simplified here

        else:  # resistance
            # Check approach
            if distance > 0 and distance < current_price * (self.config.approach_threshold_pct / 100):
                severity = self._calculate_severity(distance_pct, current_price, level_price)
                return Alert(
                    alert_type=AlertType.APPROACH_RESISTANCE,
                    ticker=ticker,
                    level_price=level_price,
                    current_price=current_price,
                    distance_pct=distance_pct,
                    severity=severity,
                    timestamp=datetime.now(),
                    message=f"{ticker} approaching resistance at ${level_price:.2f} ({distance_pct:.2f}% away)",
                    metadata={"atr": atr, "level_type": "resistance"}
                )

            # Check breakout above
            if distance > atr_distance_threshold:
                return Alert(
                    alert_type=AlertType.BREAKOUT_ABOVE,
                    ticker=ticker,
                    level_price=level_price,
                    current_price=current_price,
                    distance_pct=distance_pct,
                    severity=AlertSeverity.HIGH,
                    timestamp=datetime.now(),
                    message=f"{ticker} broke above resistance at ${level_price:.2f}",
                    metadata={"atr": atr, "level_type": "resistance", "breakout_size": distance}
                )

        return None

    def _calculate_severity(
        self,
        distance_pct: float,
        current_price: float,
        level_price: float
    ) -> AlertSeverity:
        """Calculate alert severity based on distance."""
        if distance_pct < 0.2:
            return AlertSeverity.HIGH
        elif distance_pct < 0.5:
            return AlertSeverity.MEDIUM
        elif distance_pct < 1.0:
            return AlertSeverity.LOW
        else:
            return AlertSeverity.LOW

    def get_active_alerts(self) -> List[Alert]:
        """Get recent alerts within cooldown window."""
        now = datetime.now()
        active = []
        for alert in self.history.alerts:
            elapsed = (now - alert.timestamp).total_seconds()
            if elapsed < self.config.cooldown_seconds:
                active.append(alert)
        return active

    def get_history(self, count: int = 20) -> List[Alert]:
        """Get alert history."""
        return self.history.get_recent(count)

    def get_stats(self) -> dict:
        """Get alert statistics."""
        return self.history.get_stats()


def load_alerts_from_log(log_path: str) -> List[Alert]:
    """Load alerts from a log file."""
    alerts = []
    try:
        with open(log_path, "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
                    data["alert_type"] = AlertType(data["alert_type"])
                    data["severity"] = AlertSeverity(data["severity"])
                    alerts.append(Alert(**data))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return alerts


def get_alert_summary(alerts: List[Alert]) -> str:
    """Get a formatted summary of alerts."""
    if not alerts:
        return "No recent alerts"

    summary = "Recent Alerts:\n"
    for alert in alerts[-5:]:
        summary += f"  [{alert.timestamp.strftime('%H:%M:%S')}] {alert.message}\n"

    return summary