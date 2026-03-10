#!/usr/bin/env python3
"""
Test script to verify "Prev State" functionality for Blurry responses.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_prev_state_right_eye():
    """Test Prev State functionality for right eye refraction."""
    print("\n" + "="*70)
    print("TEST: Right Eye Refraction - Prev State after Blurry")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting test...")
    state = session.start_distance_vision()
    print(f"   Initial phase: {state['phase']}")
    
    # Move to right eye refraction
    print("\n2. Moving to right eye refraction...")
    state = session.process_response("Able to read")
    print(f"   Phase: {state['phase']}")
    print(f"   Question: {state['question']}")
    print(f"   Right eye SPH: {state['power']['right']['sph']}")
    
    # Respond with "Able to read" to move through charts
    print("\n3. Moving through charts...")
    for i in range(5):
        state = session.process_response("Able to read")
        print(f"   Chart: {state['chart']}, Right SPH: {state['power']['right']['sph']}")
    
    # Now respond with "Blurry" - this should add -0.25D and enable "Prev State"
    print("\n4. Responding with 'Blurry' (should add -0.25D SPH)...")
    initial_sph = state['power']['right']['sph']
    state = session.process_response("Blurry")
    new_sph = state['power']['right']['sph']
    print(f"   Before Blurry: {initial_sph:.2f}D")
    print(f"   After Blurry:  {new_sph:.2f}D")
    print(f"   Change: {new_sph - initial_sph:.2f}D")
    print(f"   Available intents: {state['intents']}")
    
    # Verify "Prev State" is available
    if "Prev State" in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' option is available!")
        
        # Now click "Prev State" to restore previous power
        print("\n5. Clicking 'Prev State' to restore previous power...")
        state = session.process_response("Prev State")
        restored_sph = state['power']['right']['sph']
        print(f"   Restored SPH: {restored_sph:.2f}D")
        print(f"   Available intents: {state['intents']}")
        
        if abs(restored_sph - initial_sph) < 0.01:
            print("   ✓ SUCCESS: Power restored to previous state!")
        else:
            print(f"   ✗ FAILED: Power not restored correctly (expected {initial_sph:.2f}, got {restored_sph:.2f})")
        
        # Verify "Prev State" is no longer available
        if "Prev State" not in state['intents']:
            print("   ✓ SUCCESS: 'Prev State' option removed after use!")
        else:
            print("   ✗ FAILED: 'Prev State' should be removed after use")
    else:
        print("   ✗ FAILED: 'Prev State' option not available after 'Blurry' response")
    
    print("\n" + "="*70)

def test_prev_state_left_eye():
    """Test Prev State functionality for left eye refraction."""
    print("\n" + "="*70)
    print("TEST: Left Eye Refraction - Prev State after Blurry")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test and move to left eye refraction quickly
    print("\n1. Starting test and moving to left eye refraction...")
    state = session.start_distance_vision()
    state = session.process_response("Able to read")  # To right eye
    
    # Move through right eye quickly
    for _ in range(6):
        state = session.process_response("Able to read")
    
    # Skip JCC phases by reaching exit conditions
    state = session.process_response("AUTO_FLIP")  # JCC Axis Flip1
    state = session.process_response("Both Same")  # JCC Axis Flip2
    state = session.process_response("AUTO_FLIP")  # JCC Power Flip1
    state = session.process_response("Both Same")  # JCC Power Flip2
    state = session.process_response("Both Same")  # Duochrome
    
    # Now at left eye refraction
    print(f"   Phase: {state['phase']}")
    
    # Move through charts
    print("\n2. Moving through charts...")
    for i in range(3):
        state = session.process_response("Able to read")
    
    # Get current left eye SPH
    left_sph = session.current_row.l_sph
    print(f"   Current Left eye SPH: {left_sph}")
    
    # Respond with "Blurry"
    print("\n3. Responding with 'Blurry' (should add -0.25D SPH)...")
    initial_sph = left_sph
    state = session.process_response("Blurry")
    new_sph = session.current_row.l_sph
    print(f"   Before Blurry: {initial_sph:.2f}D")
    print(f"   After Blurry:  {new_sph:.2f}D")
    print(f"   Change: {new_sph - initial_sph:.2f}D")
    print(f"   Available intents: {state['intents']}")
    
    # Verify "Prev State" is available
    if "Prev State" in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' option is available!")
        
        # Click "Prev State"
        print("\n4. Clicking 'Prev State' to restore previous power...")
        state = session.process_response("Prev State")
        restored_sph = session.current_row.l_sph
        print(f"   Restored SPH: {restored_sph:.2f}D")
        
        if abs(restored_sph - initial_sph) < 0.01:
            print("   ✓ SUCCESS: Power restored to previous state!")
        else:
            print(f"   ✗ FAILED: Power not restored correctly")
        
        if "Prev State" not in state['intents']:
            print("   ✓ SUCCESS: 'Prev State' option removed after use!")
    else:
        print("   ✗ FAILED: 'Prev State' option not available after 'Blurry' response")
    
    print("\n" + "="*70)

def test_prev_state_not_available_for_other_intents():
    """Test that Prev State is not available for non-Blurry responses."""
    print("\n" + "="*70)
    print("TEST: Prev State NOT available for other intents")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start and move to right eye refraction
    state = session.start_distance_vision()
    state = session.process_response("Able to read")
    
    print("\n1. Testing 'Unable to read' response...")
    state = session.process_response("Unable to read")
    print(f"   Available intents: {state['intents']}")
    
    if "Prev State" not in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' not available for 'Unable to read'")
    else:
        print("   ✗ FAILED: 'Prev State' should not be available")
    
    print("\n2. Testing 'Able to read' response...")
    state = session.process_response("Able to read")
    print(f"   Available intents: {state['intents']}")
    
    if "Prev State" not in state['intents']:
        print("   ✓ SUCCESS: 'Prev State' not available for 'Able to read'")
    else:
        print("   ✗ FAILED: 'Prev State' should not be available")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    # Run all tests
    test_prev_state_right_eye()
    test_prev_state_left_eye()
    test_prev_state_not_available_for_other_intents()
    
    print("\n" + "="*70)
    print("All tests completed!")
    print("="*70 + "\n")
