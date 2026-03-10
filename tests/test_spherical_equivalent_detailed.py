#!/usr/bin/env python3
"""
Test spherical equivalent compensation with the exact sequence from the user.

Expected sequence:
CYL  0.00 ; SPH -1.00
CYL -0.25 ; SPH -1.00
CYL -0.50 ; SPH -0.75  (crossed -0.50 threshold → SPH +0.25)
CYL -0.25 ; SPH -1.00  (crossed out of -0.50 → SPH -0.25)
CYL -0.50 ; SPH -0.75  (crossed -0.50 threshold → SPH +0.25)
CYL -0.75 ; SPH -0.75
CYL -1.00 ; SPH -0.50  (crossed -1.00 threshold → SPH +0.25)
CYL -0.75 ; SPH -0.75  (crossed out of -1.00 → SPH -0.25)
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_exact_sequence():
    """Test the exact sequence provided by the user."""
    print("\n" + "="*70)
    print("TEST: Exact Spherical Equivalent Sequence")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test and move to JCC Power Right
    print("\n1. Setting up JCC Power Right phase...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")  # → right_eye_refraction, chart 0
    
    # Move through charts (charts 1-5)
    for _ in range(5):
        state = session.process_response("Able to read")
    
    # Now at chart index 5 (snellen_chart_20_20_20)
    # One more "Able to read" will trigger transition to JCC Axis
    state = session.process_response("Able to read")  # → jcc_axis_right
    
    # Now in JCC Axis phase
    state = session.process_response("AUTO_FLIP")  # JCC Axis Flip1 -> Flip2
    state = session.process_response("Both Same")  # Exit JCC Axis, enter JCC Power
    
    # Verify we're in JCC Power phase
    print(f"   Current phase: {state['phase']}")
    print(f"   Current internal phase: {session.current_phase}")
    
    # Manually set initial values to match example
    session.current_row.r_sph = -1.00
    session.current_row.r_cyl = 0.00
    
    print(f"   Starting: CYL={session.current_row.r_cyl:+5.2f} ; SPH={session.current_row.r_sph:+5.2f}")
    
    # Define expected sequence
    expected_sequence = [
        # (action, expected_cyl, expected_sph, description)
        ("decrease", -0.25, -1.00, "CYL -0.25 (no threshold crossed)"),
        ("decrease", -0.50, -0.75, "CYL -0.50 (crossed -0.50 → SPH +0.25)"),
        ("increase", -0.25, -1.00, "CYL -0.25 (crossed out → SPH -0.25)"),
        ("decrease", -0.50, -0.75, "CYL -0.50 (crossed -0.50 → SPH +0.25)"),
        ("decrease", -0.75, -0.75, "CYL -0.75 (no threshold crossed)"),
        ("decrease", -1.00, -0.50, "CYL -1.00 (crossed -1.00 → SPH +0.25)"),
        ("increase", -0.75, -0.75, "CYL -0.75 (crossed out → SPH -0.25)"),
    ]
    
    all_passed = True
    
    for step_num, (action, exp_cyl, exp_sph, description) in enumerate(expected_sequence, 1):
        print(f"\n{step_num}. {description}")
        
        # Perform action
        state = session.process_response("AUTO_FLIP")
        if action == "decrease":
            state = session.process_response("Flip 2 was better (RAM Power - decrease cylinder by 0.25D)")
        else:  # increase
            state = session.process_response("Flip 1 was better (GAP Power - increase cylinder by 0.25D)")
        
        actual_cyl = session.current_row.r_cyl
        actual_sph = session.current_row.r_sph
        
        print(f"   Expected: CYL={exp_cyl:+5.2f} ; SPH={exp_sph:+5.2f}")
        print(f"   Actual:   CYL={actual_cyl:+5.2f} ; SPH={actual_sph:+5.2f}")
        
        # Check cylinder
        if abs(actual_cyl - exp_cyl) < 0.01:
            print(f"   ✓ CYL correct")
        else:
            print(f"   ✗ CYL incorrect (expected {exp_cyl:.2f}, got {actual_cyl:.2f})")
            all_passed = False
        
        # Check sphere
        if abs(actual_sph - exp_sph) < 0.01:
            print(f"   ✓ SPH correct")
        else:
            print(f"   ✗ SPH incorrect (expected {exp_sph:.2f}, got {actual_sph:.2f})")
            all_passed = False
    
    print("\n" + "="*70)
    return all_passed

if __name__ == "__main__":
    try:
        success = test_exact_sequence()
        
        if success:
            print("\n" + "🎉"*35)
            print("✅ ALL STEPS PASSED")
            print("🎉"*35 + "\n")
            print("Spherical equivalent compensation verified:")
            print("✓ Crossing into -0.50D multiples: SPH +0.25D")
            print("✓ Crossing out of -0.50D multiples: SPH -0.25D")
            print("✓ Works correctly for all threshold crossings")
            print()
        else:
            print("\n" + "❌"*35)
            print("SOME STEPS FAILED")
            print("❌"*35 + "\n")
        
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
