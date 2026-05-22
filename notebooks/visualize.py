# sr_system/notebooks/visualize.py
"""Basic S/R visualization for AMD."""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from core.engine import get_engine
from detection.horizontal import SRLevel


def plot_sr_chart(ticker: str = "AMD", primary_tf: str = "1D"):
    """Plot price chart with S/R levels."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("matplotlib not installed. Install with: pip install matplotlib")
        return

    engine = get_engine()

    print(f"Analyzing {ticker} on {primary_tf} timeframe...")
    results = engine.detect_mtf_sr(ticker, primary_tf)

    if primary_tf not in results:
        print("No data found. Check your internet connection.")
        return

    support, resistance = results[primary_tf]

    # Get price data
    mtf_data = engine._get_mtf_data(ticker, [primary_tf])
    data = mtf_data[primary_tf]
    closes = data.closes
    highs = data.highs
    lows = data.lows
    timestamps = data.timestamps

    # Get current price
    current_price = closes[-1]

    # Plot
    fig, ax = plt.subplots(figsize=(14, 8))

    # Price line
    ax.plot(timestamps, closes, color='black', linewidth=1, label='Close')

    # Support levels (green)
    for level in support[:5]:
        ax.axhline(y=level.price, color='green', linestyle='--', alpha=0.7,
                   label=f'Support ${level.price:.2f} (conf: {level.confidence:.0f})' if level == support[0] else None)

    # Resistance levels (red)
    for level in resistance[:5]:
        ax.axhline(y=level.price, color='red', linestyle='--', alpha=0.7,
                   label=f'Resistance ${level.price:.2f} (conf: {level.confidence:.0f})' if level == resistance[0] else None)

    # Current price line
    ax.axhline(y=current_price, color='blue', linestyle='-', alpha=0.5, linewidth=2,
               label=f'Current ${current_price:.2f}')

    # Confluence levels
    confluence = engine.get_confluence_levels(ticker)
    for level in confluence[:3]:
        color = 'green' if level.is_support else 'red'
        ax.axhline(y=level.price, color=color, linestyle='-', alpha=0.9, linewidth=2)

    # Regime analysis
    regime = engine.classify_regime(data)
    ax.set_title(f'{ticker} S/R Analysis - {primary_tf} | Regime: {regime.name.upper()} ({regime.trend_direction})',
                 fontsize=14, fontweight='bold')

    ax.set_ylabel('Price ($)')
    ax.set_xlabel('Date')
    ax.legend(loc='upper left', fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(f'/Users/ahmedaziz2/sr_system/notebooks/{ticker}_sr_analysis.png', dpi=150)
    print(f"Chart saved to notebooks/{ticker}_sr_analysis.png")

    # Print summary
    print("\n" + "="*60)
    print(f"SUMMARY FOR {ticker}")
    print("="*60)
    print(f"Current Price: ${current_price:.2f}")
    print(f"Market Regime: {regime.name} ({regime.trend_direction})")
    print(f"\nTop Support Levels:")
    for i, s in enumerate(support[:3], 1):
        dist = (current_price - s.price) / current_price * 100
        print(f"  {i}. ${s.price:.2f} | Confidence: {s.confidence:.0f} | Distance: {dist:.2f}%")

    print(f"\nTop Resistance Levels:")
    for i, r in enumerate(resistance[:3], 1):
        dist = (r.price - current_price) / current_price * 100
        print(f"  {i}. ${r.price:.2f} | Confidence: {r.confidence:.0f} | Distance: {dist:.2f}%")

    if confluence:
        print(f"\nConfluence Levels (multi-TF):")
        for c in confluence[:3]:
            print(f"  ${c.price:.2f} ({c.level_type}) | Confidence: {c.confidence:.0f} | {c.source}")

    # Analyze price action
    analysis = engine.analyze_price_action(ticker, current_price, primary_tf)
    print(f"\nSignal: {analysis['signal'].upper()}")
    print(f"Reason: {analysis['signal_reason']}")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AMD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1D"
    plot_sr_chart(ticker, tf)