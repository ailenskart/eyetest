#!/usr/bin/env python3
"""
Test binocular balance phase logic.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession


def test_binocular_balance_top_blurry():
    """Test BINO balance: Top is blurry → Add 0.25D to Left Eye SPH."""
    session = InteractiveSession()
    
    # Set initial state
    session.current_row.r_sph = -1.00
    session.current_row.r_cyl = -0.50
    session.current_row.r_axis = 90.0
    session.current_row.l_sph = -1.00
    session.current_row.l_cyl = -0.50
    session.current_row.l_axis = 85.0
    
    # Transition to binocular balance
    response = session._transition_to_binocular_balance()
    
    print("\n" + "="*60)
    print("TEST: Binocular Balance - Top is Blurry")
    print("="*60)
    print(f"Phase: {response['phase']}")
    print(f"Chart: {response['chart']}")
    print(f"Occluder: {response['occluder']}")
    print(f"Question: {response['question']}")
    print(f"Intents: {response['intents']}")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Verify initial state
    assert response['chart'] == 'bino_chart', "Chart should be bino_chart"
    assert response['occluder'] == 'BINO', "Occluder should be BINO"
    assert "Top is blurry [Right Eye]" in response['intents'], "Should have 'Top is blurry' intent"
    assert "Bottom is blurry [Left Eye]" in response['intents'], "Should have 'Bottom is blurry' intent"
    assert "Both are same" in response['intents'], "Should have 'Both are same' intent"
    
    # Process response: Top is blurry
    print("\n→ Patient responds: Top is blurry [Right Eye]")
    response = session.process_response("Top is blurry [Right Eye]")
    
    print(f"\nAfter adjustment:")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Verify Left Eye SPH increased by 0.25D
    assert response['power']['left']['sph'] == -0.75, f"Left SPH should be -0.75, got {response['power']['left']['sph']}"
    assert response['power']['right']['sph'] == -1.00, f"Right SPH should remain -1.00, got {response['power']['right']['sph']}"
    
    print("\n✓ Test passed: Left Eye SPH increased by 0.25D")


def test_binocular_balance_bottom_blurry():
    """Test BINO balance: Bottom is blurry → Add 0.25D to Right Eye SPH."""
    session = InteractiveSession()
    
    # Set initial state
    session.current_row.r_sph = -1.00
    session.current_row.r_cyl = -0.50
    session.current_row.r_axis = 90.0
    session.current_row.l_sph = -1.00
    session.current_row.l_cyl = -0.50
    session.current_row.l_axis = 85.0
    
    # Transition to binocular balance
    response = session._transition_to_binocular_balance()
    
    print("\n" + "="*60)
    print("TEST: Binocular Balance - Bottom is Blurry")
    print("="*60)
    print(f"Phase: {response['phase']}")
    print(f"Chart: {response['chart']}")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Process response: Bottom is blurry
    print("\n→ Patient responds: Bottom is blurry [Left Eye]")
    response = session.process_response("Bottom is blurry [Left Eye]")
    
    print(f"\nAfter adjustment:")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Verify Right Eye SPH increased by 0.25D
    assert response['power']['right']['sph'] == -0.75, f"Right SPH should be -0.75, got {response['power']['right']['sph']}"
    assert response['power']['left']['sph'] == -1.00, f"Left SPH should remain -1.00, got {response['power']['left']['sph']}"
    
    print("\n✓ Test passed: Right Eye SPH increased by 0.25D")


def test_binocular_balance_both_same():
    """Test BINO balance: Both are same → Test complete."""
    session = InteractiveSession()
    
    # Set initial state
    session.current_row.r_sph = -1.00
    session.current_row.r_cyl = -0.50
    session.current_row.r_axis = 90.0
    session.current_row.l_sph = -1.00
    session.current_row.l_cyl = -0.50
    session.current_row.l_axis = 85.0
    
    # Transition to binocular balance
    response = session._transition_to_binocular_balance()
    
    print("\n" + "="*60)
    print("TEST: Binocular Balance - Both are Same")
    print("="*60)
    print(f"Phase: {response['phase']}")
    print(f"Chart: {response['chart']}")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Process response: Both are same
    print("\n→ Patient responds: Both are same")
    response = session.process_response("Both are same")
    
    print(f"\nResult:")
    print(f"Phase: {response['phase']}")
    print(f"Status: {response.get('status', 'N/A')}")
    print(f"Question: {response['question']}")
    
    # Verify test complete
    assert response['phase'] == 'complete', f"Phase should be 'complete', got {response['phase']}"
    assert response['status'] == 'complete', f"Status should be 'complete', got {response.get('status', 'N/A')}"
    
    print("\n✓ Test passed: Test completed successfully")


def test_binocular_balance_prev_state():
    """Test BINO balance: Prev State → Restore previous power."""
    session = InteractiveSession()
    
    # Set initial state
    session.current_row.r_sph = -1.00
    session.current_row.r_cyl = -0.50
    session.current_row.r_axis = 90.0
    session.current_row.l_sph = -1.00
    session.current_row.l_cyl = -0.50
    session.current_row.l_axis = 85.0
    
    # Transition to binocular balance
    response = session._transition_to_binocular_balance()
    
    print("\n" + "="*60)
    print("TEST: Binocular Balance - Prev State")
    print("="*60)
    print(f"Phase: {response['phase']}")
    print(f"Initial Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"               L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Process response: Top is blurry (saves previous state)
    print("\n→ Patient responds: Top is blurry [Right Eye]")
    response = session.process_response("Top is blurry [Right Eye]")
    
    print(f"\nAfter adjustment:")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Verify Left Eye SPH increased
    assert response['power']['left']['sph'] == -0.75, "Left SPH should be -0.75"
    
    # Verify "Prev State" is available
    assert "Prev State" in response['intents'], "Should have 'Prev State' intent available"
    
    # Process response: Prev State
    print("\n→ Patient responds: Prev State")
    response = session.process_response("Prev State")
    
    print(f"\nAfter restoring previous state:")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Verify power restored to original
    assert response['power']['left']['sph'] == -1.00, f"Left SPH should be restored to -1.00, got {response['power']['left']['sph']}"
    assert response['power']['right']['sph'] == -1.00, f"Right SPH should remain -1.00, got {response['power']['right']['sph']}"
    
    # Verify "Prev State" is no longer available
    assert "Prev State" not in response['intents'], "Should not have 'Prev State' intent after restoring"
    
    print("\n✓ Test passed: Previous state restored successfully")


def test_binocular_balance_iterative():
    """Test BINO balance: Multiple adjustments until balanced."""
    session = InteractiveSession()
    
    # Set initial state
    session.current_row.r_sph = -1.00
    session.current_row.r_cyl = -0.50
    session.current_row.r_axis = 90.0
    session.current_row.l_sph = -1.50
    session.current_row.l_cyl = -0.50
    session.current_row.l_axis = 85.0
    
    # Transition to binocular balance
    response = session._transition_to_binocular_balance()
    
    print("\n" + "="*60)
    print("TEST: Binocular Balance - Iterative Adjustments")
    print("="*60)
    print(f"Phase: {response['phase']}")
    print(f"Initial Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"               L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Round 1: Bottom is blurry (add to right eye)
    print("\n→ Round 1: Patient responds: Bottom is blurry [Left Eye]")
    response = session.process_response("Bottom is blurry [Left Eye]")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    assert response['power']['right']['sph'] == -0.75, "Right SPH should be -0.75"
    
    # Round 2: Bottom is still blurry (add more to right eye)
    print("\n→ Round 2: Patient responds: Bottom is blurry [Left Eye]")
    response = session.process_response("Bottom is blurry [Left Eye]")
    print(f"Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"       L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    assert response['power']['right']['sph'] == -0.50, "Right SPH should be -0.50"
    
    # Round 3: Both are same (balanced)
    print("\n→ Round 3: Patient responds: Both are same")
    response = session.process_response("Both are same")
    print(f"Final Power: R({response['power']['right']['sph']}/{response['power']['right']['cyl']}/{response['power']['right']['axis']})")
    print(f"             L({response['power']['left']['sph']}/{response['power']['left']['cyl']}/{response['power']['left']['axis']})")
    
    # Verify test complete
    assert response['phase'] == 'complete', "Phase should be 'complete'"
    assert response['status'] == 'complete', "Status should be 'complete'"
    
    print("\n✓ Test passed: Iterative balancing completed successfully")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("BINOCULAR BALANCE PHASE TESTS")
    print("="*60)
    
    try:
        test_binocular_balance_top_blurry()
        test_binocular_balance_bottom_blurry()
        test_binocular_balance_both_same()
        test_binocular_balance_prev_state()
        test_binocular_balance_iterative()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
