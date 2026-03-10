#!/usr/bin/env python3
"""
Test that pinhole maintains the current chart selection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_pinhole_maintains_chart():
    """Test pinhole keeps current chart (not E-chart)."""
    print("\n" + "="*70)
    print("TEST: Pinhole Maintains Current Chart Selection")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start distance vision (E-chart)
    print("\n1. Starting distance vision with E-chart...")
    state = session.start_distance_vision()
    print(f"   Current chart: {state['chart']}")
    assert state['chart'] == "echart_400"
    
    # Switch to a Snellen chart
    print("\n2. Switching to Snellen 20/70-20/60...")
    state = session.switch_chart(3)  # snellen_chart_70_60_50
    print(f"   Current chart: {state['chart']}")
    assert state['chart'] == "snellen_chart_70_60_50"
    
    # Patient unable to read (triggers pinhole)
    print("\n3. Patient says 'Unable to read' (pinhole test)...")
    state = session.process_response("Unable to read")
    
    print(f"   Current chart after pinhole: {state['chart']}")
    print(f"   Question: {state['question']}")
    
    # Verify chart stayed as Snellen (not reset to E-chart)
    if state['chart'] != "snellen_chart_70_60_50":
        print(f"   ✗ FAILED: Chart changed to {state['chart']}, expected snellen_chart_70_60_50")
        return False
    
    print("   ✓ SUCCESS: Chart maintained (not reset to E-chart)")
    
    # Verify question is generic (not E-chart specific)
    if "E clearly" in state['question']:
        print(f"   ⚠️ WARNING: Question still mentions E-chart")
    else:
        print("   ✓ SUCCESS: Question is generic")
    
    print("\n" + "="*70)
    return True

def test_pinhole_from_echart():
    """Test pinhole from E-chart still works."""
    print("\n" + "="*70)
    print("TEST: Pinhole from E-chart (Original Behavior)")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start distance vision (E-chart)
    print("\n1. Starting distance vision with E-chart...")
    state = session.start_distance_vision()
    print(f"   Current chart: {state['chart']}")
    
    # Patient unable to read (triggers pinhole)
    print("\n2. Patient says 'Unable to read' (pinhole test)...")
    state = session.process_response("Unable to read")
    
    print(f"   Current chart after pinhole: {state['chart']}")
    
    # Verify chart stayed as E-chart
    if state['chart'] != "echart_400":
        print(f"   ✗ FAILED: Chart changed to {state['chart']}, expected echart_400")
        return False
    
    print("   ✓ SUCCESS: E-chart maintained")
    
    print("\n" + "="*70)
    return True

def test_pinhole_multiple_switches():
    """Test pinhole after multiple chart switches."""
    print("\n" + "="*70)
    print("TEST: Pinhole After Multiple Chart Switches")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start and switch through multiple charts
    print("\n1. Starting and switching through charts...")
    state = session.start_distance_vision()
    print(f"   Started with: {state['chart']}")
    
    state = session.switch_chart(2)  # snellen_chart_100_80
    print(f"   Switched to: {state['chart']}")
    
    state = session.switch_chart(5)  # snellen_chart_25_20_15
    print(f"   Switched to: {state['chart']}")
    
    state = session.switch_chart(1)  # snellen_chart_200_150
    print(f"   Switched to: {state['chart']}")
    
    # Patient unable to read (triggers pinhole)
    print("\n2. Patient says 'Unable to read' (pinhole test)...")
    state = session.process_response("Unable to read")
    
    print(f"   Current chart after pinhole: {state['chart']}")
    
    # Verify chart stayed as last selected
    if state['chart'] != "snellen_chart_200_150":
        print(f"   ✗ FAILED: Chart changed to {state['chart']}, expected snellen_chart_200_150")
        return False
    
    print("   ✓ SUCCESS: Last selected chart maintained")
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success1 = test_pinhole_maintains_chart()
        success2 = test_pinhole_from_echart()
        success3 = test_pinhole_multiple_switches()
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Pinhole Maintains Chart:       {'✅ PASSED' if success1 else '❌ FAILED'}")
        print(f"Pinhole from E-chart:          {'✅ PASSED' if success2 else '❌ FAILED'}")
        print(f"Pinhole After Switches:        {'✅ PASSED' if success3 else '❌ FAILED'}")
        
        if success1 and success2 and success3:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35)
            print("\nPinhole chart maintenance verified:")
            print("✓ Pinhole keeps current chart (doesn't reset)")
            print("✓ Works from E-chart")
            print("✓ Works from any Snellen chart")
            print("✓ Maintains chart after multiple switches")
            print()
        else:
            print("\n❌ SOME TESTS FAILED\n")
        
        sys.exit(0 if (success1 and success2 and success3) else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
