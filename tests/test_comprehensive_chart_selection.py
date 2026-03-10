#!/usr/bin/env python3
"""
Test comprehensive chart selection in distance vision with all available charts.

Verify that:
1. Distance vision shows all charts (E-chart + Snellen charts)
2. Can switch between E-chart and Snellen charts
3. Can switch between different Snellen charts
4. Chart selection persists correctly
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_all_charts_available():
    """Test that all charts are available in distance vision."""
    print("\n" + "="*70)
    print("TEST: All Charts Available in Distance Vision")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting distance vision test...")
    state = session.start_distance_vision()
    
    chart_info = state['chart_info']
    available_charts = chart_info['available_charts']
    
    print(f"   Available charts: {len(available_charts)}")
    for i, chart in enumerate(available_charts):
        print(f"     {i}. {chart}")
    
    # Verify we have E-chart + Snellen charts
    expected_charts = [
        "echart_400",
        "snellen_chart_200_150",
        "snellen_chart_100_80",
        "snellen_chart_70_60_50",
        "snellen_chart_40_30_25",
        "snellen_chart_25_20_15",
        "snellen_chart_20_20_20",
        "snellen_chart_20_15_10",
    ]
    
    if available_charts != expected_charts:
        print(f"   ✗ FAILED: Expected {len(expected_charts)} charts, got {len(available_charts)}")
        print(f"   Expected: {expected_charts}")
        print(f"   Got: {available_charts}")
        return False
    
    print(f"   ✓ SUCCESS: All {len(expected_charts)} charts available")
    print(f"   ✓ SUCCESS: Includes 1 E-chart + 7 Snellen charts")
    
    print("\n" + "="*70)
    return True

def test_switch_to_snellen():
    """Test switching from E-chart to Snellen chart."""
    print("\n" + "="*70)
    print("TEST: Switch from E-chart to Snellen Chart")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start with E-chart
    print("\n1. Starting distance vision (E-chart)...")
    state = session.start_distance_vision()
    print(f"   Initial chart: {state['chart']}")
    
    if state['chart'] != "echart_400":
        print(f"   ✗ FAILED: Expected echart_400, got {state['chart']}")
        return False
    
    print("   ✓ SUCCESS: Started with E-chart")
    
    # Switch to first Snellen chart (index 1)
    print("\n2. Switching to Snellen Chart 20/200-20/150...")
    state = session.switch_chart(1)
    
    print(f"   Current chart: {state['chart']}")
    print(f"   Current index: {state['chart_info']['current_index']}")
    
    if state['chart'] != "snellen_chart_200_150":
        print(f"   ✗ FAILED: Expected snellen_chart_200_150, got {state['chart']}")
        return False
    
    if state['chart_info']['current_index'] != 1:
        print(f"   ✗ FAILED: Expected index 1, got {state['chart_info']['current_index']}")
        return False
    
    print("   ✓ SUCCESS: Switched to Snellen chart")
    
    print("\n" + "="*70)
    return True

def test_switch_between_snellen_charts():
    """Test switching between different Snellen charts."""
    print("\n" + "="*70)
    print("TEST: Switch Between Snellen Charts")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start and switch to a Snellen chart
    print("\n1. Starting and switching to Snellen 20/100-20/80...")
    state = session.start_distance_vision()
    state = session.switch_chart(2)  # snellen_chart_100_80
    
    print(f"   Current chart: {state['chart']}")
    
    if state['chart'] != "snellen_chart_100_80":
        print(f"   ✗ FAILED: Expected snellen_chart_100_80")
        return False
    
    print("   ✓ SUCCESS: At Snellen 20/100-20/80")
    
    # Switch to another Snellen chart
    print("\n2. Switching to Snellen 20/20-20/20...")
    state = session.switch_chart(6)  # snellen_chart_20_20_20
    
    print(f"   Current chart: {state['chart']}")
    
    if state['chart'] != "snellen_chart_20_20_20":
        print(f"   ✗ FAILED: Expected snellen_chart_20_20_20")
        return False
    
    print("   ✓ SUCCESS: Switched to Snellen 20/20-20/20")
    
    # Switch to last Snellen chart
    print("\n3. Switching to Snellen 20/20-20/15...")
    state = session.switch_chart(7)  # snellen_chart_20_15_10
    
    print(f"   Current chart: {state['chart']}")
    
    if state['chart'] != "snellen_chart_20_15_10":
        print(f"   ✗ FAILED: Expected snellen_chart_20_15_10")
        return False
    
    print("   ✓ SUCCESS: Switched to Snellen 20/20-20/15")
    
    # Switch back to E-chart
    print("\n4. Switching back to E-chart...")
    state = session.switch_chart(0)  # echart_400
    
    print(f"   Current chart: {state['chart']}")
    
    if state['chart'] != "echart_400":
        print(f"   ✗ FAILED: Expected echart_400")
        return False
    
    print("   ✓ SUCCESS: Switched back to E-chart")
    
    print("\n" + "="*70)
    return True

def test_chart_selection_with_pinhole():
    """Test chart selection works with pinhole test."""
    print("\n" + "="*70)
    print("TEST: Chart Selection with Pinhole Test")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start and switch to a Snellen chart
    print("\n1. Starting with E-chart, switching to Snellen...")
    state = session.start_distance_vision()
    state = session.switch_chart(3)  # snellen_chart_40_30_25
    
    print(f"   Current chart: {state['chart']}")
    
    # Patient unable to read (triggers pinhole)
    print("\n2. Patient says 'Unable to read' (pinhole test)...")
    state = session.process_response("Unable to read")
    
    print(f"   Current chart: {state['chart']}")
    print(f"   Chart info present: {'chart_info' in state}")
    
    # Verify chart selection still available
    if 'chart_info' not in state:
        print("   ✗ FAILED: chart_info missing during pinhole")
        return False
    
    print("   ✓ SUCCESS: Chart info still present during pinhole")
    
    # Verify we can still switch charts during pinhole
    print("\n3. Switching to different chart during pinhole...")
    state = session.switch_chart(1)  # snellen_chart_200_150
    
    print(f"   Current chart: {state['chart']}")
    
    if state['chart'] != "snellen_chart_200_150":
        print("   ✗ FAILED: Chart switching didn't work during pinhole")
        return False
    
    print("   ✓ SUCCESS: Can switch charts during pinhole test")
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success1 = test_all_charts_available()
        success2 = test_switch_to_snellen()
        success3 = test_switch_between_snellen_charts()
        success4 = test_chart_selection_with_pinhole()
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"All Charts Available:       {'✅ PASSED' if success1 else '❌ FAILED'}")
        print(f"Switch to Snellen:          {'✅ PASSED' if success2 else '❌ FAILED'}")
        print(f"Switch Between Snellen:     {'✅ PASSED' if success3 else '❌ FAILED'}")
        print(f"Chart Selection w/ Pinhole: {'✅ PASSED' if success4 else '❌ FAILED'}")
        
        if success1 and success2 and success3 and success4:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35)
            print("\nComprehensive chart selection verified:")
            print("✓ All 8 charts (1 E-chart + 7 Snellen) available")
            print("✓ Can switch from E-chart to Snellen charts")
            print("✓ Can switch between different Snellen charts")
            print("✓ Can switch back to E-chart")
            print("✓ Chart selection works during pinhole test")
            print()
        else:
            print("\n❌ SOME TESTS FAILED\n")
        
        sys.exit(0 if (success1 and success2 and success3 and success4) else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
