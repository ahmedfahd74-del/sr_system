# notebooks/dashboard.py
"""Real-time dashboard for S/R level visualization."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from datetime import datetime, timedelta
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

# For non-interactive backend when running headless
import os
if os.environ.get('DISPLAY') is None:
    import matplotlib
    matplotlib.use('Agg')


class PriceChart:
    """Real-time price chart with S/R level overlay."""

    def __init__(
        self,
        ticker: str,
        timeframe: str = "1D",
        lookback_bars: int = 100
    ):
        self.ticker = ticker
        self.timeframe = timeframe
        self.lookback_bars = lookback_bars

        # Price data
        self.timestamps: deque = deque(maxlen=lookback_bars)
        self.opens: deque = deque(maxlen=lookback_bars)
        self.highs: deque = deque(maxlen=lookback_bars)
        self.lows: deque = deque(maxlen=lookback_bars)
        self.closes: deque = deque(maxlen=lookback_bars)
        self.volumes: deque = deque(maxlen=lookback_bars)

        # S/R levels
        self.support_levels: List[float] = []
        self.resistance_levels: List[float] = []
        self.support_confidences: List[float] = []
        self.resistance_confidences: List[float] = []

        # Pattern/recommendations
        self.current_pattern: str = "unknown"
        self.signal: str = "neutral"
        self.regime: str = "unknown"

    def add_bar(self, timestamp: datetime, o: float, h: float, l: float, c: float, v: float):
        """Add a new bar of data."""
        self.timestamps.append(timestamp)
        self.opens.append(o)
        self.highs.append(h)
        self.lows.append(l)
        self.closes.append(c)
        self.volumes.append(v)

    def update_levels(self, support: List[Tuple[float, float]], resistance: List[Tuple[float, float]]):
        """Update S/R levels with confidences."""
        self.support_levels = [s[0] for s in support]
        self.support_confidences = [s[1] for s in support]
        self.resistance_levels = [r[0] for r in resistance]
        self.resistance_confidences = [r[1] for r in resistance]

    def update_regime(self, regime: str, pattern: str, signal: str):
        """Update market regime and signal."""
        self.regime = regime
        self.current_pattern = pattern
        self.signal = signal


class AlertPanel:
    """Alert feed panel."""

    def __init__(self, max_alerts: int = 20):
        self.max_alerts = max_alerts
        self.alerts: deque = deque(maxlen=max_alerts)

    def add_alert(self, alert_dict: dict):
        """Add a new alert."""
        self.alerts.append({
            'timestamp': datetime.now(),
            'alert_type': alert_dict.get('alert_type', 'unknown'),
            'message': alert_dict.get('message', ''),
            'severity': alert_dict.get('severity', 'low')
        })

    def get_recent(self, count: int = 5) -> List[dict]:
        """Get recent alerts."""
        return list(self.alerts)[-count:]


class Dashboard:
    """
    Real-time S/R system dashboard.

    Displays:
    - Price chart with S/R level overlay
    - Current market regime and pattern
    - Alert feed
    - Key metrics
    """

    def __init__(
        self,
        tickers: List[str],
        timeframe: str = "1D",
        refresh_rate: float = 1.0  # seconds
    ):
        self.tickers = tickers
        self.timeframe = timeframe
        self.refresh_rate = refresh_rate

        # Charts per ticker
        self.charts: Dict[str, PriceChart] = {
            ticker: PriceChart(ticker, timeframe) for ticker in tickers
        }

        # Alert panel
        self.alert_panel = AlertPanel()

        # Metrics
        self.metrics: Dict[str, dict] = {}

        # Figure and axes
        self._fig = None
        self._axes = None
        self._running = False
        self._update_thread = None

        # Callbacks
        self._on_update_callbacks: List[callable] = []

    def add_update_callback(self, callback: callable):
        """Add callback called on each update."""
        self._on_update_callbacks.append(callback)

    def setup_plot(self, figsize: Tuple[int, int] = (14, 10)):
        """Initialize the plot layout."""
        # Create figure with custom layout
        self._fig = plt.figure(figsize=figsize)
        gs = self._fig.add_gridspec(
            3, 2,
            width_ratios=[3, 1],
            height_ratios=[3, 1, 1],
            wspace=0.3,
            hspace=0.4
        )

        # Main chart area (top left, spanning 2 columns)
        self._axes = {
            'chart': self._fig.add_subplot(gs[0, :]),
            'metrics': self._fig.add_subplot(gs[1, 0]),
            'pattern': self._fig.add_subplot(gs[1, 1]),
            'alerts': self._fig.add_subplot(gs[2, :]),
        }

        # Style setup
        self._fig.patch.set_facecolor('#1a1a2e')
        for ax in self._axes.values():
            ax.set_facecolor('#16213e')
            ax.tick_params(colors='#94a3b8')
            ax.xaxis.label.set_color('#94a3b8')
            ax.yaxis.label.set_color('#94a3b8')
            ax.title.set_color('#e2e8f0')

        # Main chart setup
        self._setup_chart_axis()

        plt.ion()  # Interactive mode

    def _setup_chart_axis(self):
        """Setup the main price chart axis."""
        ax = self._axes['chart']
        ax.set_xlabel('Time')
        ax.set_ylabel('Price ($)')
        ax.grid(True, alpha=0.2, color='#64748b')

    def update_price(self, ticker: str, timestamp: datetime, o: float, h: float, l: float, c: float, v: float):
        """Update price data for a ticker."""
        if ticker in self.charts:
            self.charts[ticker].add_bar(timestamp, o, h, l, c, v)

    def update_levels(
        self,
        ticker: str,
        support: List[Tuple[float, float]],
        resistance: List[Tuple[float, float]]
    ):
        """Update S/R levels for a ticker."""
        if ticker in self.charts:
            self.charts[ticker].update_levels(support, resistance)

    def update_regime(self, ticker: str, regime: str, pattern: str, signal: str):
        """Update regime info for a ticker."""
        if ticker in self.charts:
            self.charts[ticker].update_regime(regime, pattern, signal)

    def add_alert(self, alert_dict: dict):
        """Add an alert to the panel."""
        self.alert_panel.add_alert(alert_dict)

    def update_metrics(self, metrics: dict):
        """Update dashboard metrics."""
        self.metrics.update(metrics)

    def render(self):
        """Render the current state of the dashboard."""
        if self._fig is None:
            self.setup_plot()

        self._render_chart()
        self._render_metrics()
        self._render_pattern()
        self._render_alerts()

        self._fig.canvas.draw()
        self._fig.canvas.flush_events()

        # Call any update callbacks
        for callback in self._on_update_callbacks:
            try:
                callback(self)
            except Exception:
                pass

    def _render_chart(self):
        """Render the price chart with S/R levels."""
        ax = self._axes['chart']
        ax.clear()

        # Plot first ticker as primary
        if not self.tickers:
            return

        ticker = self.tickers[0]
        chart = self.charts.get(ticker)
        if chart is None or len(chart.closes) == 0:
            ax.set_title(f"{ticker} - No Data")
            return

        # Plot candlesticks
        x = range(len(chart.closes))
        colors = ['#10b981' if chart.closes[i] >= chart.opens[i] else '#ef4444'
                  for i in range(len(chart.closes))]

        # Draw candles
        for i in range(len(chart.closes)):
            o, h, l, c = chart.opens[i], chart.highs[i], chart.lows[i], chart.closes[i]
            color = colors[i]
            ax.plot([i, i], [l, h], color=color, linewidth=0.5)
            ax.plot([i, i], [o, c], color=color, linewidth=2)

        # Draw S/R levels
        for i, (level, conf) in enumerate(zip(chart.support_levels, chart.support_confidences)):
            alpha = 0.3 + (conf / 100) * 0.5
            ax.axhline(y=level, color='#10b981', linestyle='--', alpha=alpha, linewidth=1.5)
            ax.annotate(f'S ${level:.2f}', xy=(len(chart.closes)-1, level),
                       xytext=(5, 0), textcoords='offset points',
                       color='#10b981', fontsize=8, alpha=alpha)

        for i, (level, conf) in enumerate(zip(chart.resistance_levels, chart.resistance_confidences)):
            alpha = 0.3 + (conf / 100) * 0.5
            ax.axhline(y=level, color='#ef4444', linestyle='--', alpha=alpha, linewidth=1.5)
            ax.annotate(f'R ${level:.2f}', xy=(len(chart.closes)-1, level),
                       xytext=(5, 0), textcoords='offset points',
                       color='#ef4444', fontsize=8, alpha=alpha)

        # Current price line
        current_price = chart.closes[-1] if chart.closes else 0
        ax.axhline(y=current_price, color='#fbbf24', linestyle='-', alpha=0.7, linewidth=1)

        # Title with ticker and current price
        price_str = f"${current_price:.2f}" if current_price else "N/A"
        signal_color = '#10b981' if chart.signal == 'bullish' else '#ef4444' if chart.signal == 'bearish' else '#94a3b8'
        ax.set_title(f"{ticker} {chart.timeframe} | {price_str} | {chart.signal.upper()}",
                    color=signal_color, fontsize=12, fontweight='bold')

        ax.grid(True, alpha=0.2, color='#64748b')

        # Legend
        legend_elements = [
            Line2D([0], [0], color='#10b981', linewidth=2, label='Support'),
            Line2D([0], [0], color='#ef4444', linewidth=2, label='Resistance'),
            Line2D([0], [0], color='#fbbf24', linewidth=2, label='Current Price'),
        ]
        ax.legend(handles=legend_elements, loc='upper left', fontsize=8,
                 facecolor='#16213e', edgecolor='#64748b', labelcolor='#94a3b8')

    def _render_metrics(self):
        """Render key metrics panel."""
        ax = self._axes['metrics']
        ax.clear()

        if not self.tickers:
            ax.set_visible(False)
            return

        ticker = self.tickers[0]
        chart = self.charts.get(ticker)

        metrics_text = "Key Metrics\n" + "-" * 20 + "\n"

        if chart and len(chart.closes) > 0:
            current = chart.closes[-1]
            prev = chart.closes[-2] if len(chart.closes) > 1 else current
            change = ((current - prev) / prev * 100) if prev != 0 else 0

            metrics_text += f"Regime: {chart.regime.upper()}\n"
            metrics_text += f"Change: {change:+.2f}%\n"
            metrics_text += f"Support Levels: {len(chart.support_levels)}\n"
            metrics_text += f"Resistance Levels: {len(chart.resistance_levels)}"

        ax.text(0.05, 0.95, metrics_text, transform=ax.transAxes,
               verticalalignment='top', fontfamily='monospace',
               color='#e2e8f0', fontsize=10)
        ax.axis('off')

    def _render_pattern(self):
        """Render pattern detection panel."""
        ax = self._axes['pattern']
        ax.clear()

        if not self.tickers:
            ax.set_visible(False)
            return

        ticker = self.tickers[0]
        chart = self.charts.get(ticker)

        pattern_text = "Pattern\n" + "-" * 20 + "\n"

        if chart:
            pattern_text += f"{chart.current_pattern.upper()}\n\n"
            pattern_text += f"Signal: {chart.signal.upper()}"

        pattern_color = '#10b981' if chart.signal == 'bullish' else '#ef4444' if chart.signal == 'bearish' else '#94a3b8'

        ax.text(0.05, 0.95, pattern_text, transform=ax.transAxes,
               verticalalignment='top', fontfamily='monospace',
               color='#e2e8f0', fontsize=10)

        # Color box for signal
        box_props = dict(boxstyle='round', facecolor=pattern_color, alpha=0.3)
        ax.text(0.95, 0.05, chart.signal.upper(), transform=ax.transAxes,
               horizontalalignment='right', fontsize=12, fontweight='bold',
               color=pattern_color, bbox=box_props)

        ax.axis('off')

    def _render_alerts(self):
        """Render alert feed panel."""
        ax = self._axes['alerts']
        ax.clear()

        alerts = self.alert_panel.get_recent(5)

        if not alerts:
            ax.text(0.05, 0.5, "No recent alerts",
                   transform=ax.transAxes, color='#64748b', fontsize=10)
        else:
            y = 0.9
            for alert in reversed(alerts):
                time_str = alert['timestamp'].strftime('%H:%M:%S')
                sev = alert['severity'][0].upper()  # First letter
                color = {'h': '#ef4444', 'm': '#fbbf24', 'l': '#10b981'}.get(sev.lower(), '#94a3b8')
                msg = f"[{time_str}] {sev} - {alert['message'][:50]}"
                ax.text(0.02, y, msg, transform=ax.transAxes,
                       color=color, fontsize=8, verticalalignment='top')
                y -= 0.18

        ax.set_title("Recent Alerts", color='#e2e8f0', fontsize=10)
        ax.axis('off')

    def start(self):
        """Start the dashboard update loop."""
        if self._running:
            return

        self._running = True
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()

    def stop(self):
        """Stop the dashboard."""
        self._running = False

    def _update_loop(self):
        """Background update loop."""
        while self._running:
            self.render()
            time.sleep(self.refresh_rate)

            # Call any update callbacks
            for callback in self._on_update_callbacks:
                try:
                    callback(self)
                except Exception:
                    pass

    def show(self, block: bool = True):
        """Show the dashboard."""
        if self._fig is None:
            self.setup_plot()

        if block:
            if not self._running:
                self._running = True
            try:
                plt.show(block=True)
            except KeyboardInterrupt:
                self._running = False
        else:
            if not self._running:
                self.start()
            plt.show(block=False)

    def save(self, path: str):
        """Save dashboard to image file."""
        if self._fig:
            self._fig.savefig(path, dpi=150, facecolor='#1a1a2e')


def create_demo_dashboard(ticker: str = "AMD", timeframe: str = "1D") -> Dashboard:
    """
    Create a demo dashboard with simulated data.

    Args:
        ticker: Ticker symbol
        timeframe: Timeframe string

    Returns:
        Dashboard instance
    """
    dashboard = Dashboard([ticker], timeframe, refresh_rate=2.0)

    # Generate initial demo data
    import random
    base_price = 100.0

    for i in range(50):
        timestamp = datetime.now() - timedelta(minutes=50-i)
        change = random.uniform(-1, 1.5)
        base_price += change
        open_price = base_price + random.uniform(-0.5, 0.5)
        close_price = base_price
        high_price = max(open_price, close_price) + random.uniform(0, 1)
        low_price = min(open_price, close_price) - random.uniform(0, 1)
        volume = random.randint(500000, 2000000)

        dashboard.update_price(ticker, timestamp, open_price, high_price, low_price, close_price, volume)

    # Add some S/R levels
    support = [(95.0, 75), (92.0, 60), (88.0, 45)]
    resistance = [(105.0, 80), (110.0, 65), (115.0, 50)]
    dashboard.update_levels(ticker, support, resistance)

    # Set regime info
    dashboard.update_regime(ticker, "trending", "breakout_imminent", "bullish")

    return dashboard


def run_demo():
    """Run the demo dashboard."""
    print("Starting demo dashboard...")

    dashboard = create_demo_dashboard("AMD", "1H")
    dashboard.setup_plot()

    # Simulate updates in a separate thread
    def simulate_updates():
        import random
        base_price = 100.0
        for _ in range(20):
            timestamp = datetime.now()
            change = random.uniform(-0.5, 0.8)
            base_price += change
            open_price = base_price + random.uniform(-0.3, 0.3)
            close_price = base_price
            high_price = max(open_price, close_price) + random.uniform(0, 0.5)
            low_price = min(open_price, close_price) - random.uniform(0, 0.5)
            volume = random.randint(500000, 2000000)

            dashboard.update_price("AMD", timestamp, open_price, high_price, low_price, close_price, volume)

            # Occasionally add alerts
            if random.random() < 0.2:
                alert_types = ["approach_support", "approach_resistance", "breakout_above"]
                dashboard.add_alert({
                    "alert_type": random.choice(alert_types),
                    "message": f"AMD {random.choice(['approaching', 'bouncing', 'breaking'])} level",
                    "severity": random.choice(["low", "medium", "high"])
                })

            time.sleep(1.0)

    update_thread = threading.Thread(target=simulate_updates, daemon=True)
    update_thread.start()

    dashboard.show(block=True)


if __name__ == "__main__":
    run_demo()