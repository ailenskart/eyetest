#!/usr/bin/env python3
"""
Test to verify that power updates are included in the response when duochrome reversal occurs.

When a reversal happens (e.g., Green -> Red), the power should be updated and included
in the response so the frontend can display the correct value.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_duochrome_right_reversal_power():
    """Test that power is included in response when duochrome right has reversal."""
    print("\n" + "="*70)
    print("TEST: Duochrome Right Reversal - Power Update in Response")
    print("="*70)
    
    session = InteractiveSession()
    
    # Navigate to Duochrome Right phase
    print("\n1. Setting up Duochrome Right phase...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    # Move through charts to 20/20
    for _ in range(5):
        state = session.process_response("Able to read")
    state = session.process_response("Able to read")  # Trigger JCC Axis
    
    # JCC Axis
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # JCC Power
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # Now in Duochrome Right
    print(f"   Phase: {state['phase']}")
    initial_sph = session.current_row.r_sph
    print(f"   Initial SPH: {initial_sph:.2f}D")
    
    # First choice: Green (increase SPH)
    print("\n2. First choice: Green (SPH should increase by +0.25D)...")
    state = session.process_response("Green")
    sph_after_green = session.current_row.r_sph
    print(f"   SPH after Green: {sph_after_green:.2f}D")
    
    if abs(sph_after_green - (initial_sph + 0.25)) < 0.01:
        print("   ✓ SPH increased correctly")
    else:
        print(f"   ✗ FAILED: Expected {initial_sph + 0.25:.2f}, got {sph_after_green:.2f}")
        return False
    
    # Check power is in response (no reversal yet)
    if 'power' in state:
        print("   ✓ Power included in response (no reversal)")
    else:
        print("   ✗ FAILED: Power should be in response")
        return False
    
    # Second choice: Red (decrease SPH) - This triggers reversal
    print("\n3. Second choice: Red (reversal - SPH should decrease by -0.25D)...")
    state = session.process_response("Red")
    sph_after_red = session.current_row.r_sph
    print(f"   SPH after Red: {sph_after_red:.2f}D")
    print(f"   Phase after reversal: {state['phase']}")
    
    # Verify SPH decreased
    if abs(sph_after_red - sph_after_green + 0.25) < 0.01:
        print("   ✓ SPH decreased correctly")
    else:
        print(f"   ✗ FAILED: Expected {sph_after_green - 0.25:.2f}, got {sph_after_red:.2f}")
        return False
    
    # CRITICAL: Check that power is in response after reversal
    if 'power' in state:
        print("   ✓ SUCCESS: Power included in response after reversal")
        print(f"   ✓ Frontend will display: R SPH={state['power']['right']['sph']:.2f}D")
    else:
        print("   ✗ FAILED: Power missing from response after reversal")
        print("   ✗ Frontend will not update power display!")
        return False
    
    # Verify the power value in response matches current_row
    if abs(state['power']['right']['sph'] - sph_after_red) < 0.01:
        print("   ✓ Power value in response matches internal state")
    else:
        print(f"   ✗ FAILED: Power mismatch - response={state['power']['right']['sph']:.2f}, internal={sph_after_red:.2f}")
        return False
    
    print("\n" + "="*70)
    return True

def test_duochrome_left_reversal_power():
    """Test that power is included in response when duochrome left has reversal."""
    print("\n" + "="*70)
    print("TEST: Duochrome Left Reversal - Power Update in Response")
    print("="*70)
    
    session = InteractiveSession()
    
    # Navigate to Duochrome Left phase (need to complete right eye first)
    print("\n1. Setting up Duochrome Left phase...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    # Right eye refraction
    for _ in range(5):
        state = session.process_response("Able to read")
    state = session.process_response("Able to read")
    
    # JCC Axis Right
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # JCC Power Right
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # Duochrome Right - complete quickly
    state = session.process_response("Both Same")
    
    # Left eye refraction
    for _ in range(6):
        state = session.process_response("Able to read")
    
    # JCC Axis Left
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # JCC Power Left
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # Now in Duochrome Left
    print(f"   Phase: {state['phase']}")
    initial_sph = session.current_row.l_sph
    print(f"   Initial SPH: {initial_sph:.2f}D")
    
    # First choice: Red (decrease SPH)
    print("\n2. First choice: Red (SPH should decrease by -0.25D)...")
    state = session.process_response("Red")
    sph_after_red = session.current_row.l_sph
    print(f"   SPH after Red: {sph_after_red:.2f}D")
    
    if abs(sph_after_red - (initial_sph - 0.25)) < 0.01:
        print("   ✓ SPH decreased correctly")
    else:
        print(f"   ✗ FAILED: Expected {initial_sph - 0.25:.2f}, got {sph_after_red:.2f}")
        return False
    
    # Second choice: Green (increase SPH) - This triggers reversal
    print("\n3. Second choice: Green (reversal - SPH should increase by +0.25D)...")
    state = session.process_response("Green")
    sph_after_green = session.current_row.l_sph
    print(f"   SPH after Green: {sph_after_green:.2f}D")
    print(f"   Phase after reversal: {state['phase']}")
    
    # Verify SPH increased
    if abs(sph_after_green - sph_after_red - 0.25) < 0.01:
        print("   ✓ SPH increased correctly")
    else:
        print(f"   ✗ FAILED: Expected {sph_after_red + 0.25:.2f}, got {sph_after_green:.2f}")
        return False
    
    # CRITICAL: Check that power is in response after reversal
    if 'power' in state:
        print("   ✓ SUCCESS: Power included in response after reversal")
        print(f"   ✓ Frontend will display: L SPH={state['power']['left']['sph']:.2f}D")
    else:
        print("   ✗ FAILED: Power missing from response after reversal")
        print("   ✗ Frontend will not update power display!")
        return False
    
    # Verify the power value in response matches current_row
    if abs(state['power']['left']['sph'] - sph_after_green) < 0.01:
        print("   ✓ Power value in response matches internal state")
    else:
        print(f"   ✗ FAILED: Power mismatch - response={state['power']['left']['sph']:.2f}, internal={sph_after_green:.2f}")
        return False
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success_right = test_duochrome_right_reversal_power()
        success_left = test_duochrome_left_reversal_power()
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Right Eye Duochrome Reversal: {'✅ PASSED' if success_right else '❌ FAILED'}")
        print(f"Left Eye Duochrome Reversal:  {'✅ PASSED' if success_left else '❌ FAILED'}")
        
        if success_right and success_left:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35)
            print("\nDuochrome reversal power updates verified:")
            print("✓ Power is included in response after reversal")
            print("✓ Frontend will display updated power values")
            print("✓ Works for both right and left eye")
            print()
        else:
            print("\n❌ SOME TESTS FAILED\n")
        
        sys.exit(0 if (success_right and success_left) else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
