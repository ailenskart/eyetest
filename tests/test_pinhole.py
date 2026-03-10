#!/usr/bin/env python3
"""
Test pinhole functionality during distance vision phase.

When patient says "Unable to read" during distance vision:
1. Pinhole is added
2. Patient is asked if they can see with pinhole
3. Then transition to right eye refraction
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def test_pinhole_unable_to_read():
    """Test pinhole when unable to read during distance vision."""
    print("\n" + "="*70)
    print("TEST: Pinhole Test - Unable to Read E-chart")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting distance vision test...")
    state = session.start_distance_vision()
    print(f"   Phase: {state['phase']}")
    print(f"   Question: {state['question']}")
    print(f"   Intents: {state['intents']}")
    
    # Patient says unable to read
    print("\n2. Patient says 'Unable to read'...")
    state = session.process_response("Unable to read")
    
    print(f"   Phase: {state['phase']}")
    print(f"   Question: {state['question']}")
    print(f"   Intents: {state['intents']}")
    
    # Verify pinhole question appears
    if "pinhole" in state['question'].lower():
        print("   ✓ SUCCESS: Pinhole question displayed")
    else:
        print(f"   ✗ FAILED: Expected pinhole question, got: {state['question']}")
        return False
    
    # Verify pinhole-specific intents
    if "Able to read with pinhole" in state['intents']:
        print("   ✓ SUCCESS: Pinhole intent available")
    else:
        print(f"   ✗ FAILED: Expected pinhole intent, got: {state['intents']}")
        return False
    
    # Patient can see with pinhole
    print("\n3. Patient says 'Able to read with pinhole'...")
    state = session.process_response("Able to read with pinhole")
    
    print(f"   Phase: {state['phase']}")
    
    # Verify moved to right eye refraction
    if "Right Eye Refraction" in state['phase']:
        print("   ✓ SUCCESS: Transitioned to Right Eye Refraction")
    else:
        print(f"   ✗ FAILED: Expected Right Eye Refraction, got: {state['phase']}")
        return False
    
    print("\n" + "="*70)
    return True

def test_pinhole_still_unable():
    """Test when pinhole doesn't help."""
    print("\n" + "="*70)
    print("TEST: Pinhole Test - Still Unable to Read")
    print("="*70)
    
    session = InteractiveSession()
    
    # Start test
    print("\n1. Starting distance vision test...")
    state = session.start_distance_vision()
    
    # Patient says unable to read
    print("\n2. Patient says 'Unable to read' (pinhole added)...")
    state = session.process_response("Unable to read")
    
    if "pinhole" not in state['question'].lower():
        print(f"   ✗ FAILED: Expected pinhole question")
        return False
    
    # Patient still can't see with pinhole
    print("\n3. Patient says 'Still unable to read'...")
    state = session.process_response("Still unable to read")
    
    print(f"   Phase: {state['phase']}")
    
    # Verify moved to right eye refraction anyway
    if "Right Eye Refraction" in state['phase']:
        print("   ✓ SUCCESS: Transitioned to Right Eye Refraction (flagged for evaluation)")
    else:
        print(f"   ✗ FAILED: Expected Right Eye Refraction, got: {state['phase']}")
        return False
    
    print("\n" + "="*70)
    return True

if __name__ == "__main__":
    try:
        success1 = test_pinhole_unable_to_read()
        success2 = test_pinhole_still_unable()
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Pinhole Helps:          {'✅ PASSED' if success1 else '❌ FAILED'}")
        print(f"Pinhole Doesn't Help:   {'✅ PASSED' if success2 else '❌ FAILED'}")
        
        if success1 and success2:
            print("\n" + "🎉"*35)
            print("✅ ALL TESTS PASSED")
            print("🎉"*35)
            print("\nPinhole test functionality verified:")
            print("✓ Pinhole added when unable to read E-chart")
            print("✓ Pinhole question displayed correctly")
            print("✓ Transitions to refraction after pinhole test")
            print("✓ Works for both positive and negative outcomes")
            print()
        else:
            print("\n❌ SOME TESTS FAILED\n")
        
        sys.exit(0 if (success1 and success2) else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
