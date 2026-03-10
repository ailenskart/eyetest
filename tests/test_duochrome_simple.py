#!/usr/bin/env python3
"""Simple test for duochrome reversal power update."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

print("Starting simple duochrome test...")
session = InteractiveSession()

# Manually set phase to duochrome_right for quick testing
session.current_phase = "duochrome_right"
session.current_row.r_sph = -1.00
session.current_row.occluder_state = "Left_Occluded"

print(f"Initial SPH: {session.current_row.r_sph:.2f}D")

# First: Green (increase SPH, no reversal)
print("\n1. Choosing Green...")
state = session.process_response("Green")
print(f"   SPH after Green: {session.current_row.r_sph:.2f}D")
print(f"   Power in response: {'Yes' if 'power' in state else 'No'}")

# Second: Red (decrease SPH, triggers reversal)
print("\n2. Choosing Red (reversal)...")
state = session.process_response("Red")
print(f"   SPH after Red: {session.current_row.r_sph:.2f}D")
print(f"   Phase: {state['phase']}")
print(f"   Power in response: {'Yes' if 'power' in state else 'No'}")

if 'power' in state:
    print(f"   ✓ SUCCESS: Power included! SPH={state['power']['right']['sph']:.2f}D")
else:
    print(f"   ✗ FAILED: Power missing from response!")
    sys.exit(1)

print("\n✅ Test passed!")
