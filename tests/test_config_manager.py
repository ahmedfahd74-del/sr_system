# tests/test_config_manager.py
"""Tests for the configuration manager module."""

import unittest
import json
import os
import tempfile
import time
import threading
from datetime import datetime

from core.config_manager import (
    AlertConfig,
    DetectionConfig,
    StreamingConfig,
    DashboardConfig,
    SystemConfig,
    ConfigChange,
    ConfigManager,
    create_default_config,
    load_config
)


class TestAlertConfig(unittest.TestCase):
    """Tests for AlertConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AlertConfig()
        self.assertEqual(config.approach_threshold_pct, 1.0)
        self.assertEqual(config.breakout_threshold_pct, 0.5)
        self.assertEqual(config.cooldown_seconds, 300)
        self.assertIn("approach_support", config.enabled_types)

    def test_custom_values(self):
        """Test custom configuration values."""
        config = AlertConfig(
            approach_threshold_pct=2.0,
            cooldown_seconds=600
        )
        self.assertEqual(config.approach_threshold_pct, 2.0)
        self.assertEqual(config.cooldown_seconds, 600)


class TestDetectionConfig(unittest.TestCase):
    """Tests for DetectionConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DetectionConfig()
        self.assertEqual(config.min_touches, 2)
        self.assertEqual(config.max_level_distance_pct, 0.5)
        self.assertEqual(config.lookback_bars, 100)

    def test_confidence_weights(self):
        """Test confidence weights configuration."""
        config = DetectionConfig()
        self.assertIn("touches", config.confidence_weights)
        self.assertIn("volume", config.confidence_weights)


class TestStreamingConfig(unittest.TestCase):
    """Tests for StreamingConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = StreamingConfig()
        self.assertEqual(config.provider, "yahoo")
        self.assertEqual(config.reconnect_delay, 5.0)
        self.assertIn("AMD", config.symbols)


class TestDashboardConfig(unittest.TestCase):
    """Tests for DashboardConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = DashboardConfig()
        self.assertEqual(config.refresh_rate, 1.0)
        self.assertEqual(config.theme, "dark")
        self.assertTrue(config.show_volume)


class TestSystemConfig(unittest.TestCase):
    """Tests for SystemConfig dataclass."""

    def test_default_values(self):
        """Test default system configuration."""
        config = SystemConfig()
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.data_dir, "./data")
        self.assertIsInstance(config.alerts, AlertConfig)

    def test_nested_configs(self):
        """Test nested configuration objects."""
        config = SystemConfig()
        self.assertIsInstance(config.alerts, AlertConfig)
        self.assertIsInstance(config.detection, DetectionConfig)
        self.assertIsInstance(config.streaming, StreamingConfig)
        self.assertIsInstance(config.dashboard, DashboardConfig)


class TestConfigChange(unittest.TestCase):
    """Tests for ConfigChange class."""

    def test_creation(self):
        """Test ConfigChange creation."""
        change = ConfigChange(
            key_path="alerts.cooldown_seconds",
            old_value=300,
            new_value=600,
            timestamp=datetime.now()
        )
        self.assertEqual(change.key_path, "alerts.cooldown_seconds")
        self.assertEqual(change.old_value, 300)
        self.assertEqual(change.new_value, 600)


class TestConfigManager(unittest.TestCase):
    """Tests for ConfigManager class."""

    def test_init_default(self):
        """Test initialization with default config."""
        manager = ConfigManager()
        self.assertEqual(manager.get("alerts.approach_threshold_pct"), 1.0)

    def test_get_set(self):
        """Test get and set operations."""
        manager = ConfigManager()
        
        # Test get
        self.assertEqual(manager.get("alerts.cooldown_seconds"), 300)
        
        # Test set
        self.assertTrue(manager.set("alerts.cooldown_seconds", 600))
        self.assertEqual(manager.get("alerts.cooldown_seconds"), 600)

    def test_get_nested_key(self):
        """Test getting nested configuration keys."""
        manager = ConfigManager()
        
        value = manager.get("detection.confidence_weights.touches")
        self.assertEqual(value, 0.4)

    def test_get_nonexistent_key(self):
        """Test getting nonexistent key returns default."""
        manager = ConfigManager()
        
        result = manager.get("nonexistent.key", "default_value")
        self.assertEqual(result, "default_value")

    def test_set_new_value(self):
        """Test setting a new configuration value."""
        manager = ConfigManager()
        
        result = manager.set("alerts.approach_threshold_pct", 3.0)
        self.assertTrue(result)
        self.assertEqual(manager.get("alerts.approach_threshold_pct"), 3.0)

    def test_set_same_value(self):
        """Test setting the same value returns True but doesn't record change."""
        manager = ConfigManager()
        
        manager.set("alerts.cooldown_seconds", 300)
        history = manager.get_change_history()
        initial_len = len(history)
        
        # Setting same value should not add to history
        manager.set("alerts.cooldown_seconds", 300)
        self.assertEqual(len(history), initial_len)

    def test_watch_callback(self):
        """Test watching for configuration changes."""
        manager = ConfigManager()
        changes_received = []

        def callback(change):
            changes_received.append(change)

        manager.watch(callback)
        manager.set("alerts.cooldown_seconds", 600)

        self.assertEqual(len(changes_received), 1)
        self.assertEqual(changes_received[0].key_path, "alerts.cooldown_seconds")
        self.assertEqual(changes_received[0].old_value, 300)
        self.assertEqual(changes_received[0].new_value, 600)

    def test_unwatch(self):
        """Test unwatching configuration changes."""
        manager = ConfigManager()
        changes = []

        def callback(change):
            changes.append(change)

        manager.watch(callback)
        manager.unwatch(callback)
        manager.set("alerts.cooldown_seconds", 600)

        self.assertEqual(len(changes), 0)

    def test_change_history(self):
        """Test configuration change history."""
        manager = ConfigManager()
        
        manager.set("alerts.cooldown_seconds", 600)
        manager.set("alerts.approach_threshold_pct", 2.0)
        
        history = manager.get_change_history()
        self.assertGreaterEqual(len(history), 2)

    def test_change_history_since(self):
        """Test getting change history since a timestamp."""
        manager = ConfigManager()
        
        manager.set("alerts.cooldown_seconds", 600)
        
        since = datetime.now()
        manager.set("alerts.approach_threshold_pct", 2.0)
        
        history = manager.get_change_history(since=since)
        self.assertEqual(len(history), 1)

    def test_properties(self):
        """Test configuration property accessors."""
        manager = ConfigManager()
        
        alerts = manager.alerts
        self.assertIsInstance(alerts, AlertConfig)
        
        detection = manager.detection
        self.assertIsInstance(detection, DetectionConfig)

    def test_to_dict(self):
        """Test configuration serialization to dict."""
        manager = ConfigManager()
        
        config_dict = manager.to_dict()
        self.assertIsInstance(config_dict, dict)
        self.assertIn("alerts", config_dict)
        self.assertIn("detection", config_dict)


class TestConfigManagerFileOperations(unittest.TestCase):
    """Tests for ConfigManager file operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.temp_file.close()

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.temp_file.name):
            os.unlink(self.temp_file.name)

    def test_save_and_load(self):
        """Test saving and loading configuration."""
        manager = ConfigManager()
        manager.set("alerts.cooldown_seconds", 600)
        
        self.assertTrue(manager.save(self.temp_file.name))
        
        # Load into new manager
        new_manager = ConfigManager(config_path=self.temp_file.name, auto_reload=False)
        self.assertEqual(new_manager.get("alerts.cooldown_seconds"), 600)

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file uses default config."""
        manager = ConfigManager(config_path="/nonexistent/path.json", auto_reload=False)
        # Should use default config when file doesn't exist
        self.assertIsInstance(manager._config, SystemConfig)
        self.assertEqual(manager.get("alerts.cooldown_seconds"), 300)

    def test_create_default_config(self):
        """Test creating default configuration file."""
        result = create_default_config(self.temp_file.name)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.temp_file.name))
        
        with open(self.temp_file.name, 'r') as f:
            data = json.load(f)
            self.assertIn("alerts", data)
            self.assertIn("detection", data)


class TestConfigManagerAutoReload(unittest.TestCase):
    """Tests for ConfigManager auto-reload functionality."""

    def test_reload(self):
        """Test manual reload functionality."""
        # Create initial config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'alerts': {'cooldown_seconds': 300},
                'detection': {},
                'streaming': {},
                'dashboard': {}
            }, f)
            temp_path = f.name

        try:
            manager = ConfigManager(config_path=temp_path, auto_reload=False)
            self.assertEqual(manager.get("alerts.cooldown_seconds"), 300)
            
            # Modify file
            with open(temp_path, 'w') as f:
                json.dump({
                    'alerts': {'cooldown_seconds': 600},
                    'detection': {},
                    'streaming': {},
                    'dashboard': {}
                }, f)
            
            # Reload
            manager.reload()
            self.assertEqual(manager.get("alerts.cooldown_seconds"), 600)
        finally:
            os.unlink(temp_path)

    def test_watch_unwatch_lifecycle(self):
        """Test start/stop watching lifecycle."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'alerts': {},
                'detection': {},
                'streaming': {},
                'dashboard': {}
            }, f)
            temp_path = f.name

        try:
            manager = ConfigManager(config_path=temp_path, auto_reload=True)
            
            # Should not be running initially
            self.assertFalse(manager._running)
            
            manager.start_watching()
            self.assertTrue(manager._running)
            
            manager.stop_watching()
            self.assertFalse(manager._running)
        finally:
            os.unlink(temp_path)


class TestLoadConfig(unittest.TestCase):
    """Tests for load_config function."""

    def test_load_existing_file(self):
        """Test loading an existing configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'alerts': {'cooldown_seconds': 500},
                'detection': {},
                'streaming': {},
                'dashboard': {}
            }, f)
            temp_path = f.name

        try:
            manager = load_config(temp_path)
            self.assertIsNotNone(manager)
            self.assertEqual(manager.get("alerts.cooldown_seconds"), 500)
        finally:
            os.unlink(temp_path)

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file returns None."""
        manager = load_config("/nonexistent/config.json")
        self.assertIsNone(manager)


if __name__ == "__main__":
    unittest.main()