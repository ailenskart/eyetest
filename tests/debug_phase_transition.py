#!/usr/bin/env python3
"""Debug phase transitions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

session = InteractiveSession()

print("Starting...")
state = session.start_distance_vision()
print(f"After start: phase={session.current_phase}")

state = session.process_response("Able to read")
print(f"After 1st Able to read: phase={session.current_phase}, chart_index={session.current_chart_index}")

for i in range(5):
    state = session.process_response("Able to read")
    print(f"After {i+2}nd Able to read: phase={session.current_phase}, chart_index={session.current_chart_index}, chart={session.snellen_charts[session.current_chart_index]}")

print(f"\nCurrent phase: {session.current_phase}")
print(f"Current chart: {session.snellen_charts[session.current_chart_index]}")
print(f"Available intents: {session.get_intents()}")

print("\nTrying AUTO_FLIP...")
try:
    state = session.process_response("AUTO_FLIP")
    print(f"After AUTO_FLIP: phase={session.current_phase}")
except Exception as e:
    print(f"ERROR: {e}")
