"""
FSM Session: Bridges the FSM state machine with phoropter hardware control.

This is the production orchestrator for the FSMv2 workflow:
  1. Takes patient intake data → computes DerivedVariables
  2. Initializes FSMStateMachine with DVs
  3. On each patient response: runs FSM transition → syncs lens values to phoropter
  4. Returns the next question/state for the UI

Replaces the hardcoded InteractiveSession for FSMv2-based tests.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from .derived_variables import DerivedVariables, compute_derived_variables, load_calibration
from .state_machine import FSMStateMachine, PhaseState, normalize_response
from .patient_input import PatientInput
from .ar_lenso_input import ARInput, LensoInput
from .phoropter_client import PhoropterClient

logger = logging.getLogger(__name__)


# Chart ladder sizes for the phoropter display
CHART_SIZES = ["400", "200_150", "100_80", "70_60_50", "40_30_25", "20_20_20"]

# Phase type → occluder mapping
PHASE_OCCLUDER = {
    "DIST_BASELINE": "BINO",
    "COARSE_SPHERE": None,   # set per eye below
    "JCC_AXIS": None,
    "JCC_POWER": None,
    "DUOCHROME": None,
    "BINOC_BALANCE": "BINO",
    "NEAR_ADD": None,
    "NEAR_BINOC": "BINO",
}


class FSMSession:
    """
    End-to-end FSM session that controls the phoropter.

    Usage:
        session = FSMSession(base_url, phoropter_id)
        result = session.initialize(patient, ar, lenso)
        # result contains derived_variables, start_rx, first question

        while not session.is_complete:
            result = session.respond(patient_response)
            # result contains next question, lens values, state info
    """

    def __init__(self, base_url: str, phoropter_id: str):
        self.phoropter = PhoropterClient(base_url, phoropter_id)
        self.phoropter_id = phoropter_id
        self.fsm: Optional[FSMStateMachine] = None
        self.dv: Optional[DerivedVariables] = None
        self.session_start_time: Optional[datetime] = None
        self.session_end_time: Optional[datetime] = None
        self._initialized = False

    @property
    def is_complete(self) -> bool:
        return self.fsm is not None and self.fsm.is_terminal

    def initialize(
        self,
        patient: PatientInput,
        ar: ARInput,
        lenso: LensoInput,
        calibration: Optional[dict] = None,
    ) -> dict:
        """
        Initialize session: compute DVs, create FSM, set initial power on phoropter.

        Returns dict with derived_variables, start_rx, and first question.
        """
        self.session_start_time = datetime.now()

        # Compute derived variables
        if calibration is None:
            calibration = load_calibration()
        self.dv = compute_derived_variables(patient, ar, lenso, calibration)

        # Create FSM
        self.fsm = FSMStateMachine(derived_vars=self.dv)

        # Set initial power on phoropter
        ps = self.fsm.phase_state
        self.phoropter.reset()
        self.phoropter.set_power(
            re_sph=ps.re_sph, re_cyl=ps.re_cyl, re_axis=ps.re_axis,
            le_sph=ps.le_sph, le_cyl=ps.le_cyl, le_axis=ps.le_axis,
            occluder="BINO",
        )

        # Show first chart for distance baseline
        self._show_chart_for_state()

        self._initialized = True
        return self._build_response()

    def respond(self, response: str) -> dict:
        """
        Process a patient response: run FSM transition, sync phoropter, return next state.

        Args:
            response: Patient response (e.g. 'READABLE', 'BETTER_1', 'RED_CLEARER')

        Returns:
            Dict with state info, lens values, next question
        """
        if not self._initialized or self.fsm is None:
            return {"error": "Session not initialized"}

        if self.fsm.is_terminal:
            return self._build_response()

        # Snapshot lens values before transition
        ps = self.fsm.phase_state
        prev_re = {"sph": ps.re_sph, "cyl": ps.re_cyl, "axis": ps.re_axis, "add": ps.re_add}
        prev_le = {"sph": ps.le_sph, "cyl": ps.le_cyl, "axis": ps.le_axis, "add": ps.le_add}
        prev_state = self.fsm.current_state

        # Run FSM transition (this applies clinical adjustments internally)
        new_state = self.fsm.transition(response)

        # Sync updated lens values to phoropter
        self._sync_phoropter(prev_state, new_state, prev_re, prev_le)

        # Show appropriate chart if state changed
        if new_state != prev_state:
            self._show_chart_for_state()

        # Check for completion
        if self.fsm.is_terminal:
            self.session_end_time = datetime.now()

        return self._build_response()

    def _sync_phoropter(self, prev_state: str, new_state: str, prev_re: dict, prev_le: dict):
        """Sync the FSM's current lens values to the phoropter hardware."""
        ps = self.fsm.phase_state
        eye = self.fsm.current_eye
        phase_type = self.fsm.current_phase_type

        # Determine occluder based on eye
        if eye == "RE":
            occluder = "Left_Occluded"
        elif eye == "LE":
            occluder = "Right_Occluded"
        else:
            occluder = "BINO"

        # Check if lens values actually changed
        re_changed = (
            ps.re_sph != prev_re["sph"] or
            ps.re_cyl != prev_re["cyl"] or
            ps.re_axis != prev_re["axis"] or
            ps.re_add != prev_re["add"]
        )
        le_changed = (
            ps.le_sph != prev_le["sph"] or
            ps.le_cyl != prev_le["cyl"] or
            ps.le_axis != prev_le["axis"] or
            ps.le_add != prev_le["add"]
        )
        state_changed = prev_state != new_state

        # Only send to phoropter if something changed
        if re_changed or le_changed or state_changed:
            self.phoropter.set_power(
                re_sph=ps.re_sph, re_cyl=ps.re_cyl, re_axis=ps.re_axis,
                le_sph=ps.le_sph, le_cyl=ps.le_cyl, le_axis=ps.le_axis,
                re_add=ps.re_add, le_add=ps.le_add,
                occluder=occluder,
            )
            logger.info(
                f"Synced phoropter: RE({ps.re_sph}/{ps.re_cyl}/{ps.re_axis}) "
                f"LE({ps.le_sph}/{ps.le_cyl}/{ps.le_axis}) occ={occluder}"
            )

    def _show_chart_for_state(self):
        """Display the appropriate chart for the current FSM state."""
        phase_type = self.fsm.current_phase_type
        ps = self.fsm.phase_state

        if phase_type in ("DIST_BASELINE", "COARSE_SPHERE"):
            # Show distance VA chart at current chart index
            idx = min(ps.chart_idx, len(CHART_SIZES) - 1)
            self.phoropter.set_chart("snellen", size=CHART_SIZES[idx])
        elif phase_type == "DUOCHROME":
            self.phoropter.set_chart("red_green")
        elif phase_type in ("JCC_AXIS", "JCC_POWER"):
            self.phoropter.set_chart("cross_cylinder")
            # Set JCC eye mode
            eye = self.fsm.current_eye
            jcc_mode = "R" if eye == "RE" else "L"
            self.phoropter.jcc_control(jcc_mode)
        elif phase_type in ("NEAR_ADD", "NEAR_BINOC"):
            self.phoropter.set_chart("near_chart", tab="Chart5")
        elif phase_type == "BINOC_BALANCE":
            self.phoropter.set_chart("snellen")

    def _build_response(self) -> dict:
        """Build the response dict for the API."""
        fsm = self.fsm
        ps = fsm.phase_state
        dv = self.dv

        result = {
            "state": fsm.current_state,
            "description": fsm.current_description,
            "phase_type": fsm.current_phase_type,
            "eye": fsm.current_eye,
            "step_count": ps.step_count,
            "is_terminal": fsm.is_terminal,
            "question": fsm.get_question(),
            "allowed_responses": fsm.get_allowed_responses(),
            "chart_type": fsm.get_chart_type(),
            "timeout_limit": fsm.get_timeout_limit(),
            "lens_values": fsm.get_final_rx(),
            "va": {
                "re": ps.va_re,
                "le": ps.va_le,
                "bin": ps.va_bin,
            },
        }

        if fsm.is_terminal:
            result["final_rx"] = fsm.get_final_rx()
            result["step_log"] = fsm.step_log

        return result

    def get_state_summary(self) -> dict:
        """Get full state summary for debugging / status endpoint."""
        if not self._initialized or self.fsm is None:
            return {"error": "Not initialized"}
        return {
            **self._build_response(),
            "derived_variables": self.dv.to_dict() if self.dv else {},
            "state_history": self.fsm.state_history,
        }
