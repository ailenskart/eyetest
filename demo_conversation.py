#!/usr/bin/env python3
"""
Demo script showing conversation flow with simulated responses.
"""
import json
from pathlib import Path
import yaml


def load_protocol():
    """Load protocol configuration."""
    config_path = Path(__file__).parent / "config" / "protocol.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def display_conversation_step(phase_id: str, protocol: dict, step_num: int):
    """Display a conversation step."""
    phase = protocol["phases"].get(phase_id, {})
    phase_name = phase.get("name", phase_id)
    questions = phase.get("questions", [])
    intents = phase.get("intents", [])
    
    print(f"\n{'='*70}")
    print(f"STEP {step_num}: {phase_name}")
    print(f"{'='*70}")
    
    # Display question
    if isinstance(questions, dict):
        # JCC phase
        print(f"\n❓ Question (Flip 1): {questions.get('flip1', '')}")
        print(f"❓ Question (Flip 2): {questions.get('flip2', '')}")
    elif isinstance(questions, list) and questions:
        print(f"\n❓ Question: {questions[0]}")
    
    # Display intents
    print(f"\n💬 Available Patient Responses:")
    if isinstance(intents, dict):
        # JCC phase
        flip1_intent = intents.get("flip1", "")
        flip2_intents = intents.get("flip2", [])
        
        print(f"\n  Flip 1 Response:")
        print(f"    • {flip1_intent}")
        
        print(f"\n  Flip 2 Responses:")
        if isinstance(flip2_intents, list):
            for i, intent in enumerate(flip2_intents, 1):
                print(f"    {i}. {intent}")
        else:
            print(f"    • {flip2_intents}")
    elif isinstance(intents, list):
        for i, intent in enumerate(intents, 1):
            print(f"    {i}. {intent}")
    
    # Display trigger info
    trigger = phase.get("trigger", {})
    print(f"\n🔧 Machine State:")
    print(f"    Occluder: {trigger.get('occluder', 'N/A')}")
    print(f"    Charts: {', '.join(trigger.get('charts', []))}")


def main():
    """Run demo conversation."""
    protocol = load_protocol()
    
    print("\n" + "="*70)
    print("EYE TEST ENGINE - CONVERSATION FLOW DEMO")
    print("="*70)
    print("\nThis demo shows the question-and-answer flow for each phase")
    print("of the eye test, with available patient response options.")
    
    # Define conversation flow
    flow = [
        ("distance_vision", "Distance Vision - Initial Assessment"),
        ("right_eye_refraction", "Right Eye - Sphere Refinement"),
        ("jcc_axis_right", "Right Eye - Axis Refinement (JCC)"),
        ("jcc_power_right", "Right Eye - Power Refinement (JCC)"),
        ("duochrome_right", "Right Eye - Duochrome Balance"),
        ("left_eye_refraction", "Left Eye - Sphere Refinement"),
        ("jcc_axis_left", "Left Eye - Axis Refinement (JCC)"),
        ("jcc_power_left", "Left Eye - Power Refinement (JCC)"),
        ("duochrome_left", "Left Eye - Duochrome Balance"),
        ("binocular_balance", "Binocular Balance - Final Verification"),
    ]
    
    for step_num, (phase_id, description) in enumerate(flow, 1):
        display_conversation_step(phase_id, protocol, step_num)
        
        if step_num < len(flow):
            input(f"\n{'─'*70}\nPress Enter to continue to next phase...")
    
    print(f"\n{'='*70}")
    print("END OF DEMO")
    print(f"{'='*70}")
    print("\nComplete conversation flow demonstrated!")
    print("\nTo run an actual test:")
    print("  1. Start API server: python -m eye_test_engine.api_server")
    print("  2. Use curl commands from curl_API.md to control phoropter")
    print("  3. POST to /api/session/start to begin")
    print("  4. POST to /api/session/<id>/respond with patient intent")


if __name__ == "__main__":
    main()
