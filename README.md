# Adaptive MTF Support & Resistance System

A self-adapting, AI-powered S/R detection engine that works across any ticker and timeframe.

## Features

- **Multi-Method Detection**: Combines 3 S/R detection methods:
  - **Horizontal** - Pivot-based price levels with ATR proximity
  - **Trendline** - Diagonal support/resistance using linear regression
  - **Fractal** - Bill Williams 5-bar fractal detection

- **Adaptive Parameters**: Automatically adjusts detection parameters based on market regime:
  - Trending, Ranging, Volatile, Low-Vol

- **Multi-Timeframe Analysis**: Processes 6 timeframes simultaneously (1m to 1D)

- **Confluence Detection**: Identifies levels confirmed across multiple timeframes

- **Real-time Signals**: Bullish/Bearish/Neutral signals based on price proximity to S/R

## Architecture

```
sr_system/
├── core/
│   ├── config.py       # Configuration dataclasses
│   └── engine.py       # Main SREngine orchestrator
├── data/
│   ├── ohlcv.py        # OHLCV data structures
│   ├── cache.py        # Thread-safe in-memory cache
│   ├── storage.py      # SQLite persistence
│   └── sources/
│       └── yahoo_direct.py  # Yahoo Finance data source
├── detection/
│   ├── horizontal.py   # Pivot-based S/R
│   ├── trendline.py    # Diagonal S/R
│   └── fractal.py      # Bill Williams fractals
├── adaptive/
├── ai/
│   ├── features.py      # Market feature extraction
│   ├── pattern.py       # Pattern recognition
│   └── signal_enhancer.py  # Entry timing & risk management
├── signals/
├── tests/
│   ├── test_detection.py    # Unit tests (27 tests)
│   ├── test_ai_modules.py   # AI module tests (24 tests)
│   └── test_full_system.py  # Integration tests (10 tests)
└── notebooks/
    └── visualize.py    # Chart visualization
```

## Quick Start

```bash
# Install dependencies
pip install numpy requests matplotlib

# Run visualization
python3 notebooks/visualize.py AMD 1D

# Run full system test
python3 tests/test_full_system.py

# Run unit tests
python3 -m unittest tests.test_detection -v
```

## Usage Example

```python
from core.engine import SREngine

# Initialize engine
engine = SREngine()

# Run unified multi-method detection
unified = engine.detect_unified("AMD", "1D")

# Access results by timeframe
for tf, levels in unified.items():
    print(f"{tf} Support: {[l.price for l in levels['support'][:3]]}")
    print(f"{tf} Resistance: {[l.price for l in levels['resistance'][:3]]}")

# Get price action analysis
analysis = engine.analyze_price_action("AMD", 450.0, "1D")
print(f"Signal: {analysis['signal']}")  # "bullish", "bearish", "neutral"
print(f"Regime: {analysis['regime']}")   # "trending", "ranging", etc.
```

## Detection Methods

### Horizontal S/R
- Finds pivot highs/lows
- Counts touches within ATR distance
- Merges nearby levels
- Confidence based on: touch count, volume, recency

### Trendline S/R
- Identifies swing points
- Fits linear regression (R² quality check)
- Classifies as support/resistance by price interaction
- Slope sensitivity threshold

### Fractal S/R
- Bill Williams 5-bar fractal detection
- Configurable period (default: 2 = 5-bar)
- Strength based on: protrusion height, volume, recency

## Market Regime Adaptation

| Regime | Lookback | Min Touches | ATR Multiplier | Dominant Method |
|--------|----------|-------------|----------------|-----------------|
| Trending | 100 | 2 | 2.0 | Trendline |
| Ranging | 50 | 3 | 1.5 | Horizontal |
| Volatile | 150 | 2 | 3.0 | VWAP (future) |
| Low-Vol | 30 | 4 | 1.0 | Volume Profile (future) |

## Confidence Scoring

Each S/R level is scored 0-100 based on:
- **Touches** (30%): Number of times price tested the level
- **Volume** (25%): Volume at touch points vs average
- **Recency** (20%): Recent touches weighted higher
- **Confluence** (25%): Multi-timeframe confirmation bonus

## Data Sources

- **Primary**: Yahoo Finance (free, no API key required)
- **Alternative**: Alpaca (real-time, requires API key)
- **Storage**: SQLite for persistence, in-memory cache for speed

## Testing

- **27 unit tests** covering all detection modules
- **24 AI module tests** covering pattern recognition and signal enhancement
- **10 integration tests** covering full system pipeline
- Tests for edge cases: empty data, flat data, extreme volatility

```bash
# Run all tests
python3 -m unittest discover tests -v

# Run AI module tests specifically
PYTHONPATH=. python3 -m unittest tests.test_ai_modules -v
```

## AI Enhancement (Phase 3)

The AI module provides intelligent market analysis for better trade timing.

### Features Extraction
- **ATR**: Current vs average volatility ratio
- **Volume**: Ratio, coefficient of variation, uniformity
- **Momentum**: Price change percentage over lookback
- **Range Narrowing**: 5-bar vs 20-bar range compression
- **ADX**: Trend strength (0-100) and direction
- **Consolidation Score**: 0-100, how compressed price is
- **Symmetry Score**: How symmetric the consolidation is

### Pattern Recognition
Detects market patterns to suggest actions:

| Pattern | Action | Conditions |
|---------|--------|------------|
| CONSOLIDATION | HOLD | Range compression + stable volume |
| BREAKOUT_IMMINENT | BUY/SELL | Compression + volume buildup + momentum |
| FALSE_BREAKOUT | SELL/BUY | Strong move + reversal + high volume |
| TREND_CONTINUATION | BUY/SELL | Strong ADX + healthy momentum |

### Signal Enhancement
Provides entry timing with risk management:
- **Entry Zone**: Optimal buy/sell zone around S/R level
- **Stop Loss**: Based on recent structure and ATR
- **Take Profit**: Based on volatility expansion estimate
- **Risk/Reward**: Calculated ratio for trade validation
- **Confidence Score**: 0-100 based on multiple factors

### Usage Example
```python
from core.engine import SREngine

engine = SREngine()

# Analyze market pattern
pattern = engine.analyze_pattern("AMD", "1D")
print(f"Pattern: {pattern.pattern_type.value}")
print(f"Action: {pattern.action.value}")
print(f"Confidence: {pattern.confidence:.0f}%")

# Enhance a support signal
signal = engine.enhance_signal("AMD", "support", "1D")
print(f"Entry: ${signal.entry_price:.2f}")
print(f"Stop: ${signal.stop_loss:.2f}")
print(f"TP: ${signal.take_profit:.2f}")
print(f"Risk/Reward: {signal.risk_reward_ratio:.1f}:1")
```

## Current Status

✅ Phase 1: Foundation (Data layer, Horizontal S/R, Engine)  
✅ Phase 2: Multi-Method Detection (Trendline, Fractal)  
✅ Phase 3: AI Enhancement (Pattern recognition, Signal enhancement)  
⏳ Phase 4: Production (Real-time streaming, Dashboard, Alerts)

## License

MIT