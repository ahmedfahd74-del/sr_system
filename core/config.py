# sr_system/core/config.py
"""Configuration for the S/R system."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class DataConfig:
    source: str = "yahoo"  # "alpaca" or "yahoo"
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    cache_enabled: bool = True
    cache_ttl_seconds: int = 60


@dataclass
class DetectionConfig:
    horizontal: dict = field(default_factory=lambda: {
        "lookback": 100,
        "pivot_strength_min": 2,
        "atr_multiplier": 2.0,
        "merge_threshold_pct": 0.5,
    })
    trendline: dict = field(default_factory=lambda: {
        "slope_sensitivity": 0.001,
        "min_touches": 2,
        "lookback": 50,
    })
    fractal: dict = field(default_factory=lambda: {
        "fractal_period": 2,
    })
    volume: dict = field(default_factory=lambda: {
        "percentile": 70,
    })
    vwap: dict = field(default_factory=lambda: {
        "deviation_multipliers": [1.0, 2.0, 3.0],
    })


@dataclass
class AdaptiveConfig:
    regimes: dict = field(default_factory=lambda: {
        "trending": {"lookback": 100, "min_touches": 2, "atr_mult": 2.0},
        "ranging": {"lookback": 50, "min_touches": 3, "atr_mult": 1.5},
        "volatile": {"lookback": 150, "min_touches": 2, "atr_mult": 3.0},
        "low_vol": {"lookback": 30, "min_touches": 4, "atr_mult": 1.0},
    })
    confluence_min_tfs: int = 2
    confidence_weights: dict = field(default_factory=lambda: {
        "touches": 0.30,
        "volume": 0.25,
        "recency": 0.20,
        "confluence": 0.25,
    })


@dataclass
class TimeframeConfig:
    timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1H", "4H", "1D"])
    tf_weights: dict = field(default_factory=lambda: {
        "1m": 0.05, "5m": 0.10, "15m": 0.15,
        "1H": 0.25, "4H": 0.20, "1D": 0.25,
    })


@dataclass
class SignalConfig:
    breakout_volume_threshold: float = 1.5  # volume > avg * this
    bounce_confirmation_bars: int = 2
    trailing_activation_bars: int = 3


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    adaptive: AdaptiveConfig = field(default_factory=AdaptiveConfig)
    timeframe: TimeframeConfig = field(default_factory=TimeframeConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)


# Global config instance
_config = Config()


def get_config() -> Config:
    return _config


def update_config(**kwargs):
    """Update config values dynamically."""
    for section, values in kwargs.items():
        if hasattr(_config, section):
            section_obj = getattr(_config, section)
            if isinstance(values, dict):
                for k, v in values.items():
                    if hasattr(section_obj, k):
                        setattr(section_obj, k, v)