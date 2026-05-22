# core/config_manager.py
"""Hot-reloadable configuration manager for S/R system."""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class AlertConfig:
    """Alert configuration settings."""
    approach_threshold_pct: float = 1.0
    breakout_threshold_pct: float = 0.5
    cooldown_seconds: int = 300
    enabled_types: List[str] = field(default_factory=lambda: [
        "approach_support", "approach_resistance",
        "bounce_support", "bounce_resistance",
        "breakout_above", "breakout_below",
        "false_breakout_above", "false_breakout_below"
    ])


@dataclass
class DetectionConfig:
    """S/R detection configuration settings."""
    min_touches: int = 2
    max_level_distance_pct: float = 0.5
    lookback_bars: int = 100
    min_volume_ratio: float = 1.0
    confidence_weights: Dict[str, float] = field(default_factory=lambda: {
        "touches": 0.4,
        "volume": 0.3,
        "freshness": 0.2,
        "tightness": 0.1
    })


@dataclass
class StreamingConfig:
    """Streaming data configuration."""
    provider: str = "yahoo"  # yahoo, alpaca, simulated
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10
    rate_limit_per_minute: int = 60
    symbols: List[str] = field(default_factory=lambda: ["AMD", "AAPL", "TSLA"])


@dataclass
class DashboardConfig:
    """Dashboard configuration."""
    refresh_rate: float = 1.0
    lookback_bars: int = 100
    theme: str = "dark"
    show_volume: bool = True
    show_pattern_labels: bool = True


@dataclass
class SystemConfig:
    """Top-level system configuration."""
    alerts: AlertConfig = field(default_factory=AlertConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    log_level: str = "INFO"
    data_dir: str = "./data"


class ConfigChange:
    """Represents a configuration change event."""
    def __init__(self, key_path: str, old_value: Any, new_value: Any, timestamp: datetime):
        self.key_path = key_path
        self.old_value = old_value
        self.new_value = new_value
        self.timestamp = timestamp


class ConfigManager:
    """
    Hot-reloadable configuration manager.

    Features:
    - File-based configuration with automatic reload on changes
    - Thread-safe access to configuration values
    - Callback notifications on configuration changes
    - Default configuration with validation
    - Nested key path access (e.g., "alerts.approach_threshold_pct")
    """

    @staticmethod
    def _create_default_config() -> SystemConfig:
        """Create a fresh default configuration instance."""
        return SystemConfig()

    def __init__(self, config_path: Optional[str] = None, auto_reload: bool = True):
        """
        Initialize the configuration manager.

        Args:
            config_path: Path to JSON config file. If None, uses default config.
            auto_reload: Whether to watch for file changes and reload automatically.
        """
        self._config_path = config_path
        self._auto_reload = auto_reload
        self._config: SystemConfig = self._create_default_config()
        self._lock = threading.RLock()
        self._watchers: List[Callable[[ConfigChange], None]] = []
        self._change_history: List[ConfigChange] = []
        self._last_modified: float = 0
        self._running = False
        self._watch_thread: Optional[threading.Thread] = None

        # Load initial config
        if config_path and os.path.exists(config_path):
            self._load_from_file(config_path)

    def _load_from_file(self, path: str) -> bool:
        """Load configuration from JSON file."""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self._config = self._parse_config(data)
            self._last_modified = os.path.getmtime(path)
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading config from {path}: {e}")
            return False

    def _parse_config(self, data: dict) -> SystemConfig:
        """Parse JSON data into SystemConfig."""
        alerts = AlertConfig(**data.get('alerts', {}))
        detection = DetectionConfig(**data.get('detection', {}))
        streaming = StreamingConfig(**data.get('streaming', {}))
        dashboard = DashboardConfig(**data.get('dashboard', {}))

        return SystemConfig(
            alerts=alerts,
            detection=detection,
            streaming=streaming,
            dashboard=dashboard,
            log_level=data.get('log_level', 'INFO'),
            data_dir=data.get('data_dir', './data')
        )

    def _serialize_config(self, config: SystemConfig) -> dict:
        """Serialize SystemConfig to dict for JSON export."""
        return {
            'alerts': asdict(config.alerts),
            'detection': {
                **asdict(config.detection),
                'confidence_weights': config.detection.confidence_weights
            },
            'streaming': asdict(config.streaming),
            'dashboard': asdict(config.dashboard),
            'log_level': config.log_level,
            'data_dir': config.data_dir
        }

    def save(self, path: Optional[str] = None) -> bool:
        """
        Save current configuration to file.

        Args:
            path: Path to save to. Uses config_path if not provided.

        Returns:
            True if save was successful.
        """
        path = path or self._config_path
        if not path:
            return False

        try:
            with open(path, 'w') as f:
                json.dump(self._serialize_config(self._config), f, indent=2)
            self._last_modified = os.path.getmtime(path)
            return True
        except IOError as e:
            print(f"Error saving config to {path}: {e}")
            return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by key path.

        Args:
            key_path: Dot-separated path (e.g., "alerts.cooldown_seconds")
            default: Default value if key not found

        Returns:
            Configuration value or default.
        """
        with self._lock:
            config_dict = self._serialize_config(self._config)
            keys = key_path.split('.')
            value = config_dict

            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default

            return value

    def set(self, key_path: str, value: Any) -> bool:
        """
        Set configuration value by key path.

        Args:
            key_path: Dot-separated path (e.g., "alerts.cooldown_seconds")
            value: New value

        Returns:
            True if set was successful.
        """
        with self._lock:
            old_value = self.get(key_path)
            if old_value == value:
                return True  # No change needed

            keys = key_path.split('.')
            obj = self._config

            # Navigate to parent object
            for key in keys[:-1]:
                if hasattr(obj, key):
                    obj = getattr(obj, key)
                else:
                    return False

            # Set the value
            final_key = keys[-1]
            if hasattr(obj, final_key):
                setattr(obj, final_key, value)
                self._record_change(key_path, old_value, value)
                return True

            return False

    def _record_change(self, key_path: str, old_value: Any, new_value: Any):
        """Record a configuration change and notify watchers."""
        change = ConfigChange(key_path, old_value, new_value, datetime.now())
        self._change_history.append(change)

        for watcher in self._watchers:
            try:
                watcher(change)
            except Exception as e:
                print(f"Error in config watcher: {e}")

    def watch(self, callback: Callable[[ConfigChange], None]):
        """
        Register a callback to be notified of configuration changes.

        Args:
            callback: Function that receives ConfigChange events.
        """
        self._watchers.append(callback)

    def unwatch(self, callback: Callable[[ConfigChange], None]):
        """Remove a configuration change callback."""
        if callback in self._watchers:
            self._watchers.remove(callback)

    def get_change_history(self, since: Optional[datetime] = None) -> List[ConfigChange]:
        """
        Get configuration change history.

        Args:
            since: Only return changes after this time.

        Returns:
            List of ConfigChange objects.
        """
        with self._lock:
            if since:
                return [c for c in self._change_history if c.timestamp >= since]
            return list(self._change_history)

    def reload(self) -> bool:
        """
        Reload configuration from file.

        Returns:
            True if reload was successful.
        """
        if not self._config_path:
            return False

        current_mtime = os.path.getmtime(self._config_path)
        if current_mtime > self._last_modified:
            return self._load_from_file(self._config_path)

        return False

    def start_watching(self):
        """Start background thread to watch for file changes."""
        if self._running or not self._config_path:
            return

        self._running = True
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._watch_thread.start()

    def stop_watching(self):
        """Stop background file watching."""
        self._running = False
        if self._watch_thread:
            self._watch_thread.join(timeout=2.0)

    def _watch_loop(self):
        """Background loop to check for file changes."""
        while self._running:
            if self._auto_reload and self._config_path and os.path.exists(self._config_path):
                try:
                    current_mtime = os.path.getmtime(self._config_path)
                    if current_mtime > self._last_modified:
                        self.reload()
                except OSError:
                    pass

            time.sleep(1.0)

    @property
    def alerts(self) -> AlertConfig:
        """Get alerts configuration."""
        with self._lock:
            return self._config.alerts

    @property
    def detection(self) -> DetectionConfig:
        """Get detection configuration."""
        with self._lock:
            return self._config.detection

    @property
    def streaming(self) -> StreamingConfig:
        """Get streaming configuration."""
        with self._lock:
            return self._config.streaming

    @property
    def dashboard(self) -> DashboardConfig:
        """Get dashboard configuration."""
        with self._lock:
            return self._config.dashboard

    def to_dict(self) -> dict:
        """Get configuration as dictionary."""
        with self._lock:
            return self._serialize_config(self._config)


def create_default_config(path: str) -> bool:
    """
    Create a default configuration file.

    Args:
        path: Path where to save the default config.

    Returns:
        True if successful.
    """
    config = SystemConfig()
    try:
        with open(path, 'w') as f:
            json.dump({
                'alerts': asdict(config.alerts),
                'detection': {
                    **asdict(config.detection),
                    'confidence_weights': config.detection.confidence_weights
                },
                'streaming': asdict(config.streaming),
                'dashboard': asdict(config.dashboard),
                'log_level': config.log_level,
                'data_dir': config.data_dir
            }, f, indent=2)
        return True
    except IOError as e:
        print(f"Error creating default config at {path}: {e}")
        return False


def load_config(path: str) -> Optional[ConfigManager]:
    """
    Load configuration from file.

    Args:
        path: Path to configuration file.

    Returns:
        ConfigManager instance or None on failure.
    """
    if not os.path.exists(path):
        return None

    manager = ConfigManager(config_path=path, auto_reload=False)
    return manager