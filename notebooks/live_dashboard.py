# sr_system/notebooks/live_dashboard.py
"""Live S/R dashboard: real Yahoo data + detection + alerts + chart, all wired together.

This is the end-to-end runner that ties together every phase of the system:

    Phase 1 (data + detection)  -> core.engine.SREngine
    Phase 2 (multi-method)      -> engine.detect_unified / get_confluence_levels
    Phase 3 (AI enhancement)    -> engine.analyze_pattern / analyze_price_action
    Phase 4 (alerts + dashboard) -> signals.alerts.SRAlertDetector + notebooks.dashboard

It polls Yahoo Finance on a configurable interval, refreshes the engine, runs
alert detection against the latest price, and renders the dashboard.

Two modes:
- Interactive (DISPLAY available, e.g. running on your Mac):
    Live matplotlib window that updates in place. Close it to stop.
- Headless (no DISPLAY, e.g. server, sandbox):
    Each tick saves notebooks/<TICKER>_live.png so you can refresh it externally.

Usage from the repo root:

    PYTHONPATH=. python3 notebooks/live_dashboard.py AMD 1D 30
    PYTHONPATH=. python3 notebooks/live_dashboard.py SPY 1H 60
    PYTHONPATH=. python3 notebooks/live_dashboard.py TSLA 5m 15

Args:
    ticker     - any Yahoo ticker (default AMD)
    timeframe  - 1m, 5m, 15m, 1H, 1D (default 1D)
    interval   - poll interval in seconds (default 30)
"""
from __future__ import annotations

import os
import sys
import time
import signal as _signal_mod
from datetime import datetime
from typing import List, Tuple

# Make sure the project root is importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Headless detection BEFORE pyplot import inside dashboard module.
import matplotlib

if os.environ.get("DISPLAY") is None and sys.platform != "darwin":
    matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from core.engine import get_engine  # noqa: E402
from signals.alerts import SRAlertDetector, AlertConfig, Alert  # noqa: E402
from notebooks.dashboard import Dashboard  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_interactive() -> bool:
    """True iff we have a real display (Mac with backend, or X11)."""
    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY"))


def _atr_from_data(data) -> float:
    """Best-effort ATR(14) on an OHLCVData object. Falls back to a fraction of price."""
    try:
        highs = list(data.highs)
        lows = list(data.lows)
        closes = list(data.closes)
    except Exception:
        return 0.0

    if len(closes) < 2:
        return max(closes[-1] * 0.01, 0.01) if closes else 0.01

    period = min(14, len(closes) - 1)
    trs = []
    for i in range(len(closes) - period, len(closes)):
        if i <= 0:
            continue
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if not trs:
        return max(closes[-1] * 0.01, 0.01)
    return sum(trs) / len(trs)


def _format_alert(alert: Alert) -> str:
    return (
        f"{alert.severity.value.upper():<8} "
        f"{alert.alert_type.value:<22} "
        f"{alert.ticker} @ {alert.current_price:.2f} "
        f"vs level {alert.level_price:.2f} "
        f"({alert.distance_pct:+.2f}%)"
    )


# ---------------------------------------------------------------------------
# Live runner
# ---------------------------------------------------------------------------

class LiveRunner:
    """Glue between the engine, alert detector, and dashboard."""

    def __init__(self, ticker: str, timeframe: str, interval_seconds: float):
        self.ticker = ticker
        self.timeframe = timeframe
        self.interval = max(5.0, float(interval_seconds))

        self.engine = get_engine()
        self.alerts = SRAlertDetector(AlertConfig(
            approach_threshold_pct=0.75,
            breakout_atr_mult=1.5,
            cooldown_seconds=120,
            file_log_enabled=False,  # we already echo to console
        ))

        # Echo every alert to stdout so the user sees them even in headless mode.
        self.alerts.add_notification_callback(self._on_alert)

        self.dashboard = Dashboard([ticker], timeframe, refresh_rate=1.0)
        self.dashboard.setup_plot()

        self.tick_count = 0
        self._stop = False

        # Graceful shutdown on Ctrl+C.
        _signal_mod.signal(_signal_mod.SIGINT, self._handle_sigint)

    def _handle_sigint(self, *_args):
        print("\n[live] received Ctrl+C, shutting down ...")
        self._stop = True

    def _on_alert(self, alert: Alert):
        # Mirror the alert into the dashboard's alert panel and echo it.
        self.dashboard.add_alert(alert.to_dict())
        print(f"[ALERT] {_format_alert(alert)}")

    # -- one polling cycle ------------------------------------------------

    def _tick(self) -> None:
        self.tick_count += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[tick {self.tick_count} @ {ts}] refreshing {self.ticker} {self.timeframe} ...")

        # 1) Fetch + detect (Phases 1 + 2)
        results = self.engine.detect_mtf_sr(self.ticker, self.timeframe)
        if self.timeframe not in results:
            print(f"[live] no data for {self.ticker} {self.timeframe} this cycle")
            return

        support_levels, resistance_levels = results[self.timeframe]

        mtf_data = self.engine._get_mtf_data(self.ticker, [self.timeframe])
        data = mtf_data.get(self.timeframe)
        if data is None or not list(data.closes):
            print("[live] empty bar data this cycle")
            return

        current_price = float(data.closes[-1])
        atr = _atr_from_data(data)

        # 2) Push every bar into the dashboard's price chart.
        for i in range(len(data.closes)):
            self.dashboard.update_price(
                self.ticker,
                data.timestamps[i] if hasattr(data, "timestamps") else datetime.now(),
                float(data.opens[i]),
                float(data.highs[i]),
                float(data.lows[i]),
                float(data.closes[i]),
                float(data.volumes[i]) if hasattr(data, "volumes") else 0.0,
            )

        # 3) Convert SRLevel objects into the (price, confidence) tuples the dashboard expects.
        s_pairs: List[Tuple[float, float]] = [
            (float(lvl.price), float(getattr(lvl, "confidence", 0.0)))
            for lvl in support_levels[:5]
        ]
        r_pairs: List[Tuple[float, float]] = [
            (float(lvl.price), float(getattr(lvl, "confidence", 0.0)))
            for lvl in resistance_levels[:5]
        ]
        self.dashboard.update_levels(self.ticker, s_pairs, r_pairs)

        # 4) Regime + pattern (Phase 3 AI bits)
        regime = self.engine.classify_regime(data)
        try:
            pattern_obj = self.engine.analyze_pattern(self.ticker, self.timeframe)
            pattern_name = pattern_obj.pattern_type.value
        except Exception:
            pattern_name = "unknown"

        signal_info = self.engine.analyze_price_action(self.ticker, current_price, self.timeframe)
        signal_label = signal_info.get("signal", "neutral")
        self.dashboard.update_regime(
            self.ticker, regime.name, pattern_name, signal_label
        )

        # 5) Alerts (Phase 4 alerts)
        alerts_fired = self.alerts.check_alerts(
            self.ticker,
            current_price,
            [float(lvl.price) for lvl in support_levels],
            [float(lvl.price) for lvl in resistance_levels],
            atr,
        )

        # 6) Headline
        print(
            f"[live] price={current_price:.2f} "
            f"regime={regime.name} pattern={pattern_name} signal={signal_label} "
            f"alerts_this_cycle={len(alerts_fired)} "
            f"S/R top: {s_pairs[:1]} / {r_pairs[:1]}"
        )

        # 7) Render
        self.dashboard.render()

        # Always save a snapshot PNG. On Mac this is the most reliable way for
        # the user to actually SEE the dashboard - the matplotlib MacOSX backend
        # is flaky about popping a window from a long-running terminal script.
        out_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"{self.ticker}_live.png",
        )
        self.dashboard._fig.savefig(out_path, dpi=120, facecolor="#1a1a2e")

        if self.tick_count == 1:
            # First tick: print a banner showing how to open the snapshot.
            print()
            print("=" * 60)
            print("[live] DASHBOARD SNAPSHOT saved at:")
            print(f"       {out_path}")
            print()
            print("[live] To view it, in a SEPARATE terminal run:")
            print(f"       open {out_path}")
            print()
            print("[live] Preview will pop up. Close + reopen to see updates,")
            print("       or just leave it - we resave it every tick.")
            print("=" * 60)
            print()
        else:
            print(f"[live] snapshot -> {out_path}")

        # On macOS, give the matplotlib event loop a tiny window of time to
        # actually refresh any open GUI window. Cheap, harmless on other OSes.
        if sys.platform == "darwin":
            try:
                plt.pause(0.01)
            except Exception:
                pass

    # -- main loop --------------------------------------------------------

    def run(self) -> None:
        print(
            f"[live] starting live dashboard for {self.ticker} ({self.timeframe}), "
            f"poll every {self.interval:.0f}s. Press Ctrl+C to stop."
        )
        try:
            while not self._stop:
                try:
                    self._tick()
                except Exception as exc:
                    # Never let a transient data-fetch error kill the loop.
                    print(f"[live] tick error: {exc!r}")
                # Sleep in 1s slices so Ctrl+C is responsive even on long intervals.
                slept = 0.0
                while slept < self.interval and not self._stop:
                    time.sleep(min(1.0, self.interval - slept))
                    slept += 1.0
        finally:
            print("\n[live] final stats:")
            print(f"  ticks      : {self.tick_count}")
            print(f"  alerts     : {self.alerts.get_stats()}")
            if _is_interactive():
                plt.ioff()
                # Leave the chart on screen so the user can inspect it.
                plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AMD"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1D"
    try:
        interval = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    except ValueError:
        interval = 30.0

    runner = LiveRunner(ticker.upper(), timeframe, interval)
    runner.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
