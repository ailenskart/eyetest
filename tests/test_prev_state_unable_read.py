#!/usr/bin/env python3
"""
Test to verify "Prev State" appears for "Unable to read" option as well.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_prev_state_for_unable_read():
    """Test that Prev State appears after 'Unable to read'."""
    print("\n" + "="*70)
    print("TEST: Prev State for 'Unable to read' option")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting test...")
    state = session.start_distance_vision()
    
    # Move to right eye refraction
    print("\n2. Moving to right eye refraction...")
    state = session.process_response("Able to read")
    print(f"   Phase: {state['phase']}")
    print(f"   Right eye SPH: {state['power']['right']['sph']}")
    
    # Respond with "Unable to read" - should add -0.25D and enable "Prev State"
    print("\n3. Responding with 'Unable to read' (should add -0.25D SPH)...")
    initial_sph = state['power']['right']['sph']
    state = session.process_response("Unable to read")
    new_sph = state['power']['right']['sph']
    print(f"   Before: {initial_sph:.2f}D")
    print(f"   After:  {new_sph:.2f}D")
    print(f"   Change: {new_sph - initial_sph:.2f}D")
    print(f"   Available intents: {state['intents']}")
    
    # Verify "Prev State" is available
    if "Prev State" in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' option is available after 'Unable to read'!")
        
        # Now click "Prev State" to restore previous power
        print("\n4. Clicking 'Prev State' to restore previous power...")
        state = session.process_response("Prev State")
        restored_sph = state['power']['right']['sph']
        print(f"   Restored SPH: {restored_sph:.2f}D")
        print(f"   Available intents: {state['intents']}")
        
        if abs(restored_sph - initial_sph) < 0.01:
            print("   ✓ SUCCESS: Power restored to previous state!")
        else:
            print(f"   ✗ FAILED: Power not restored correctly (expected {initial_sph:.2f}, got {restored_sph:.2f})")
            return False
        
        # Verify "Prev State" is no longer available
        if "Prev State" not in state['intents']:
            print("   ✓ SUCCESS: 'Prev State' option removed after use!")
        else:
            print("   ✗ FAILED: 'Prev State' should be removed after use")
            return False
    else:
        print("   ✗ FAILED: 'Prev State' option not available after 'Unable to read' response")
        return False
    
    print("\n" + "="*70)
    return True

def test_prev_state_for_blurry_still_works():
    """Test that Prev State still works for 'Blurry' option."""
    print("\n" + "="*70)
    print("TEST: Prev State for 'Blurry' option (should still work)")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting test...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    # Move through some charts
    for _ in range(3):
        state = session.process_response("Able to read")
    
    print(f"   Phase: {state['phase']}")
    initial_sph = state['power']['right']['sph']
    print(f"   Right eye SPH: {initial_sph:.2f}D")
    
    # Respond with "Blurry"
    print("\n2. Responding with 'Blurry'...")
    state = session.process_response("Blurry")
    new_sph = state['power']['right']['sph']
    print(f"   After Blurry: {new_sph:.2f}D")
    print(f"   Available intents: {state['intents']}")
    
    if "Prev State" in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' still appears for 'Blurry'!")
        
        # Click Prev State
        state = session.process_response("Prev State")
        restored_sph = state['power']['right']['sph']
        
        if abs(restored_sph - initial_sph) < 0.01:
            print("   ✓ SUCCESS: Power restored correctly!")
        else:
            print(f"   ✗ FAILED: Power not restored")
            return False
    else:
        print("   ✗ FAILED: 'Prev State' should appear for 'Blurry'")
        return False
    
    print("\n" + "="*70)
    return True

def test_prev_state_not_for_able_to_read():
    """Test that Prev State does NOT appear for 'Able to read'."""
    print("\n" + "="*70)
    print("TEST: Prev State should NOT appear for 'Able to read'")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting test...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    print(f"\n2. Responding with 'Able to read'...")
    state = session.process_response("Able to read")
    print(f"   Available intents: {state['intents']}")
    
    if "Prev State" not in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' does not appear for 'Able to read'")
    else:
        print("   ✗ FAILED: 'Prev State' should not appear for 'Able to read'")
        return False
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success = True
        success = test_prev_state_for_unable_read() and success
        success = test_prev_state_for_blurry_still_works() and success
        success = test_prev_state_not_for_able_to_read() and success
        
        if success:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35 + "\n")
            print("Key behaviors verified:")
            print("✓ 'Prev State' appears after 'Unable to read'")
            print("✓ 'Prev State' still appears after 'Blurry'")
            print("✓ 'Prev State' does NOT appear after 'Able to read'")
            print("✓ Power is correctly restored when 'Prev State' is clicked")
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
