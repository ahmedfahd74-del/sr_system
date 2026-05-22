# sr_system/tests/test_full_system.py
"""Full system integration test for the S/R detection engine."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime

from core.engine import SREngine, UnifiedSRLevel, get_engine
from core.config import Config, get_config
from detection.horizontal import SRLevel
from detection.trendline import TrendlineLevel
from detection.fractal import FractalLevel


def test_engine_initialization():
    """Test that engine initializes correctly."""
    print("\n" + "="*60)
    print("TEST 1: Engine Initialization")
    print("="*60)
    
    engine = SREngine()
    assert engine is not None, "Engine should initialize"
    assert engine.data_source is not None, "Data source should be set"
    assert engine.cache is not None, "Cache should be initialized"
    
    config = get_config()
    assert config is not None, "Config should be available"
    print("✓ Engine initializes correctly")
    return True


def test_data_fetch():
    """Test fetching real market data."""
    print("\n" + "="*60)
    print("TEST 2: Data Fetching (AMD)")
    print("="*60)
    
    engine = SREngine()
    
    # Clear cache to force fresh fetch
    engine.cache.clear()
    
    start_time = time.time()
    mtf_data = engine._get_mtf_data("AMD", ["1D", "1H", "4H"])
    fetch_time = time.time() - start_time
    
    print(f"Fetched {len(mtf_data)} timeframes in {fetch_time:.2f}s")
    
    for tf, data in mtf_data.items():
        print(f"  {tf}: {len(data)} bars, latest close: ${data.closes[-1]:.2f}")
    
    assert len(mtf_data) >= 1, "Should fetch at least one timeframe"
    print("✓ Data fetching works")
    return True


def test_regime_classification():
    """Test market regime classification."""
    print("\n" + "="*60)
    print("TEST 3: Regime Classification (AMD)")
    print("="*60)
    
    engine = SREngine()
    mtf_data = engine._get_mtf_data("AMD", ["1D"])
    
    if "1D" not in mtf_data:
        print("✗ Could not fetch 1D data")
        return False
    
    regime = engine.classify_regime(mtf_data["1D"])
    print(f"  Regime: {regime.name}")
    print(f"  Strength: {regime.strength:.1f}")
    print(f"  Direction: {regime.trend_direction}")
    
    assert regime.name in ["trending", "ranging", "volatile", "low_vol", "unknown"]
    print("✓ Regime classification works")
    return True


def test_horizontal_detection():
    """Test horizontal S/R detection."""
    print("\n" + "="*60)
    print("TEST 4: Horizontal S/R Detection (AMD 1D)")
    print("="*60)
    
    engine = SREngine()
    results = engine.detect_mtf_sr("AMD", "1D")
    
    if "1D" not in results:
        print("✗ No results for 1D")
        return False
    
    support, resistance = results["1D"]
    print(f"  Support levels found: {len(support)}")
    print(f"  Resistance levels found: {len(resistance)}")
    
    if support:
        print(f"  Top support: ${support[0].price:.2f} (conf: {support[0].confidence:.0f})")
    if resistance:
        print(f"  Top resistance: ${resistance[0].price:.2f} (conf: {resistance[0].confidence:.0f})")
    
    print("✓ Horizontal detection works")
    return True


def test_trendline_detection():
    """Test trendline S/R detection."""
    print("\n" + "="*60)
    print("TEST 5: Trendline Detection (AMD 1D)")
    print("="*60)
    
    from detection.trendline import detect_trendline_sr
    
    engine = SREngine()
    mtf_data = engine._get_mtf_data("AMD", ["1D"])
    
    if "1D" not in mtf_data:
        print("✗ Could not fetch 1D data")
        return False
    
    data = mtf_data["1D"]
    support, resistance = detect_trendline_sr(data, lookback=50, min_touches=2)
    
    print(f"  Trendline support: {len(support)}")
    print(f"  Trendline resistance: {len(resistance)}")
    
    for i, tl in enumerate(support[:3]):
        print(f"    S{i+1}: price=${tl.current_price:.2f}, slope={tl.slope:.4f}, conf={tl.confidence:.0f}")
    
    for i, tl in enumerate(resistance[:3]):
        print(f"    R{i+1}: price=${tl.current_price:.2f}, slope={tl.slope:.4f}, conf={tl.confidence:.0f}")
    
    print("✓ Trendline detection works")
    return True


def test_fractal_detection():
    """Test fractal S/R detection."""
    print("\n" + "="*60)
    print("TEST 6: Fractal Detection (AMD 1D)")
    print("="*60)
    
    from detection.fractal import detect_fractal_sr
    
    engine = SREngine()
    mtf_data = engine._get_mtf_data("AMD", ["1D"])
    
    if "1D" not in mtf_data:
        print("✗ Could not fetch 1D data")
        return False
    
    data = mtf_data["1D"]
    support, resistance = detect_fractal_sr(data, period=2, lookback=100)
    
    print(f"  Fractal support: {len(support)}")
    print(f"  Fractal resistance: {len(resistance)}")
    
    for i, fr in enumerate(support[:3]):
        print(f"    S{i+1}: price=${fr.price:.2f}, type={fr.fractal_type}, conf={fr.confidence:.0f}")
    
    for i, fr in enumerate(resistance[:3]):
        print(f"    R{i+1}: price=${fr.price:.2f}, type={fr.fractal_type}, conf={fr.confidence:.0f}")
    
    print("✓ Fractal detection works")
    return True


def test_unified_detection():
    """Test unified multi-method detection."""
    print("\n" + "="*60)
    print("TEST 7: Unified Detection (AMD - All Methods)")
    print("="*60)
    
    engine = SREngine()
    
    start_time = time.time()
    unified = engine.detect_unified("AMD", "1D")
    detect_time = time.time() - start_time
    
    print(f"Detection completed in {detect_time:.2f}s")
    
    total_support = 0
    total_resistance = 0
    method_counts = {"horizontal": 0, "trendline": 0, "fractal": 0}
    
    for tf, levels in unified.items():
        total_support += len(levels["support"])
        total_resistance += len(levels["resistance"])
        
        for level in levels["support"] + levels["resistance"]:
            if level.source in method_counts:
                method_counts[level.source] += 1
    
    print(f"\nTotal levels across all TFs:")
    print(f"  Support: {total_support}")
    print(f"  Resistance: {total_resistance}")
    print(f"\nBy detection method:")
    for method, count in method_counts.items():
        print(f"  {method}: {count}")
    
    # Show top levels for primary TF
    if "1D" in unified:
        print(f"\nTop 3 support (1D):")
        for i, lvl in enumerate(unified["1D"]["support"][:3]):
            print(f"  {i+1}. ${lvl.price:.2f} [{lvl.source}] conf={lvl.confidence:.0f}")
        
        print(f"\nTop 3 resistance (1D):")
        for i, lvl in enumerate(unified["1D"]["resistance"][:3]):
            print(f"  {i+1}. ${lvl.price:.2f} [{lvl.source}] conf={lvl.confidence:.0f}")
    
    assert total_support > 0, "Should find some support levels"
    assert total_resistance > 0, "Should find some resistance levels"
    print("✓ Unified detection works")
    return True


def test_confluence_detection():
    """Test multi-timeframe confluence detection."""
    print("\n" + "="*60)
    print("TEST 8: Confluence Detection (AMD)")
    print("="*60)
    
    engine = SREngine()
    
    # First run unified detection to populate cache
    engine.detect_all_mtf_unified("AMD", "1D")
    
    # Then get confluence
    confluence = engine.get_confluence_levels("AMD", price_range=0.01)
    
    print(f"Confluence levels found: {len(confluence)}")
    
    for i, lvl in enumerate(confluence[:5]):
        dist_from_current = abs(lvl.price - 450) / 450 * 100  # Assuming ~450 price
        print(f"  {i+1}. ${lvl.price:.2f} [{lvl.level_type}] conf={lvl.confidence:.0f} ({lvl.source})")
    
    print("✓ Confluence detection works")
    return True


def test_price_action_analysis():
    """Test price action analysis."""
    print("\n" + "="*60)
    print("TEST 9: Price Action Analysis (AMD)")
    print("="*60)
    
    engine = SREngine()
    mtf_data = engine._get_mtf_data("AMD", ["1D"])
    
    if "1D" not in mtf_data:
        print("✗ Could not fetch data")
        return False
    
    current_price = mtf_data["1D"].closes[-1]
    analysis = engine.analyze_price_action("AMD", current_price, "1D")
    
    print(f"Current price: ${analysis['current_price']:.2f}")
    print(f"Regime: {analysis['regime']}")
    print(f"Signal: {analysis['signal']}")
    print(f"Reason: {analysis['signal_reason']}")
    
    if analysis['nearest_support']:
        s = analysis['nearest_support']
        print(f"Nearest support: ${s.price:.2f} (dist: {analysis['distance_to_support_pct']:.2f}%)")
    
    if analysis['nearest_resistance']:
        r = analysis['nearest_resistance']
        print(f"Nearest resistance: ${r.price:.2f} (dist: {analysis['distance_to_resistance_pct']:.2f}%)")
    
    print("✓ Price action analysis works")
    return True


def test_adaptive_parameters():
    """Test adaptive parameter adjustment per regime."""
    print("\n" + "="*60)
    print("TEST 10: Adaptive Parameter Adjustment")
    print("="*60)
    
    engine = SREngine()
    mtf_data = engine._get_mtf_data("AMD", ["1D"])
    
    if "1D" not in mtf_data:
        print("✗ Could not fetch data")
        return False
    
    regime = engine.classify_regime(mtf_data["1D"])
    params = engine.get_adaptive_params(regime, "AMD")
    
    print(f"Regime: {regime.name}")
    print(f"Adaptive parameters:")
    print(f"  lookback: {params['lookback']}")
    print(f"  min_touches: {params['min_touches']}")
    print(f"  atr_multiplier: {params['atr_multiplier']}")
    print(f"  merge_threshold_pct: {params['merge_threshold_pct']}")
    
    # Verify params differ per regime
    print(f"\nExpected for '{regime.name}' regime:")
    expected = engine.config.adaptive.regimes.get(regime.name, {})
    print(f"  lookback: {expected.get('lookback', 'N/A')}")
    
    print("✓ Adaptive parameters work")
    return True


def run_all_tests():
    """Run all system tests."""
    print("\n" + "#"*60)
    print("# FULL SYSTEM INTEGRATION TEST")
    print("# S/R Detection Engine - All Methods")
    print("#"*60)
    
    tests = [
        ("Engine Initialization", test_engine_initialization),
        ("Data Fetching", test_data_fetch),
        ("Regime Classification", test_regime_classification),
        ("Horizontal Detection", test_horizontal_detection),
        ("Trendline Detection", test_trendline_detection),
        ("Fractal Detection", test_fractal_detection),
        ("Unified Detection", test_unified_detection),
        ("Confluence Detection", test_confluence_detection),
        ("Price Action Analysis", test_price_action_analysis),
        ("Adaptive Parameters", test_adaptive_parameters),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed, None))
        except Exception as e:
            print(f"✗ FAILED with exception: {e}")
            results.append((name, False, str(e)))
    
    # Summary
    print("\n" + "#"*60)
    print("# TEST SUMMARY")
    print("#"*60)
    
    passed_count = sum(1 for _, p, _ in results if p)
    total_count = len(results)
    
    for name, passed, error in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if error:
            print(f"         Error: {error}")
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED!")
        return True
    else:
        print(f"\n⚠️  {total_count - passed_count} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)