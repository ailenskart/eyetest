#!/usr/bin/env python3
"""
Test phase flow: duochrome_right -> validation_right -> left_eye_refraction;
duochrome_left -> validation_left -> validation_distance -> binocular_balance -> near_add_adjust.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interactive_session import InteractiveSession


def test_duochrome_right_to_validation_right():
    """Duochrome right 'Both Same' should transition to validation_right (Phase H), not left_eye_refraction."""
    session = InteractiveSession()
    session.current_phase = "duochrome_right"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out = session.process_response("Both Same")
    assert session.current_phase == "validation_right", f"expected validation_right, got {session.current_phase}"
    assert "Phase H" in out.get("phase", "") or "validation" in out.get("phase", "").lower()
    print("OK: duochrome_right Both Same -> validation_right")


def test_validation_right_yes_to_left_eye_refraction():
    """Validation right 'Yes' should transition to left_eye_refraction (Phase I)."""
    session = InteractiveSession()
    session.current_phase = "validation_right"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out = session.process_response("Yes")
    assert session.current_phase == "left_eye_refraction", f"expected left_eye_refraction, got {session.current_phase}"
    print("OK: validation_right Yes -> left_eye_refraction")


def test_duochrome_left_to_validation_left():
    """Duochrome left 'Both Same' should transition to validation_left (Phase M), not binocular_balance."""
    session = InteractiveSession()
    session.current_phase = "duochrome_left"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out = session.process_response("Both Same")
    assert session.current_phase == "validation_left", f"expected validation_left, got {session.current_phase}"
    print("OK: duochrome_left Both Same -> validation_left")


def test_validation_left_yes_to_validation_distance():
    """Validation left 'Yes' should transition to validation_distance (Phase N)."""
    session = InteractiveSession()
    session.current_phase = "validation_left"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out = session.process_response("Yes")
    assert session.current_phase == "validation_distance", f"expected validation_distance, got {session.current_phase}"
    print("OK: validation_left Yes -> validation_distance")


def test_validation_distance_yes_to_binocular_balance():
    """Validation distance 'Yes' should transition to binocular_balance (Phase O)."""
    session = InteractiveSession()
    session.current_phase = "validation_distance"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out = session.process_response("Yes")
    assert session.current_phase == "binocular_balance", f"expected binocular_balance, got {session.current_phase}"
    print("OK: validation_distance Yes -> binocular_balance")


def test_binocular_balance_both_same_to_near_add_adjust():
    """Binocular balance 'Both are same' should transition to near_add_adjust (Phase P), not complete."""
    session = InteractiveSession()
    session.current_phase = "binocular_balance"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out = session.process_response("Both are same")
    assert session.current_phase == "near_add_adjust", f"expected near_add_adjust, got {session.current_phase}"
    assert out.get("phase") != "complete"
    print("OK: binocular_balance Both are same -> near_add_adjust")


def test_validation_right_fallback_then_same():
    """Validation right: No -> fallback, then Same -> left_eye_refraction."""
    session = InteractiveSession()
    session.current_phase = "validation_right"
    session.current_row.r_sph = -1.0
    session.current_row.l_sph = -1.0

    out1 = session.process_response("No")
    assert session._validation_fallback_active == "right"
    assert out1.get("status") == "fallback_active"
    assert "Better" in out1.get("intents", [])

    out2 = session.process_response("Same")
    assert session._validation_fallback_active is None
    assert session.current_phase == "left_eye_refraction"
    print("OK: validation_right fallback (No) then Same -> left_eye_refraction")


if __name__ == "__main__":
    test_duochrome_right_to_validation_right()
    test_validation_right_yes_to_left_eye_refraction()
    test_duochrome_left_to_validation_left()
    test_validation_left_yes_to_validation_distance()
    test_validation_distance_yes_to_binocular_balance()
    test_binocular_balance_both_same_to_near_add_adjust()
    test_validation_right_fallback_then_same()
    print("\nAll phase flow tests passed.")
