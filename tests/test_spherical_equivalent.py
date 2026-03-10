#!/usr/bin/env python3
"""
Test to verify spherical equivalent compensation logic.
When cylinder decreases by -0.50D (two steps of -0.25D), sphere increases by +0.25D.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_spherical_equivalent_right_eye():
    """Test spherical equivalent compensation for right eye."""
    print("\n" + "="*70)
    print("TEST: Spherical Equivalent Compensation - Right Eye")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test and move to JCC Power Right
    print("\n1. Starting test and moving to JCC Power Right...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    # Move through charts to reach 20/20
    for _ in range(5):
        state = session.process_response("Able to read")
    
    # Move through JCC Axis to JCC Power
    state = session.process_response("AUTO_FLIP")  # JCC Axis Flip1 -> Flip2
    state = session.process_response("Both Same")  # Exit JCC Axis, enter JCC Power
    
    # Now at JCC Power Right - need to do AUTO_FLIP to get to Flip2
    print(f"   Phase: {state['phase']}")
    initial_sph = session.current_row.r_sph
    initial_cyl = session.current_row.r_cyl
    print(f"   Initial: SPH={initial_sph:.2f}D, CYL={initial_cyl:.2f}D")
    
    # First decrease: CYL -0.25D (no SPH change yet)
    print("\n2. First cylinder decrease (Flip 2 is better)...")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Flip 2 was better (RAM Power - decrease cylinder by 0.25D)")
    
    sph_after_1 = session.current_row.r_sph
    cyl_after_1 = session.current_row.r_cyl
    print(f"   After 1st decrease: SPH={sph_after_1:.2f}D, CYL={cyl_after_1:.2f}D")
    print(f"   Decrease count: {session.r_cyl_decrease_count}")
    
    if abs(cyl_after_1 - (initial_cyl - 0.25)) < 0.01:
        print("   ✓ Cylinder decreased by -0.25D")
    else:
        print(f"   ✗ FAILED: Expected CYL {initial_cyl - 0.25:.2f}, got {cyl_after_1:.2f}")
        return False
    
    if abs(sph_after_1 - initial_sph) < 0.01:
        print("   ✓ Sphere unchanged (as expected, waiting for 2nd decrease)")
    else:
        print(f"   ✗ FAILED: Sphere should not change yet")
        return False
    
    # Second decrease: CYL -0.25D (SPH should increase by +0.25D)
    print("\n3. Second cylinder decrease (Flip 2 is better again)...")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Flip 2 was better (RAM Power - decrease cylinder by -0.25D)")
    
    sph_after_2 = session.current_row.r_sph
    cyl_after_2 = session.current_row.r_cyl
    print(f"   After 2nd decrease: SPH={sph_after_2:.2f}D, CYL={cyl_after_2:.2f}D")
    print(f"   Decrease count: {session.r_cyl_decrease_count}")
    
    # Verify cylinder decreased by another -0.25D
    if abs(cyl_after_2 - (cyl_after_1 - 0.25)) < 0.01:
        print("   ✓ Cylinder decreased by another -0.25D (total -0.50D)")
    else:
        print(f"   ✗ FAILED: Expected CYL {cyl_after_1 - 0.25:.2f}, got {cyl_after_2:.2f}")
        return False
    
    # Verify sphere increased by +0.25D (spherical equivalent compensation)
    expected_sph = initial_sph + 0.25
    if abs(sph_after_2 - expected_sph) < 0.01:
        print(f"   ✓ SUCCESS: Sphere increased by +0.25D (spherical equivalent compensation)")
        print(f"   ✓ Total change: CYL -0.50D, SPH +0.25D")
    else:
        print(f"   ✗ FAILED: Expected SPH {expected_sph:.2f}, got {sph_after_2:.2f}")
        return False
    
    # Verify counter was reset
    if session.r_cyl_decrease_count == 0:
        print("   ✓ Decrease counter reset after compensation")
    else:
        print(f"   ✗ FAILED: Counter should be reset, but is {session.r_cyl_decrease_count}")
        return False
    
    print("\n" + "="*70)
    return True

def test_spherical_equivalent_left_eye():
    """Test spherical equivalent compensation for left eye."""
    print("\n" + "="*70)
    print("TEST: Spherical Equivalent Compensation - Left Eye")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test and move through to left eye JCC Power
    print("\n1. Starting test and moving to JCC Power Left...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    # Move through right eye quickly
    for _ in range(6):
        state = session.process_response("Able to read")
    
    # Skip right eye JCC phases
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    state = session.process_response("Both Same")
    
    # Move through left eye charts
    for _ in range(6):
        state = session.process_response("Able to read")
    
    # Skip left eye JCC Axis
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    
    # Now at JCC Power Left
    print(f"   Phase: {state['phase']}")
    initial_sph = session.current_row.l_sph
    initial_cyl = session.current_row.l_cyl
    print(f"   Initial: SPH={initial_sph:.2f}D, CYL={initial_cyl:.2f}D")
    
    # First decrease
    print("\n2. First cylinder decrease...")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Flip 2 was better (RAM Power - decrease cylinder by -0.25D)")
    
    sph_after_1 = session.current_row.l_sph
    cyl_after_1 = session.current_row.l_cyl
    print(f"   After 1st decrease: SPH={sph_after_1:.2f}D, CYL={cyl_after_1:.2f}D")
    
    # Second decrease
    print("\n3. Second cylinder decrease...")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Flip 2 was better (RAM Power - decrease cylinder by 0.25D)")
    
    sph_after_2 = session.current_row.l_sph
    cyl_after_2 = session.current_row.l_cyl
    print(f"   After 2nd decrease: SPH={sph_after_2:.2f}D, CYL={cyl_after_2:.2f}D")
    
    # Verify spherical equivalent compensation
    expected_sph = initial_sph + 0.25
    if abs(sph_after_2 - expected_sph) < 0.01:
        print(f"   ✓ SUCCESS: Sphere increased by +0.25D (spherical equivalent compensation)")
        print(f"   ✓ Total change: CYL -0.50D, SPH +0.25D")
    else:
        print(f"   ✗ FAILED: Expected SPH {expected_sph:.2f}, got {sph_after_2:.2f}")
        return False
    
    print("\n" + "="*70)
    return True

def test_counter_reset_on_increase():
    """Test that counter resets when cylinder increases."""
    print("\n" + "="*70)
    print("TEST: Counter Reset on Cylinder Increase")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test and move to JCC Power Right
    print("\n1. Moving to JCC Power Right...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    for _ in range(5):
        state = session.process_response("Able to read")
    
    state = session.process_response("AUTO_FLIP")  # JCC Axis Flip1 -> Flip2
    state = session.process_response("Both Same")  # Exit JCC Axis, enter JCC Power
    
    print(f"   Phase: {state['phase']}")
    
    # First decrease
    print("\n2. First cylinder decrease...")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Flip 2 was better (RAM Power - decrease cylinder by 0.25D)")
    print(f"   Decrease count: {session.r_cyl_decrease_count}")
    
    if session.r_cyl_decrease_count == 1:
        print("   ✓ Counter incremented to 1")
    else:
        print(f"   ✗ FAILED: Expected count 1, got {session.r_cyl_decrease_count}")
        return False
    
    # Now increase (should reset counter)
    print("\n3. Cylinder increase (Flip 1 is better)...")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Flip 1 was better (GAP Power - increase cylinder by +0.25D)")
    print(f"   Decrease count: {session.r_cyl_decrease_count}")
    
    if session.r_cyl_decrease_count == 0:
        print("   ✓ SUCCESS: Counter reset to 0 after increase")
    else:
        print(f"   ✗ FAILED: Counter should be 0, got {session.r_cyl_decrease_count}")
        return False
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success = True
        success = test_spherical_equivalent_right_eye() and success
        success = test_spherical_equivalent_left_eye() and success
        success = test_counter_reset_on_increase() and success
        
        if success:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35 + "\n")
            print("Key behaviors verified:")
            print("✓ After 2 consecutive CYL decreases (-0.50D), SPH increases by +0.25D")
            print("✓ Works correctly for both right and left eye")
            print("✓ Counter resets after compensation is applied")
            print("✓ Counter resets when cylinder increases")
            print()
        else:
            print("\n" + "❌"*35)
            print("SOME TESTS FAILED")
            print("❌"*35 + "\n")
        
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
