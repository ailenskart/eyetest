#!/usr/bin/env python3
"""
Test ADD phase logic (P: Near Vision - ADD, Q: Near Vision - Testing).
- Session add_right / add_left increment on Blurry.
- Phase transitions and response shape (current_add, power with add).
"""
import sys
from pathlib import Path

# Allow importing from parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interactive_session import InteractiveSession


def test_add_increments_on_blurry():
    """Phase P: Blurry increases add_right and add_left by 0.25."""
    session = InteractiveSession()
    session.current_phase = "near_add_adjust"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0
    session.add_right = 0.0
    session.add_left = 0.0

    out = session.process_response("Blurry")
    assert session.add_right == 0.25
    assert session.add_left == 0.25
    assert out.get("current_add") == 0.25
    assert "Blurry" in out.get("intents", [])

    out2 = session.process_response("Blurry")
    assert session.add_right == 0.50
    assert session.add_left == 0.50
    assert out2.get("current_add") == 0.50
    print("OK: ADD increments on Blurry (Phase P)")


def test_add_comfortable_goes_to_near_chart_testing():
    """Phase P: Comfortable moves to near_chart_testing."""
    session = InteractiveSession()
    session.current_phase = "near_add_adjust"
    session.add_right = 1.0
    session.add_left = 1.0

    out = session.process_response("Comfortable")
    assert session.current_phase == "near_chart_testing"
    assert "Phase Q" in out.get("phase", "")
    print("OK: Comfortable transitions to Phase Q (near_chart_testing)")


def test_near_chart_testing_confirmed_returns_power_with_add():
    """Phase Q: Confirmed returns power dict with add."""
    session = InteractiveSession()
    session.current_phase = "near_chart_testing"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.25
    session.add_right = 1.25
    session.add_left = 1.25

    out = session.process_response("Confirmed")
    assert out.get("phase") == "complete"
    assert "power" in out
    assert out["power"]["right"].get("add") == 1.25
    assert out["power"]["left"].get("add") == 1.25
    print("OK: Confirmed returns power with ADD in response")


if __name__ == "__main__":
    test_add_increments_on_blurry()
    test_add_comfortable_goes_to_near_chart_testing()
    test_near_chart_testing_confirmed_returns_power_with_add()
    print("\nAll ADD phase tests passed.")
