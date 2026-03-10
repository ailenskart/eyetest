#!/usr/bin/env python3
"""
Interactive demo script to test the "Prev State" feature manually.
Shows exactly when "Prev State" appears and how it works.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive_session import InteractiveSession

def print_state(state, session):
    """Print current state in a nice format."""
    print("\n" + "="*70)
    print(f"📋 Phase: {state['phase']}")
    print(f"❓ Question: {state['question']}")
    print("-"*70)
    print(f"📊 Chart: {state.get('chart', session.current_row.chart_display)}")
    print(f"👁️  Occluder: {state.get('occluder', session.current_row.occluder_state)}")
    
    # Get power from state or session
    if 'power' in state:
        r_power = state['power']['right']
        l_power = state['power']['left']
    else:
        r_power = {
            'sph': session.current_row.r_sph,
            'cyl': session.current_row.r_cyl,
            'axis': session.current_row.r_axis
        }
        l_power = {
            'sph': session.current_row.l_sph,
            'cyl': session.current_row.l_cyl,
            'axis': session.current_row.l_axis
        }
    
    print(f"🔧 Power:")
    print(f"   Right: {r_power['sph']:+6.2f} / {r_power['cyl']:+6.2f} / {r_power['axis']:3.0f}°")
    print(f"   Left:  {l_power['sph']:+6.2f} / {l_power['cyl']:+6.2f} / {l_power['axis']:3.0f}°")
    print("-"*70)
    print(f"💬 Available Options:")
    for i, intent in enumerate(state['intents'], 1):
        marker = "⭐" if intent == "Prev State" else "  "
        print(f"   {marker} {i}. {intent}")
    print("="*70)

def get_user_choice(state):
    """Get user's choice of intent."""
    intents = state['intents']
    while True:
        try:
            choice = input(f"\n➤ Enter choice (1-{len(intents)}) or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(intents):
                return intents[idx]
            print(f"❌ Invalid choice. Please enter 1-{len(intents)}")
        except ValueError:
            print("❌ Invalid input. Please enter a number.")

def main():
    print("\n" + "🔬"*35)
    print("PREV STATE FEATURE - INTERACTIVE DEMO")
    print("🔬"*35)
    print("\nThis demo shows the 'Prev State' feature in action.")
    print("Look for the ⭐ star when 'Prev State' appears!")
    print("\nInstructions:")
    print("1. We'll start the test and move to right eye refraction")
    print("2. Move through some charts by selecting 'Able to read'")
    print("3. Select 'Blurry' to see the 'Prev State' option appear")
    print("4. Select 'Prev State' to undo the change")
    
    input("\n➤ Press Enter to start the demo...")
    
    session = InteractiveSession()
    
    # Start test
    print("\n🚀 Starting test...")
    state = session.start_distance_vision()
    print_state(state, session)
    
    # Auto-proceed to right eye refraction
    print("\n⏩ Auto-proceeding to Right Eye Refraction...")
    input("   Press Enter to continue...")
    state = session.process_response("Able to read")
    print_state(state, session)
    
    # Main loop
    step = 1
    while True:
        print(f"\n📍 Step {step}")
        
        # Check if we're in the right phase for the demo
        if session.current_phase not in ['right_eye_refraction', 'left_eye_refraction']:
            print("\n✅ Demo complete! You've seen the 'Prev State' feature in action.")
            print("   The feature works the same way for left eye refraction.")
            break
        
        # Suggest actions based on state
        if "Prev State" in state['intents']:
            print("\n💡 TIP: Notice the ⭐ 'Prev State' option!")
            print("       Try selecting it to restore the previous power.")
        elif "Blurry" in state['intents'] and session.current_chart_index > 2:
            print("\n💡 TIP: Try selecting 'Blurry' to see the 'Prev State' option appear.")
        
        # Get user choice
        choice = get_user_choice(state)
        
        if choice is None:
            print("\n👋 Demo ended by user.")
            break
        
        # Process response
        print(f"\n✓ Selected: {choice}")
        if choice == "Blurry":
            print("   ⚡ Power will be adjusted by -0.25D SPH")
            print("   ⚡ Watch for 'Prev State' option in next screen!")
        elif choice == "Prev State":
            print("   ⚡ Power will be restored to previous state")
            print("   ⚡ 'Prev State' option will be removed")
        
        input("   Press Enter to continue...")
        
        state = session.process_response(choice)
        
        # Check if test is complete
        if state.get('phase') == 'complete' or state.get('status') == 'complete':
            print("\n✅ Test complete!")
            break
        
        print_state(state, session)
        step += 1
    
    print("\n" + "🎉"*35)
    print("DEMO FINISHED")
    print("🎉"*35)
    print("\nKey Takeaways:")
    print("✓ 'Prev State' appears only after clicking 'Blurry'")
    print("✓ It restores the power to the state before 'Blurry' was clicked")
    print("✓ It disappears after being used or when another option is selected")
    print("✓ It works for both right and left eye refraction phases")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
