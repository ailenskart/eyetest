#!/usr/bin/env python3
"""
Test to verify "Getting better" option is commented out.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_no_getting_better():
    """Verify that 'Getting better' is not in the intents list."""
    print("\n" + "="*70)
    print("TEST: Verify 'Getting better' option is commented out")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting test...")
    state = session.start_distance_vision()
    
    # Move to right eye refraction
    print("\n2. Moving to right eye refraction...")
    state = session.process_response("Able to read")
    
    print(f"\n3. Checking intents for right eye refraction...")
    print(f"   Phase: {state['phase']}")
    print(f"   Available intents: {state['intents']}")
    
    if "Getting better" in state['intents']:
        print("   ✗ FAILED: 'Getting better' should be commented out!")
        return False
    else:
        print("   ✓ SUCCESS: 'Getting better' is not in the intents list")
    
    # Move through charts to left eye
    print("\n4. Moving to left eye refraction...")
    for _ in range(6):
        state = session.process_response("Able to read")
    
    # Skip JCC phases
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    state = session.process_response("AUTO_FLIP")
    state = session.process_response("Both Same")
    state = session.process_response("Both Same")
    
    print(f"\n5. Checking intents for left eye refraction...")
    print(f"   Phase: {state['phase']}")
    print(f"   Available intents: {state['intents']}")
    
    if "Getting better" in state['intents']:
        print("   ✗ FAILED: 'Getting better' should be commented out!")
        return False
    else:
        print("   ✓ SUCCESS: 'Getting better' is not in the intents list")
    
    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED: 'Getting better' is successfully commented out")
    print("="*70 + "\n")
    return True

if __name__ == "__main__":
    try:
        success = test_no_getting_better()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
