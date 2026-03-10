#!/usr/bin/env python3
"""
Test chart selector functionality for distance vision phase.

Verify that:
1. Distance vision starts with chart_info included
2. Chart selector data is properly formatted
3. Chart switching works during distance vision
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_distance_vision_chart_selector():
    """Test chart selector in distance vision phase."""
    print("\n" + "="*70)
    print("TEST: Chart Selector in Distance Vision")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting distance vision test...")
    state = session.start_distance_vision()
    
    print(f"   Phase: {state['phase']}")
    print(f"   Chart: {state['chart']}")
    
    # Verify chart_info exists
    if 'chart_info' not in state:
        print("   ✗ FAILED: chart_info not included in response")
        return False
    
    print("   ✓ SUCCESS: chart_info included")
    
    chart_info = state['chart_info']
    print(f"   Available charts: {chart_info['available_charts']}")
    print(f"   Current index: {chart_info['current_index']}")
    print(f"   Current chart: {chart_info['current_chart']}")
    
    # Verify chart_info structure
    if not isinstance(chart_info['available_charts'], list):
        print("   ✗ FAILED: available_charts is not a list")
        return False
    
    if len(chart_info['available_charts']) == 0:
        print("   ✗ FAILED: available_charts is empty")
        return False
    
    print(f"   ✓ SUCCESS: Found {len(chart_info['available_charts'])} charts")
    
    # Verify current chart matches
    if chart_info['current_chart'] != state['chart']:
        print(f"   ✗ FAILED: Current chart mismatch: {chart_info['current_chart']} vs {state['chart']}")
        return False
    
    print("   ✓ SUCCESS: Current chart matches state")
    
    # Verify initial index is 0
    if chart_info['current_index'] != 0:
        print(f"   ✗ FAILED: Expected initial index 0, got {chart_info['current_index']}")
        return False
    
    print("   ✓ SUCCESS: Initial chart index is 0")
    
    print("\n" + "="*70)
    return True

def test_distance_vision_chart_switching():
    """Test switching charts during distance vision."""
    print("\n" + "="*70)
    print("TEST: Chart Switching in Distance Vision")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting distance vision...")
    state = session.start_distance_vision()
    
    available_charts = state['chart_info']['available_charts']
    print(f"   Available charts: {available_charts}")
    
    if len(available_charts) < 2:
        print("   ⚠️ SKIPPED: Only one chart available, cannot test switching")
        return True
    
    # Switch to chart 1 (if available)
    print(f"\n2. Switching to chart index 1...")
    try:
        state = session.switch_chart(1)
        print(f"   Current chart: {state['chart']}")
        print(f"   Chart info index: {state['chart_info']['current_index']}")
        
        if state['chart_info']['current_index'] != 1:
            print(f"   ✗ FAILED: Expected index 1, got {state['chart_info']['current_index']}")
            return False
        
        if state['chart'] != available_charts[1]:
            print(f"   ✗ FAILED: Expected chart {available_charts[1]}, got {state['chart']}")
            return False
        
        print("   ✓ SUCCESS: Chart switched correctly")
        
    except ValueError as e:
        print(f"   ✗ FAILED: {e}")
        return False
    
    # Switch back to chart 0
    print(f"\n3. Switching back to chart index 0...")
    state = session.switch_chart(0)
    
    if state['chart_info']['current_index'] != 0:
        print(f"   ✗ FAILED: Expected index 0, got {state['chart_info']['current_index']}")
        return False
    
    print("   ✓ SUCCESS: Switched back to first chart")
    
    print("\n" + "="*70)
    return True

def test_distance_vision_chart_persistence():
    """Test that chart selection persists through pinhole test."""
    print("\n" + "="*70)
    print("TEST: Chart Persistence Through Pinhole Test")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting distance vision...")
    state = session.start_distance_vision()
    
    # Patient unable to read (triggers pinhole)
    print("\n2. Patient says 'Unable to read' (pinhole test)...")
    state = session.process_response("Unable to read")
    
    # Verify chart_info still present during pinhole
    if 'chart_info' not in state:
        print("   ✗ FAILED: chart_info missing during pinhole test")
        return False
    
    print("   ✓ SUCCESS: chart_info present during pinhole test")
    print(f"   Current chart: {state['chart']}")
    
    # Verify still in distance vision phase
    if "Distance Vision" not in state['phase']:
        print(f"   ✗ FAILED: Not in distance vision phase: {state['phase']}")
        return False
    
    print("   ✓ SUCCESS: Still in distance vision phase with chart selector")
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success1 = test_distance_vision_chart_selector()
        success2 = test_distance_vision_chart_switching()
        success3 = test_distance_vision_chart_persistence()
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Chart Selector Present:     {'✅ PASSED' if success1 else '❌ FAILED'}")
        print(f"Chart Switching Works:      {'✅ PASSED' if success2 else '❌ FAILED'}")
        print(f"Persistence Through Test:   {'✅ PASSED' if success3 else '❌ FAILED'}")
        
        if success1 and success2 and success3:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35)
            print("\nChart selector for distance vision verified:")
            print("✓ Chart info included in distance vision phase")
            print("✓ Chart switching works correctly")
            print("✓ Chart selector persists through pinhole test")
            print()
        else:
            print("\n❌ SOME TESTS FAILED\n")
        
        sys.exit(0 if (success1 and success2 and success3) else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
