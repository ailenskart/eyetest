#!/usr/bin/env python3
"""
FSM Simulator Tests: Verify state transitions, guard evaluation,
entry actions, timeout behavior, and full test paths through the FSM.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.patient_input import PatientInput
from core.ar_lenso_input import ARInput, LensoInput, EyeRx
from core.derived_variables import (
    DerivedVariables, compute_derived_variables, load_calibration,
)
from core.state_machine import (
    FSMStateMachine, PhaseState, normalize_response, load_response_types,
)


class TestResponseNormalization(unittest.TestCase):
    """Tests for response normalization (legacy mapping)."""

    def setUp(self):
        config_dir = Path(__file__).parent.parent / "config"
        self.rt = load_response_types(config_dir)

    def test_canonical_passthrough(self):
        self.assertEqual(normalize_response("READABLE", self.rt), "READABLE")
        self.assertEqual(normalize_response("BETTER_1", self.rt), "BETTER_1")

    def test_legacy_mapping(self):
        self.assertEqual(normalize_response("Able to read", self.rt), "READABLE")
        self.assertEqual(normalize_response("Unable to read", self.rt), "NOT_READABLE")
        self.assertEqual(normalize_response("Flip 1 better", self.rt), "BETTER_1")
        self.assertEqual(normalize_response("Flip 2 better", self.rt), "BETTER_2")
        self.assertEqual(normalize_response("Both Same", self.rt), "SAME")

    def test_color_mapping(self):
        self.assertEqual(normalize_response("Red", self.rt), "RED_CLEARER")
        self.assertEqual(normalize_response("Green", self.rt), "GREEN_CLEARER")
        self.assertEqual(normalize_response("Red is clearer", self.rt), "RED_CLEARER")

    def test_top_bottom_mapping(self):
        self.assertEqual(normalize_response("Top is blurry", self.rt), "BOTTOM_CLEARER")
        self.assertEqual(normalize_response("Bottom is blurry", self.rt), "TOP_CLEARER")

    def test_unknown_passthrough(self):
        self.assertEqual(normalize_response("UNKNOWN_VAL", self.rt), "UNKNOWN_VAL")


class TestFSMInitialization(unittest.TestCase):
    """Tests for FSM initialization and config loading."""

    def setUp(self):
        self.cal = load_calibration()
        self.dv = DerivedVariables(
            dv_start_rx_RE_sph=-2.0, dv_start_rx_RE_cyl=-0.75,
            dv_start_rx_RE_axis=180,
            dv_start_rx_LE_sph=-1.75, dv_start_rx_LE_cyl=-0.50,
            dv_start_rx_LE_axis=170,
        )

    def test_initial_state(self):
        fsm = FSMStateMachine(derived_vars=self.dv)
        self.assertEqual(fsm.current_state, "A")
        self.assertFalse(fsm.is_terminal)

    def test_lens_initialization(self):
        fsm = FSMStateMachine(derived_vars=self.dv)
        ps = fsm.phase_state
        self.assertAlmostEqual(ps.re_sph, -2.0)
        self.assertAlmostEqual(ps.re_cyl, -0.75)
        self.assertAlmostEqual(ps.re_axis, 180)
        self.assertAlmostEqual(ps.le_sph, -1.75)
        self.assertAlmostEqual(ps.le_cyl, -0.50)
        self.assertAlmostEqual(ps.le_axis, 170)

    def test_config_loaded(self):
        fsm = FSMStateMachine(derived_vars=self.dv)
        self.assertIn("A", fsm.transitions_config)
        self.assertIn("B", fsm.transitions_config)
        self.assertIn("END", fsm.transitions_config)
        self.assertIn("DIST_BASELINE", fsm.phase_ui_map)

    def test_ui_config(self):
        fsm = FSMStateMachine(derived_vars=self.dv)
        question = fsm.get_question()
        self.assertTrue(len(question) > 0)
        responses = fsm.get_allowed_responses()
        self.assertIsInstance(responses, list)
        self.assertTrue(len(responses) > 0)


class TestGuardEvaluation(unittest.TestCase):
    """Tests for guard condition evaluation engine."""

    def setUp(self):
        self.dv = DerivedVariables()
        self.fsm = FSMStateMachine(derived_vars=self.dv)

    def test_true_literal(self):
        result = self.fsm._evaluate_guard("true", {})
        self.assertTrue(result)

    def test_equality(self):
        ctx = {"response": "READABLE"}
        self.assertTrue(self.fsm._evaluate_guard("response == READABLE", ctx))
        self.assertFalse(self.fsm._evaluate_guard("response == BLURRY", ctx))

    def test_inequality(self):
        ctx = {"dv_add_expected": "None"}
        self.assertTrue(self.fsm._evaluate_guard("dv_add_expected != Likely", ctx))
        self.assertFalse(self.fsm._evaluate_guard("dv_add_expected != None", ctx))

    def test_greater_equal(self):
        ctx = {"chart_idx": 5, "target_chart_idx": 5}
        self.assertTrue(self.fsm._evaluate_guard(
            "chart_idx >= target_chart_idx", ctx
        ))

    def test_greater_than(self):
        ctx = {"comparisons": 10, "limit": 5}
        self.assertTrue(self.fsm._evaluate_guard(
            "comparisons > limit", ctx
        ))

    def test_in_list(self):
        ctx = {"response": "BETTER_1"}
        self.assertTrue(self.fsm._evaluate_guard(
            "response in [BETTER_1, BETTER_2]", ctx
        ))
        ctx2 = {"response": "SAME"}
        self.assertFalse(self.fsm._evaluate_guard(
            "response in [BETTER_1, BETTER_2]", ctx2
        ))

    def test_and_conjunction(self):
        ctx = {"axis_converged": True, "response": "SAME"}
        self.assertTrue(self.fsm._evaluate_guard(
            "axis_converged and response == SAME", ctx
        ))
        ctx2 = {"axis_converged": False, "response": "SAME"}
        self.assertFalse(self.fsm._evaluate_guard(
            "axis_converged and response == SAME", ctx2
        ))

    def test_or_disjunction(self):
        ctx1 = {"response": "SAME"}
        self.assertTrue(self.fsm._evaluate_guard(
            "response == SAME or response == CANT_TELL", ctx1
        ))
        ctx2 = {"response": "BETTER_1"}
        self.assertFalse(self.fsm._evaluate_guard(
            "response == SAME or response == CANT_TELL", ctx2
        ))

    def test_bare_boolean(self):
        ctx = {"dv_requires_optom_review": True}
        self.assertTrue(self.fsm._evaluate_guard(
            "dv_requires_optom_review", ctx
        ))

    def test_none_comparison(self):
        ctx = {"dv_add_expected": "None"}
        self.assertTrue(self.fsm._evaluate_guard(
            "dv_add_expected == None", ctx
        ))


class TestPhaseState(unittest.TestCase):
    """Tests for PhaseState management."""

    def test_reset(self):
        ps = PhaseState()
        ps.step_count = 10
        ps.axis_converged = True
        ps.fog_remaining = 0.5
        ps.reset_for_new_state()
        self.assertEqual(ps.step_count, 0)
        self.assertFalse(ps.axis_converged)
        self.assertAlmostEqual(ps.fog_remaining, 0.0)


class TestDistanceBaseline(unittest.TestCase):
    """Tests for State A: Distance Baseline transitions."""

    def setUp(self):
        self.dv = DerivedVariables(
            dv_start_rx_RE_sph=-2.0, dv_start_rx_RE_cyl=-0.75,
            dv_start_rx_RE_axis=180,
            dv_start_rx_LE_sph=-1.75, dv_start_rx_LE_cyl=-0.50,
            dv_start_rx_LE_axis=170,
            dv_target_distance_va="6/6_target",
        )

    def test_readable_advances_chart(self):
        """READABLE increments chart index but stays in A if not at target."""
        fsm = FSMStateMachine(derived_vars=self.dv)
        self.assertEqual(fsm.current_state, "A")

        # First READABLE — chart_idx 0 → 1 (still < target 5)
        new_state = fsm.transition("READABLE")
        self.assertEqual(new_state, "A")  # Stays in A

    def test_progress_to_target(self):
        """Reaching target chart with READABLE transitions to B."""
        fsm = FSMStateMachine(derived_vars=self.dv)

        # Walk through all charts (6 charts, 0→5)
        for i in range(5):
            fsm.transition("READABLE")
            fsm.phase_state.chart_idx = i + 1

        # At chart_idx=5 (target), READABLE should transition to B
        new_state = fsm.transition("READABLE")
        self.assertEqual(new_state, "B")

    def test_not_readable_stays(self):
        """NOT_READABLE stays in state A."""
        fsm = FSMStateMachine(derived_vars=self.dv)
        new_state = fsm.transition("NOT_READABLE")
        self.assertEqual(new_state, "A")

    def test_optom_review_escalates(self):
        """If dv_requires_optom_review=True, transitions to ESCALATE."""
        dv = DerivedVariables(dv_requires_optom_review=True)
        fsm = FSMStateMachine(derived_vars=dv)

        # First check — the guard for ESCALATE should fire
        new_state = fsm.transition("READABLE")
        self.assertEqual(new_state, "ESCALATE")


class TestFullPath(unittest.TestCase):
    """Tests for complete FSM path: A → B → E → F → G → D → H → I → J → K → END."""

    def setUp(self):
        self.dv = DerivedVariables(
            dv_start_rx_RE_sph=-2.0, dv_start_rx_RE_cyl=-0.75,
            dv_start_rx_RE_axis=180,
            dv_start_rx_LE_sph=-1.75, dv_start_rx_LE_cyl=-0.50,
            dv_start_rx_LE_axis=170,
            dv_target_distance_va="6/6_target",
            dv_add_expected="None",  # No near workflow
        )

    def test_full_distance_path(self):
        """Walk through the complete distance refraction path."""
        fsm = FSMStateMachine(derived_vars=self.dv)
        path = ["A"]

        # State A → B: Distance baseline
        fsm.phase_state.chart_idx = 5  # At target chart
        state = fsm.transition("READABLE")
        path.append(state)
        self.assertEqual(state, "B")

        # State B → E: Coarse sphere RE
        fsm.phase_state.fog_remaining = 0.0
        fsm.phase_state.chart_idx = 5
        state = fsm.transition("READABLE")
        path.append(state)
        self.assertEqual(state, "E")

        # State E → F: JCC Axis RE (convergence via SAME)
        fsm.phase_state.axis_converged = True
        state = fsm.transition("SAME")
        path.append(state)
        self.assertEqual(state, "F")

        # State F → G: JCC Power RE (convergence via SAME streak)
        fsm.phase_state.cyl_converged = True
        state = fsm.transition("SAME")
        path.append(state)
        self.assertEqual(state, "G")

        # State G → D: Duochrome RE (balanced via EQUAL)
        fsm.phase_state.duochrome_balanced = True
        state = fsm.transition("EQUAL")
        path.append(state)
        self.assertEqual(state, "D")

        # State D → H: Coarse sphere LE
        fsm.phase_state.fog_remaining = 0.0
        fsm.phase_state.chart_idx = 5
        state = fsm.transition("READABLE")
        path.append(state)
        self.assertEqual(state, "H")

        # State H → I: JCC Axis LE
        fsm.phase_state.axis_converged = True
        state = fsm.transition("SAME")
        path.append(state)
        self.assertEqual(state, "I")

        # State I → J: JCC Power LE
        fsm.phase_state.cyl_converged = True
        state = fsm.transition("SAME")
        path.append(state)
        self.assertEqual(state, "J")

        # State J → K: Duochrome LE
        fsm.phase_state.duochrome_balanced = True
        state = fsm.transition("EQUAL")
        path.append(state)
        self.assertEqual(state, "K")

        # State K → END: Binocular balance (no near workflow)
        fsm.phase_state.balance_converged = True
        state = fsm.transition("SAME")
        path.append(state)
        self.assertEqual(state, "END")

        # Verify full path
        self.assertEqual(path, ["A", "B", "E", "F", "G", "D", "H", "I", "J", "K", "END"])

    def test_near_workflow_path(self):
        """K → P → Q → R → END when near ADD is needed."""
        dv = DerivedVariables(
            dv_start_rx_RE_sph=-1.0,
            dv_start_rx_LE_sph=-0.75,
            dv_target_distance_va="6/6_target",
            dv_add_expected="Likely",
            dv_near_test_required=True,
        )
        fsm = FSMStateMachine(derived_vars=dv)

        # Fast-forward to state K
        fsm.current_state = "K"
        fsm.current_eye = "BIN"
        fsm.phase_state.reset_for_new_state()

        # K → P (balance converged, ADD expected)
        fsm.phase_state.balance_converged = True
        state = fsm.transition("SAME")
        self.assertEqual(state, "P")

        # P → Q (near ADD RE converged)
        fsm.phase_state.add_converged = True
        state = fsm.transition("READABLE")
        self.assertEqual(state, "Q")

        # Q → R (near ADD LE converged)
        fsm.phase_state.add_converged = True
        state = fsm.transition("READABLE")
        self.assertEqual(state, "R")

        # R → END
        state = fsm.transition("TARGET_OK")
        self.assertEqual(state, "END")


class TestTimeouts(unittest.TestCase):
    """Tests for phase timeout behavior."""

    def setUp(self):
        self.dv = DerivedVariables(
            dv_start_rx_RE_sph=-2.0,
            dv_start_rx_LE_sph=-1.75,
            dv_expected_convergence_time="Fast",
        )

    def test_timeout_limit_values(self):
        """Verify timeout limits are read from calibration."""
        fsm = FSMStateMachine(derived_vars=self.dv)
        cal = fsm.calibration

        # State A uses DIST_BASELINE — check timeout
        # Note: DIST_BASELINE maps to timeout_coarse by default
        limit = fsm.get_timeout_limit()
        expected = cal.get("PHASE_TIMEOUTS", {}).get("timeout_coarse_fast", 24)
        self.assertEqual(limit, expected)

    def test_timeout_triggers_accept_best(self):
        """When step_count >= timeout, ACCEPT_BEST should advance state."""
        fsm = FSMStateMachine(derived_vars=self.dv)

        # Move to state B (COARSE_SPHERE)
        fsm.phase_state.chart_idx = 5
        fsm.transition("READABLE")  # A → B
        self.assertEqual(fsm.current_state, "B")

        # Simulate hitting timeout
        timeout = fsm.get_timeout_limit()
        fsm.phase_state.step_count = timeout - 1  # Next transition will trigger

        # This should trigger ACCEPT_BEST and advance to E
        state = fsm.transition("NOT_READABLE")
        self.assertIn(state, ["E", "ESCALATE"])  # Depending on timeout_action


class TestEntryActions(unittest.TestCase):
    """Tests for state entry actions."""

    def setUp(self):
        self.dv = DerivedVariables(
            dv_start_rx_RE_sph=-2.0,
            dv_start_rx_RE_cyl=-0.75,
            dv_start_rx_RE_axis=180,
            dv_start_rx_LE_sph=-1.75,
            dv_fogging_policy="Strong_Fog",
            dv_fogging_amount_D=1.0,
        )

    def test_fogging_applied_on_coarse_sphere(self):
        """Entering COARSE_SPHERE should apply fogging to SPH."""
        fsm = FSMStateMachine(derived_vars=self.dv)

        # Transition from A to B
        fsm.phase_state.chart_idx = 5
        fsm.transition("READABLE")

        self.assertEqual(fsm.current_state, "B")
        # Fogging should add +1.0D to RE_SPH
        # Start was -2.0, after fogging should be -2.0 + 1.0 = -1.0
        self.assertAlmostEqual(fsm.phase_state.re_sph, -1.0)
        self.assertAlmostEqual(fsm.phase_state.fog_remaining, 1.0)

    def test_jcc_axis_initialized(self):
        """Entering JCC_AXIS should set axis_step to start value."""
        fsm = FSMStateMachine(derived_vars=self.dv)

        # Fast-forward to E
        fsm._enter_state("E")
        self.assertEqual(fsm.current_state, "E")
        expected_step = fsm.calibration.get("AXIS_POLICY", {}).get("axis_start_step", 5)
        self.assertEqual(fsm.phase_state.axis_step, expected_step)
        self.assertEqual(fsm.phase_state.axis_reversal_count, 0)
        self.assertFalse(fsm.phase_state.axis_converged)


class TestStateSummary(unittest.TestCase):
    """Tests for state summary output."""

    def test_summary_structure(self):
        dv = DerivedVariables()
        fsm = FSMStateMachine(derived_vars=dv)
        summary = fsm.get_state_summary()

        self.assertIn("current_state", summary)
        self.assertIn("description", summary)
        self.assertIn("phase_type", summary)
        self.assertIn("eye", summary)
        self.assertIn("step_count", summary)
        self.assertIn("is_terminal", summary)
        self.assertIn("question", summary)
        self.assertIn("allowed_responses", summary)
        self.assertIn("lens_values", summary)

    def test_final_rx(self):
        dv = DerivedVariables(
            dv_start_rx_RE_sph=-2.5,
            dv_start_rx_LE_sph=-1.75,
        )
        fsm = FSMStateMachine(derived_vars=dv)
        rx = fsm.get_final_rx()

        self.assertIn("RE", rx)
        self.assertIn("LE", rx)
        self.assertAlmostEqual(rx["RE"]["sph"], -2.5)
        self.assertAlmostEqual(rx["LE"]["sph"], -1.75)

    def test_terminal_detection(self):
        dv = DerivedVariables()
        fsm = FSMStateMachine(derived_vars=dv)
        self.assertFalse(fsm.is_terminal)

        fsm.current_state = "END"
        self.assertTrue(fsm.is_terminal)

        fsm.current_state = "ESCALATE"
        self.assertTrue(fsm.is_terminal)


class TestStepLog(unittest.TestCase):
    """Tests for step logging."""

    def test_log_records_steps(self):
        dv = DerivedVariables()
        fsm = FSMStateMachine(derived_vars=dv)
        fsm.transition("READABLE")
        self.assertEqual(len(fsm.step_log), 1)
        entry = fsm.step_log[0]
        self.assertEqual(entry["state"], "A")
        self.assertEqual(entry["response"], "READABLE")

    def test_log_accumulates(self):
        dv = DerivedVariables()
        fsm = FSMStateMachine(derived_vars=dv)
        for _ in range(5):
            fsm.transition("NOT_READABLE")
        self.assertEqual(len(fsm.step_log), 5)


class TestEscalation(unittest.TestCase):
    """Tests for escalation transitions."""

    def test_escalate_on_optom_review(self):
        dv = DerivedVariables(dv_requires_optom_review=True)
        fsm = FSMStateMachine(derived_vars=dv)

        state = fsm.transition("READABLE")
        self.assertEqual(state, "ESCALATE")
        self.assertTrue(fsm.is_terminal)

    def test_terminal_stays_terminal(self):
        dv = DerivedVariables()
        fsm = FSMStateMachine(derived_vars=dv)
        fsm.current_state = "END"

        state = fsm.transition("READABLE")
        self.assertEqual(state, "END")


class TestBackwardCompatAlias(unittest.TestCase):
    """Test that StateMachine alias works for legacy code."""

    def test_alias_import(self):
        from core.state_machine import StateMachine
        self.assertIs(StateMachine, FSMStateMachine)


if __name__ == "__main__":
    unittest.main()
