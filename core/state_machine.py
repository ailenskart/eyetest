"""
State Machine: Table-driven FSM for eye test orchestration.

Replaces the hardcoded if/elif chain with a YAML-driven transition table.
Each state defines:
  - phase_type: what clinical test to perform
  - eye: which eye (RE/LE/BIN)
  - entry_actions: setup steps on entering the state
  - transitions: guard conditions evaluated in order, first match determines next state
  - timeout_bucket / timeout_action: safety limits

The FSM is parameterized by DerivedVariables (computed before test starts)
and calibration.yaml thresholds, so behavior adapts per patient without code changes.
"""
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
import yaml
import logging

from .derived_variables import DerivedVariables
from .context import RowContext

logger = logging.getLogger(__name__)


# =============================================================================
# Response Enum Normalization
# =============================================================================

class ResponseType(str, Enum):
    # READABILITY
    READABLE = "READABLE"
    NOT_READABLE = "NOT_READABLE"
    BLURRY = "BLURRY"
    # COMPARE_1_2
    BETTER_1 = "BETTER_1"
    BETTER_2 = "BETTER_2"
    SAME = "SAME"
    CANT_TELL = "CANT_TELL"
    # COLOR_CHOICE
    RED_CLEARER = "RED_CLEARER"
    GREEN_CLEARER = "GREEN_CLEARER"
    EQUAL = "EQUAL"
    # TOP_BOTTOM
    TOP_CLEARER = "TOP_CLEARER"
    BOTTOM_CLEARER = "BOTTOM_CLEARER"
    # NEAR
    TARGET_OK = "TARGET_OK"
    NOT_CLEAR = "NOT_CLEAR"


def load_response_types(config_dir: Path) -> dict:
    """Load response type definitions with legacy mapping."""
    with open(config_dir / "response_types.yaml") as f:
        data = yaml.safe_load(f)
    return data.get("response_types", {})


def normalize_response(raw_response: str, response_types: dict) -> str:
    """
    Normalize a raw patient response to canonical enum value.
    Checks all legacy mappings across all response types.
    Returns the canonical value or the raw response if no mapping found.
    """
    if not raw_response:
        return ""

    # Check if already canonical
    for rtype_name, rtype_def in response_types.items():
        if raw_response in rtype_def.get("values", []):
            return raw_response

    # Check legacy mappings
    for rtype_name, rtype_def in response_types.items():
        legacy = rtype_def.get("legacy_mapping", {})
        if raw_response in legacy:
            return legacy[raw_response]

    return raw_response


# =============================================================================
# Phase State: Runtime state for current phase
# =============================================================================

@dataclass
class PhaseState:
    """Runtime state for the current phase within the FSM."""

    # Phase step counter (resets on state entry)
    step_count: int = 0

    # Current lens values being adjusted
    re_sph: float = 0.0
    re_cyl: float = 0.0
    re_axis: float = 0.0
    re_add: float = 0.0
    le_sph: float = 0.0
    le_cyl: float = 0.0
    le_axis: float = 0.0
    le_add: float = 0.0

    # Coarse sphere state
    fog_remaining: float = 0.0       # Remaining fog to clear (D)
    fog_phase: str = "fogging"       # fogging / clearing / cleared

    # JCC axis state
    axis_step: int = 5               # Current axis step (degrees)
    axis_reversal_count: int = 0     # Number of reversals
    prev_axis_response: str = ""     # Previous response for reversal detection
    axis_converged: bool = False

    # JCC power state
    cyl_cumulative_change: float = 0.0  # Cumulative CYL change for SE compensation
    same_streak: int = 0               # Consecutive SAME/CANT_TELL responses
    cyl_converged: bool = False

    # Duochrome state
    duo_iter: int = 0                 # Total duochrome iterations
    duo_flip: int = 0                 # Direction changes (red→green or green→red)
    prev_duo_response: str = ""       # For flip tracking
    equal_streak: int = 0             # Consecutive EQUAL responses
    duochrome_balanced: bool = False

    # Binocular balance state
    balance_same_streak: int = 0
    balance_converged: bool = False

    # Near ADD state
    add_converged: bool = False

    # Chart state
    chart_idx: int = 0               # Current chart in the ladder

    # Comparison counter (total interactions within this state)
    comparisons: int = 0

    def reset_for_new_state(self):
        """Reset phase-local counters for a new state entry."""
        self.step_count = 0
        self.comparisons = 0
        self.fog_remaining = 0.0
        self.fog_phase = "fogging"
        self.axis_step = 5
        self.axis_reversal_count = 0
        self.prev_axis_response = ""
        self.axis_converged = False
        self.cyl_cumulative_change = 0.0
        self.same_streak = 0
        self.cyl_converged = False
        self.duo_iter = 0
        self.duo_flip = 0
        self.prev_duo_response = ""
        self.equal_streak = 0
        self.duochrome_balanced = False
        self.balance_same_streak = 0
        self.balance_converged = False
        self.add_converged = False


# =============================================================================
# FSM State Machine
# =============================================================================

@dataclass
class FSMStateMachine:
    """
    Table-driven finite state machine for the eye test.

    The FSM loads its transition table from fsm_transitions.yaml and
    uses DerivedVariables to parameterize all decisions.
    Phase modules (spherical, cylinder_axis, cylinder_power, duochrome,
    binocular_balance) implement the clinical logic within each state.
    """

    # Current state
    current_state: str = "A"
    current_eye: str = "BIN"

    # Configuration (loaded from YAML)
    transitions_config: dict = field(default_factory=dict)
    phase_ui_map: dict = field(default_factory=dict)
    response_types: dict = field(default_factory=dict)
    calibration: dict = field(default_factory=dict)

    # Derived variables (computed before test starts)
    derived_vars: DerivedVariables = field(default_factory=DerivedVariables)

    # Runtime phase state
    phase_state: PhaseState = field(default_factory=PhaseState)

    # History
    state_history: List[str] = field(default_factory=list)
    step_log: List[dict] = field(default_factory=list)

    # Terminal states
    _terminal_states: set = field(default_factory=lambda: {"END", "ESCALATE"})

    def __post_init__(self):
        """Load configuration if not provided."""
        if not self.transitions_config:
            self.load_config()
        # Initialize lens values from derived variables
        self._init_lens_values()

    def load_config(self, config_dir: Optional[str] = None):
        """Load all configuration files."""
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        else:
            config_dir = Path(config_dir)

        with open(config_dir / "fsm_transitions.yaml") as f:
            data = yaml.safe_load(f)
            self.transitions_config = data.get("states", {})

        with open(config_dir / "phase_ui_map.yaml") as f:
            data = yaml.safe_load(f)
            self.phase_ui_map = data.get("phases", {})

        self.response_types = load_response_types(config_dir)

        with open(config_dir / "calibration.yaml") as f:
            self.calibration = yaml.safe_load(f)

    def _init_lens_values(self):
        """Initialize lens values from derived variables start Rx."""
        dv = self.derived_vars
        self.phase_state.re_sph = dv.dv_start_rx_RE_sph
        self.phase_state.re_cyl = dv.dv_start_rx_RE_cyl
        self.phase_state.re_axis = dv.dv_start_rx_RE_axis
        self.phase_state.le_sph = dv.dv_start_rx_LE_sph
        self.phase_state.le_cyl = dv.dv_start_rx_LE_cyl
        self.phase_state.le_axis = dv.dv_start_rx_LE_axis

    # -------------------------------------------------------------------------
    # Core FSM Interface
    # -------------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        """Check if FSM has reached a terminal state."""
        return self.current_state in self._terminal_states

    @property
    def current_state_config(self) -> dict:
        """Get configuration for the current state."""
        return self.transitions_config.get(self.current_state, {})

    @property
    def current_phase_type(self) -> str:
        """Get the phase type for the current state."""
        return self.current_state_config.get("phase_type", "")

    @property
    def current_description(self) -> str:
        """Get human-readable description of current state."""
        return self.current_state_config.get("description", self.current_state)

    def get_ui_config(self) -> dict:
        """Get the UI configuration for the current phase type."""
        phase_type = self.current_phase_type
        return self.phase_ui_map.get(phase_type, {})

    def get_question(self) -> str:
        """Get the question to ask the patient in the current phase."""
        ui = self.get_ui_config()
        return ui.get("question", "")

    def get_allowed_responses(self) -> List[str]:
        """Get allowed response values for the current phase."""
        ui = self.get_ui_config()
        return ui.get("allowed_values", [])

    def get_response_type(self) -> str:
        """Get the response type enum name for the current phase."""
        ui = self.get_ui_config()
        return ui.get("response_type", "")

    def get_chart_type(self) -> str:
        """Get the chart type for the current phase."""
        ui = self.get_ui_config()
        return ui.get("chart_type", "")

    def get_stimulus_type(self) -> str:
        """Get the stimulus type for the current phase."""
        ui = self.get_ui_config()
        return ui.get("stimulus_type", "")

    def get_timeout_limit(self) -> int:
        """Get the timeout (max step count) for the current state."""
        state_cfg = self.current_state_config
        bucket = state_cfg.get("timeout_bucket")
        if not bucket:
            return 999  # No timeout

        phase_type = self.current_phase_type
        convergence = self.derived_vars.dv_expected_convergence_time.lower()
        timeouts = self.calibration.get("PHASE_TIMEOUTS", {})

        # Map phase type to timeout category
        if phase_type == "COARSE_SPHERE":
            key = f"timeout_coarse_{convergence}"
        elif phase_type in ("JCC_AXIS", "JCC_POWER"):
            key = f"timeout_jcc_{convergence}"
        elif phase_type == "DUOCHROME":
            key = f"timeout_duochrome_{convergence}"
        elif phase_type == "BINOC_BALANCE":
            key = f"timeout_bino_{convergence}"
        elif phase_type in ("NEAR_ADD", "NEAR_BINOC"):
            key = f"timeout_near_{convergence}"
        else:
            key = f"timeout_coarse_{convergence}"

        return timeouts.get(key, 30)

    # -------------------------------------------------------------------------
    # State Transition
    # -------------------------------------------------------------------------

    def transition(self, response: str) -> str:
        """
        Process a patient response and transition to the next state.

        Args:
            response: Normalized response value (e.g., READABLE, BETTER_1)

        Returns:
            The new state ID after transition
        """
        if self.is_terminal:
            return self.current_state

        # Normalize response
        response = normalize_response(response, self.response_types)

        # Increment counters
        self.phase_state.step_count += 1
        self.phase_state.comparisons += 1

        # Process the response: apply clinical adjustments to lens values
        self._process_response(response)

        # Log the step
        self._log_step(response)

        # Check timeout
        timeout_limit = self.get_timeout_limit()
        if self.phase_state.step_count >= timeout_limit:
            timeout_action = self.current_state_config.get(
                "timeout_action", "ESCALATE"
            )
            if timeout_action == "ACCEPT_BEST":
                logger.warning(
                    f"Phase timeout in state {self.current_state} "
                    f"after {self.phase_state.step_count} steps. "
                    f"Accepting best values."
                )
                # Accept current values and move to next logical state
                return self._accept_best_transition()
            else:
                logger.warning(
                    f"Phase timeout in state {self.current_state}. Escalating."
                )
                return self._enter_state("ESCALATE")

        # Evaluate guard conditions
        transitions = self.current_state_config.get("transitions", [])
        context = self._build_guard_context(response)

        for rule in transitions:
            guard = rule.get("guard", "true")
            if self._evaluate_guard(guard, context):
                next_state = rule.get("next_state", self.current_state)
                if next_state != self.current_state:
                    return self._enter_state(next_state)
                else:
                    # Stay in same state (loop)
                    return self.current_state

        # No guard matched — stay in current state
        logger.debug(
            f"No guard matched for response '{response}' "
            f"in state {self.current_state}"
        )
        return self.current_state

    def _enter_state(self, new_state: str) -> str:
        """Enter a new state, resetting phase-local counters."""
        old_state = self.current_state
        self.state_history.append(old_state)
        self.current_state = new_state

        # Update eye
        state_cfg = self.transitions_config.get(new_state, {})
        self.current_eye = state_cfg.get("eye", "BIN")

        # Reset phase-local counters
        self.phase_state.reset_for_new_state()

        # Execute entry actions
        entry_actions = state_cfg.get("entry_actions", [])
        self._execute_entry_actions(entry_actions, new_state)

        logger.info(
            f"State transition: {old_state} -> {new_state} "
            f"({state_cfg.get('description', '')})"
        )

        return new_state

    def _accept_best_transition(self) -> str:
        """
        When timeout hits with ACCEPT_BEST, determine the next state
        as if the phase converged normally.
        """
        state = self.current_state
        transitions = self.current_state_config.get("transitions", [])

        # Find the first transition that leads to a DIFFERENT state
        # (convergence guard or similar)
        for rule in transitions:
            next_state = rule.get("next_state", state)
            if next_state != state and next_state != "ESCALATE":
                return self._enter_state(next_state)

        # Fallback: escalate if no forward transition found
        return self._enter_state("ESCALATE")

    # -------------------------------------------------------------------------
    # Response Processing: Clinical Adjustments per Phase
    # -------------------------------------------------------------------------

    def _process_response(self, response: str):
        """
        Apply clinical adjustments to lens values based on the patient response.
        This is the core intelligence layer — it modifies PhaseState based on
        the phase type, response, and derived variables / calibration params.
        """
        phase_type = self.current_phase_type
        dv = self.derived_vars
        ps = self.phase_state
        cal = self.calibration

        if phase_type == "DIST_BASELINE":
            self._process_dist_baseline(response)
        elif phase_type == "COARSE_SPHERE":
            self._process_coarse_sphere(response)
        elif phase_type == "JCC_AXIS":
            self._process_jcc_axis(response)
        elif phase_type == "JCC_POWER":
            self._process_jcc_power(response)
        elif phase_type == "DUOCHROME":
            self._process_duochrome(response)
        elif phase_type == "BINOC_BALANCE":
            self._process_binoc_balance(response)
        elif phase_type == "NEAR_ADD":
            self._process_near_add(response)
        elif phase_type == "NEAR_BINOC":
            self._process_near_binoc(response)

    def _process_dist_baseline(self, response: str):
        """
        Distance Baseline (State A): Chart ladder progression.
        Advance chart on READABLE, stay on NOT_READABLE/BLURRY.
        """
        ps = self.phase_state
        if response == "READABLE":
            ps.chart_idx += 1

    def _process_coarse_sphere(self, response: str):
        """
        Coarse Sphere (States B, D): Sphere refinement with fogging protocol.

        Logic:
        - BLURRY/NOT_READABLE: add minus SPH (step from calibration)
        - READABLE:
          - If fog_remaining > 0: clear fog step-by-step
          - If fog cleared: check VA target for convergence
        - Drift detection: escalate if delta from start exceeds max
        """
        ps = self.phase_state
        dv = self.derived_vars
        cal = self.calibration
        eye = self.current_eye

        # Get sphere step from step_size_policy
        step_cfg = cal.get("STEP_POLICY", {})
        policy = dv.dv_step_size_policy.lower()
        sph_step = step_cfg.get(f"{policy}_sph_step", 0.25)

        if response in ("BLURRY", "NOT_READABLE"):
            # Add minus power (more myopic correction)
            if eye == "RE":
                ps.re_sph -= sph_step
            else:
                ps.le_sph -= sph_step

        elif response == "READABLE":
            if ps.fog_remaining > 0:
                # Clear fog step by step
                clearance = dv.dv_fogging_clearance_mode
                clear_step = self._get_fog_clear_step(clearance, ps.fog_remaining)

                if eye == "RE":
                    ps.re_sph -= clear_step
                else:
                    ps.le_sph -= clear_step

                ps.fog_remaining = max(0.0, ps.fog_remaining - clear_step)
                ps.fog_remaining = round(ps.fog_remaining, 2)

                if ps.fog_remaining <= 0:
                    ps.fog_phase = "cleared"
                else:
                    ps.fog_phase = "clearing"
            # If fog cleared and READABLE, VA is likely at/near target

        # Drift detection
        if eye == "RE":
            delta = abs(ps.re_sph - dv.dv_start_rx_RE_sph)
        else:
            delta = abs(ps.le_sph - dv.dv_start_rx_LE_sph)

        if delta > dv.dv_max_delta_from_start_sph and dv.dv_anomaly_watch:
            logger.warning(
                f"Drift anomaly: {eye} SPH delta {delta:.2f}D "
                f"exceeds max {dv.dv_max_delta_from_start_sph}D"
            )

    def _get_fog_clear_step(self, clearance_mode: str, fog_remaining: float) -> float:
        """Determine fog clearance step size based on mode."""
        if clearance_mode == "StepDown_0.25":
            return 0.25
        elif clearance_mode == "StepDown_0.50_then_0.25":
            # Start with 0.50 steps, switch to 0.25 when remaining ≤ 0.50
            return 0.50 if fog_remaining > 0.50 else 0.25
        elif clearance_mode == "Early_Stop_if_Risk":
            # Stop clearing early — accept current as best
            return fog_remaining  # Clear all remaining in one step
        else:
            return 0.25

    def _process_jcc_axis(self, response: str):
        """
        JCC Axis (States E, H): Axis refinement with reversal detection.

        Logic:
        - BETTER_1: adjust axis by +axis_step
        - BETTER_2: adjust axis by -axis_step
        - Reversal (direction change): halve step (5°→3°→1°)
        - SAME/CANT_TELL: axis_converged = True
        """
        ps = self.phase_state
        dv = self.derived_vars
        cal = self.calibration
        eye = self.current_eye
        axis_cfg = cal.get("AXIS_POLICY", {})

        if response in ("SAME", "CANT_TELL"):
            ps.axis_converged = True
            return

        if response in ("BETTER_1", "BETTER_2"):
            # Reversal detection
            if ps.prev_axis_response and ps.prev_axis_response != response:
                ps.axis_reversal_count += 1
                # Reduce step on reversal
                if ps.axis_reversal_count == 1:
                    ps.axis_step = axis_cfg.get("axis_reversal_step_1", 3)
                elif ps.axis_reversal_count >= 2:
                    ps.axis_step = axis_cfg.get("axis_reversal_step_2", 1)

                # Check convergence: if step ≤ tolerance, converged
                if ps.axis_step <= dv.dv_axis_tolerance_deg:
                    ps.axis_converged = True

            ps.prev_axis_response = response

            # Apply axis adjustment
            direction = 1 if response == "BETTER_1" else -1
            step = ps.axis_step * direction

            if eye == "RE":
                ps.re_axis = (ps.re_axis + step) % 180
                if ps.re_axis == 0:
                    ps.re_axis = 180
            else:
                ps.le_axis = (ps.le_axis + step) % 180
                if ps.le_axis == 0:
                    ps.le_axis = 180

    def _process_jcc_power(self, response: str):
        """
        JCC Power (States F, I): Cylinder power refinement with SE compensation.

        Logic:
        - BETTER_1: increase CYL by +cyl_step (less negative)
        - BETTER_2: decrease CYL by -cyl_step (more negative)
        - SE compensation: for every 0.50D cumulative CYL change, adjust SPH ±0.25D
        - SAME/CANT_TELL: increment same_streak → converged when streak ≥ threshold
        """
        ps = self.phase_state
        dv = self.derived_vars
        cal = self.calibration
        eye = self.current_eye

        step_cfg = cal.get("STEP_POLICY", {})
        policy = dv.dv_step_size_policy.lower()
        cyl_step = step_cfg.get(f"{policy}_cyl_step", 0.25)

        if response in ("SAME", "CANT_TELL"):
            ps.same_streak += 1
            if ps.same_streak >= dv.dv_jcc_power_same_required:
                ps.cyl_converged = True
            return

        # Reset same_streak on non-SAME response
        ps.same_streak = 0

        if response in ("BETTER_1", "BETTER_2"):
            # BETTER_1 = more plus CYL (less negative), BETTER_2 = more minus CYL
            direction = 1 if response == "BETTER_1" else -1
            delta_cyl = cyl_step * direction

            if eye == "RE":
                ps.re_cyl += delta_cyl
            else:
                ps.le_cyl += delta_cyl

            # Track cumulative CYL change for SE compensation
            ps.cyl_cumulative_change += delta_cyl

            # Spherical equivalent (SE) compensation:
            # For every 0.50D CYL change, compensate SPH by ±0.25D
            # (half the CYL change in opposite direction)
            if abs(ps.cyl_cumulative_change) >= 0.50:
                se_adjust = -0.25 if ps.cyl_cumulative_change > 0 else 0.25
                if eye == "RE":
                    ps.re_sph += se_adjust
                else:
                    ps.le_sph += se_adjust
                # Reset cumulative tracker (keep remainder)
                ps.cyl_cumulative_change -= 0.50 if ps.cyl_cumulative_change > 0 else -0.50

    def _process_duochrome(self, response: str):
        """
        Duochrome (States G, J): Red-green balance with flip counting.

        Logic:
        - RED_CLEARER: SPH += red_step (-0.25D, more minus)
        - GREEN_CLEARER: SPH += green_step (+0.25D, more plus)
        - EQUAL/CANT_TELL: increment equal_streak → balanced when streak ≥ confirmations
        - Flip detection (RED→GREEN or GREEN→RED): increment duo_flip
        - Convergence: equal_streak ≥ threshold OR duo_flip ≥ max_flips
        - Apply endpoint bias at convergence
        """
        ps = self.phase_state
        dv = self.derived_vars
        cal = self.calibration
        eye = self.current_eye
        duo_cfg = cal.get("DUOCHROME", {})

        ps.duo_iter += 1

        if response in ("EQUAL", "CANT_TELL"):
            ps.equal_streak += 1
            equal_needed = duo_cfg.get("duochrome_equal_confirmations", 2)
            if ps.equal_streak >= equal_needed:
                ps.duochrome_balanced = True
                self._apply_endpoint_bias(eye)
            return

        # Reset equal streak on non-EQUAL response
        ps.equal_streak = 0

        if response in ("RED_CLEARER", "GREEN_CLEARER"):
            # Flip detection
            if ps.prev_duo_response and ps.prev_duo_response != response:
                ps.duo_flip += 1

            ps.prev_duo_response = response

            # Check max flips guard
            if ps.duo_flip >= dv.dv_duochrome_max_flips:
                ps.duochrome_balanced = True
                self._apply_endpoint_bias(eye)
                return

            # Apply sphere adjustment
            if response == "RED_CLEARER":
                delta = duo_cfg.get("duochrome_red_step", -0.25)
            else:
                delta = duo_cfg.get("duochrome_green_step", 0.25)

            if eye == "RE":
                ps.re_sph += delta
            else:
                ps.le_sph += delta

    def _apply_endpoint_bias(self, eye: str):
        """Apply endpoint bias (undercorrect/overcorrect) at duochrome convergence."""
        dv = self.derived_vars
        cal = self.calibration
        ps = self.phase_state
        bias = dv.dv_endpoint_bias_policy
        eb_cfg = cal.get("ENDPOINT_BIAS", {})

        if bias == "Undercorrect":
            # Slight plus bias (less minus)
            delta = eb_cfg.get("undercorrect_step", 0.25)
        elif bias == "Overcorrect":
            # Slight minus bias (more minus)
            delta = -eb_cfg.get("overcorrect_step", 0.25)
        else:
            return  # Neutral — no bias

        if eye == "RE":
            ps.re_sph += delta
        else:
            ps.le_sph += delta

        logger.info(f"Applied endpoint bias: {bias} ({delta:+.2f}D) to {eye}")

    def _process_binoc_balance(self, response: str):
        """
        Binocular Balance (State K): Balance sphere between eyes.

        Logic:
        - TOP_CLEARER: RE SPH += balance_step (add plus to weaker eye)
        - BOTTOM_CLEARER: LE SPH += balance_step
        - SAME/CANT_TELL: increment same_streak → converged when streak ≥ threshold
        """
        ps = self.phase_state
        cal = self.calibration
        bino_cfg = cal.get("BINOC_BALANCE", {})
        step = bino_cfg.get("bino_balance_step", 0.25)
        same_needed = bino_cfg.get("bino_balance_same_required", 1)

        if response in ("SAME", "CANT_TELL"):
            ps.balance_same_streak += 1
            if ps.balance_same_streak >= same_needed:
                ps.balance_converged = True
            return

        # Reset same streak
        ps.balance_same_streak = 0

        if response == "TOP_CLEARER":
            # Top is RE — RE is clearer, so add plus to LE to balance
            ps.le_sph += step
        elif response == "BOTTOM_CLEARER":
            # Bottom is LE — LE is clearer, so add plus to RE to balance
            ps.re_sph += step

    def _process_near_add(self, response: str):
        """
        Near ADD (States P, Q): Determine reading addition.

        Logic:
        - BLURRY/NOT_READABLE: increment ADD by near_add_step (+0.25D)
        - READABLE: add_converged = True
        """
        ps = self.phase_state
        cal = self.calibration
        eye = self.current_eye
        near_cfg = cal.get("NEAR_WORKFLOW", {})
        add_step = near_cfg.get("near_add_step", 0.25)

        if response in ("BLURRY", "NOT_READABLE"):
            if eye == "RE":
                ps.re_add += add_step
            else:
                ps.le_add += add_step
        elif response == "READABLE":
            ps.add_converged = True

    def _process_near_binoc(self, response: str):
        """
        Near Binocular Verify (State R): Verify binocular near vision.

        Logic:
        - TARGET_OK: test complete
        - NOT_CLEAR: increment both ADDs by step
        """
        ps = self.phase_state
        cal = self.calibration
        near_cfg = cal.get("NEAR_WORKFLOW", {})
        add_step = near_cfg.get("near_add_step", 0.25)

        if response == "NOT_CLEAR":
            ps.re_add += add_step
            ps.le_add += add_step

    # -------------------------------------------------------------------------
    # Guard Evaluation
    # -------------------------------------------------------------------------

    def _build_guard_context(self, response: str) -> dict:
        """Build the context dictionary used by guard condition evaluation."""
        dv = self.derived_vars
        ps = self.phase_state
        cal = self.calibration

        # Determine current VA (simplified — uses chart index as proxy)
        charts = cal.get("CHARTS", {})
        chart_list = [charts.get(f"dist_chart_{i}", "") for i in range(1, 7)]

        # Target chart index
        if dv.dv_target_distance_va == "6/6_target":
            target_chart = cal.get("DISTANCE_TARGET", {}).get(
                "distance_target_6_6_chart", "20_20_20"
            )
        else:
            target_chart = cal.get("DISTANCE_TARGET", {}).get(
                "distance_target_6_9_chart", "40_30_25"
            )

        target_chart_idx = -1
        for i, c in enumerate(chart_list):
            if c == target_chart:
                target_chart_idx = i
                break

        # Comparison limit
        limit = self.get_timeout_limit()

        return {
            # Response
            "response": response,

            # Phase counters
            "step_count": ps.step_count,
            "comparisons": ps.comparisons,
            "chart_idx": ps.chart_idx,
            "target_chart_idx": target_chart_idx,
            "limit": limit,

            # Convergence flags
            "axis_converged": ps.axis_converged,
            "cyl_converged": ps.cyl_converged,
            "duochrome_balanced": ps.duochrome_balanced,
            "balance_converged": ps.balance_converged,
            "add_converged": ps.add_converged,

            # Derived variables
            "dv_requires_optom_review": dv.dv_requires_optom_review,
            "dv_add_expected": dv.dv_add_expected,
            "dv_target_distance_va": dv.dv_target_distance_va,
            "dv_near_test_required": dv.dv_near_test_required,
            "dv_anomaly_watch": dv.dv_anomaly_watch,

            # Fogging state
            "fog_cleared": ps.fog_phase == "cleared" or ps.fog_remaining <= 0,
            "fog_remaining": ps.fog_remaining,

            # VA proxies
            "VA_RE": ps.chart_idx,  # Simplified; real implementation uses VA measurement
            "VA_LE": ps.chart_idx,
            "target_va": target_chart_idx,
        }

    def _evaluate_guard(self, guard_expr: str, context: dict) -> bool:
        """
        Evaluate a guard condition expression.

        Guard expressions use Python-like syntax:
        - "response == READABLE"
        - "axis_converged"
        - "comparisons > limit"
        - "response in [BETTER_1, BETTER_2]"
        - "balance_converged and dv_add_expected == None"

        This is a safe evaluator — no exec/eval, only predefined patterns.
        """
        guard_expr = guard_expr.strip()

        if guard_expr == "true":
            return True

        # Handle 'and' conjunction
        if " and " in guard_expr:
            parts = guard_expr.split(" and ")
            return all(self._evaluate_guard(p.strip(), context) for p in parts)

        # Handle 'or' disjunction
        if " or " in guard_expr:
            parts = guard_expr.split(" or ")
            return any(self._evaluate_guard(p.strip(), context) for p in parts)

        # Handle "key == value"
        if " == " in guard_expr:
            key, value = guard_expr.split(" == ", 1)
            key = key.strip()
            value = value.strip()
            left = self._resolve_value(key, context)
            right = self._resolve_value(value, context)

            # Handle special values
            if right is True:
                return bool(left)
            if right is False:
                return not bool(left)
            if right is None:
                return left is None or left == "None"

            # String/enum comparison
            return str(left) == str(right)

        # Handle "key != value"
        if " != " in guard_expr:
            key, value = guard_expr.split(" != ", 1)
            key = key.strip()
            value = value.strip()
            left = self._resolve_value(key, context)
            right = self._resolve_value(value, context)
            if right is None:
                return left is not None and left != "None"
            return str(left) != str(right)

        # Handle "key >= value"
        if " >= " in guard_expr:
            key, value = guard_expr.split(" >= ", 1)
            left = self._resolve_value(key.strip(), context)
            right = self._resolve_value(value.strip(), context)
            try:
                return float(left) >= float(right)
            except (ValueError, TypeError):
                return False

        # Handle "key > value"
        if " > " in guard_expr:
            key, value = guard_expr.split(" > ", 1)
            left = self._resolve_value(key.strip(), context)
            right = self._resolve_value(value.strip(), context)
            try:
                return float(left) > float(right)
            except (ValueError, TypeError):
                return False

        # Handle "response in [VAL1, VAL2, ...]"
        if " in [" in guard_expr:
            key, vals_str = guard_expr.split(" in [", 1)
            key = key.strip()
            vals_str = vals_str.rstrip("]").strip()
            values = [v.strip() for v in vals_str.split(",")]
            ctx_val = str(context.get(key, ""))
            return ctx_val in values

        # Handle bare boolean: "axis_converged", "dv_requires_optom_review"
        ctx_val = context.get(guard_expr)
        if ctx_val is not None:
            return bool(ctx_val)

        logger.warning(f"Unrecognized guard expression: {guard_expr}")
        return False

    def _resolve_value(self, token: str, context: dict):
        """
        Resolve a token to its value.
        If the token is a key in the context, return the context value.
        Otherwise, try to parse it as a literal (number, bool, None).
        """
        # Check if it's a context variable
        if token in context:
            return context[token]

        # Try as number
        try:
            return float(token)
        except ValueError:
            pass

        # Boolean / None literals
        if token in ("true", "True", "TRUE"):
            return True
        if token in ("false", "False", "FALSE"):
            return False
        if token == "None":
            return None

        # Return as string
        return token

    # -------------------------------------------------------------------------
    # Entry Actions
    # -------------------------------------------------------------------------

    def _execute_entry_actions(self, actions: List[str], state: str):
        """
        Execute entry actions for a state.
        These are descriptive strings that trigger specific setup logic.
        """
        phase_type = self.transitions_config.get(state, {}).get("phase_type", "")
        dv = self.derived_vars
        ps = self.phase_state
        cal = self.calibration

        if phase_type == "COARSE_SPHERE":
            # Apply fogging
            if dv.dv_fogging_policy != "No_Fog":
                eye = self.transitions_config.get(state, {}).get("eye", "RE")
                fog_amount = dv.dv_fogging_amount_D
                if eye == "RE":
                    ps.re_sph += fog_amount
                    ps.fog_remaining = fog_amount
                else:
                    ps.le_sph += fog_amount
                    ps.fog_remaining = fog_amount
                ps.fog_phase = "fogging"
                logger.info(
                    f"Applied {fog_amount}D fogging to {eye} "
                    f"(policy: {dv.dv_fogging_policy})"
                )

        elif phase_type == "JCC_AXIS":
            # Initialize axis step
            ps.axis_step = cal.get("AXIS_POLICY", {}).get("axis_start_step", 5)
            ps.axis_reversal_count = 0
            ps.axis_converged = False
            ps.prev_axis_response = ""

        elif phase_type == "JCC_POWER":
            ps.same_streak = 0
            ps.cyl_converged = False
            ps.cyl_cumulative_change = 0.0

        elif phase_type == "DUOCHROME":
            ps.duo_iter = 0
            ps.duo_flip = 0
            ps.equal_streak = 0
            ps.duochrome_balanced = False
            ps.prev_duo_response = ""

        elif phase_type == "BINOC_BALANCE":
            ps.balance_same_streak = 0
            ps.balance_converged = False

        elif phase_type == "NEAR_ADD":
            ps.add_converged = False

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def _log_step(self, response: str):
        """Record a step in the log."""
        ps = self.phase_state
        entry = {
            "state": self.current_state,
            "phase_type": self.current_phase_type,
            "eye": self.current_eye,
            "step": ps.step_count,
            "response": response,
            "re_sph": ps.re_sph,
            "re_cyl": ps.re_cyl,
            "re_axis": ps.re_axis,
            "le_sph": ps.le_sph,
            "le_cyl": ps.le_cyl,
            "le_axis": ps.le_axis,
            "re_add": ps.re_add,
            "le_add": ps.le_add,
        }
        self.step_log.append(entry)

    # -------------------------------------------------------------------------
    # Final Rx
    # -------------------------------------------------------------------------

    def get_final_rx(self) -> dict:
        """Get the final prescription values."""
        ps = self.phase_state
        return {
            "RE": {
                "sph": round(ps.re_sph, 2),
                "cyl": round(ps.re_cyl, 2),
                "axis": round(ps.re_axis),
                "add": round(ps.re_add, 2),
            },
            "LE": {
                "sph": round(ps.le_sph, 2),
                "cyl": round(ps.le_cyl, 2),
                "axis": round(ps.le_axis),
                "add": round(ps.le_add, 2),
            },
        }

    def get_state_summary(self) -> dict:
        """Get a summary of the current FSM state for API/debug."""
        return {
            "current_state": self.current_state,
            "description": self.current_description,
            "phase_type": self.current_phase_type,
            "eye": self.current_eye,
            "step_count": self.phase_state.step_count,
            "is_terminal": self.is_terminal,
            "question": self.get_question(),
            "allowed_responses": self.get_allowed_responses(),
            "chart_type": self.get_chart_type(),
            "timeout_limit": self.get_timeout_limit(),
            "lens_values": self.get_final_rx(),
        }


# =============================================================================
# Backward-compatible alias for legacy InteractiveSession import
# =============================================================================
StateMachine = FSMStateMachine
