"""
State machine: Manages phase transitions and state tracking.
"""
from typing import List, Optional
from dataclasses import dataclass, field
import yaml
from pathlib import Path

from .context import RowContext


@dataclass
class StateMachine:
    """Manages phase transitions and state variables."""
    
    # State variables
    current_phase: str = "distance_vision"
    current_eye: str = "both"
    duochrome_seen: bool = False
    right_sph_stable: bool = False
    left_sph_stable: bool = False
    right_axis_stable: bool = False
    left_axis_stable: bool = False
    right_cyl_stable: bool = False
    left_cyl_stable: bool = False
    unable_read_count_right: int = 0
    unable_read_count_left: int = 0
    last_question: str = ""
    last_occluder: str = ""
    
    # Configuration
    protocol: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    
    # History
    phase_history: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Load configuration if not provided."""
        if not self.protocol:
            self.load_config()
    
    def load_config(self):
        """Load protocol and thresholds from YAML files."""
        config_dir = Path(__file__).parent.parent / "config"
        
        with open(config_dir / "protocol.yaml") as f:
            self.protocol = yaml.safe_load(f)
        
        with open(config_dir / "thresholds.yaml") as f:
            self.thresholds = yaml.safe_load(f)
    
    def process_row(self, row: RowContext, prev: Optional[RowContext], nxt: Optional[RowContext]) -> str:
        """
        Process a row and determine its phase.
        Returns the phase ID.
        """
        # Update duochrome tracking
        if row.chart_type == "duochrome" and not self.duochrome_seen:
            self.duochrome_seen = True
        
        # Determine phase based on triggers
        phase = self._match_phase(row)
        
        # Update state variables based on phase
        self._update_state(row, prev, nxt, phase)
        
        # Record phase history
        self.phase_history.append(phase)
        self.current_phase = phase
        
        return phase
    
    def _match_phase(self, row: RowContext) -> str:
        """Match row to a phase based on triggers."""
        
        # Special markers (non-sequential)
        if row.occluder_state == "Detection_Failed":
            return "detection_failed"
        
        if row.occluder_state == "Both_Occluded":
            return "both_occluded"
        
        if "Pinhole" in row.occluder_state:
            if row.occluder_state == "Right_Pinhole":
                return "pinhole_check_right"
            elif row.occluder_state == "Left_Pinhole":
                return "pinhole_check_left"
            else:
                return "pinhole_check_a4"
        
        # JCC phases (check before refraction phases)
        if row.is_flip1 or row.is_flip2 or row.chart_type == "jcc":
            if "Right_" in row.occluder_state or row.eye_tested == "right":
                if row.is_axis_flip:
                    return "jcc_axis_right"
                elif row.is_power_flip:
                    return "jcc_power_right"
                else:
                    # JCC chart without explicit flip state
                    return "jcc_axis_right"
            elif "Left_" in row.occluder_state or row.eye_tested == "left":
                if row.is_axis_flip:
                    return "jcc_axis_left"
                elif row.is_power_flip:
                    return "jcc_power_left"
                else:
                    return "jcc_axis_left"
        
        # Duochrome
        if row.chart_type == "duochrome":
            if row.occluder_state == "Left_Occluded":
                return "duochrome_right"
            elif row.occluder_state == "Right_Occluded":
                return "duochrome_left"
            else:
                return "duochrome_right"  # default
        
        # Refraction phases
        if row.chart_type in ["snellen", "echart"]:
            if row.occluder_state == "BINO":
                if self.duochrome_seen:
                    return "binocular_balance"
                else:
                    return "distance_vision"
            elif row.occluder_state == "Left_Occluded":
                return "right_eye_refraction"
            elif row.occluder_state == "Right_Occluded":
                return "left_eye_refraction"
        
        # Default fallback
        return "unknown"
    
    def _update_state(self, row: RowContext, prev: Optional[RowContext], 
                     nxt: Optional[RowContext], phase: str):
        """Update state variables based on current row and phase."""
        
        # Update eye tracking
        self.current_eye = row.eye_tested
        
        # Update unable_read counters for sphere refinement
        if phase == "right_eye_refraction":
            if row.patient_answer_intent == "Unable to read" and row.has_sph_change(prev):
                self.unable_read_count_right += 1
            else:
                # Reset if able to read or no SPH change
                if row.patient_answer_intent in ["Able to read", "Getting better"]:
                    self.unable_read_count_right = 0
            
            # Check exit condition
            if self.unable_read_count_right >= self.thresholds["sphere_refinement"]["unable_read_threshold"]:
                self.right_sph_stable = True
        
        elif phase == "left_eye_refraction":
            if row.patient_answer_intent == "Unable to read" and row.has_sph_change(prev):
                self.unable_read_count_left += 1
            else:
                if row.patient_answer_intent in ["Able to read", "Getting better"]:
                    self.unable_read_count_left = 0
            
            if self.unable_read_count_left >= self.thresholds["sphere_refinement"]["unable_read_threshold"]:
                self.left_sph_stable = True
        
        # Update axis/power stability for JCC
        if phase in ["jcc_axis_right", "jcc_axis_left"]:
            if row.is_flip2 and nxt:
                if "Both Same" in (row.patient_answer_intent or ""):
                    if "right" in phase:
                        self.right_axis_stable = True
                    else:
                        self.left_axis_stable = True
                elif not row.has_axis_change(nxt):
                    if "right" in phase:
                        self.right_axis_stable = True
                    else:
                        self.left_axis_stable = True
        
        if phase in ["jcc_power_right", "jcc_power_left"]:
            if row.is_flip2 and nxt:
                if "Both Same" in (row.patient_answer_intent or ""):
                    if "right" in phase:
                        self.right_cyl_stable = True
                    else:
                        self.left_cyl_stable = True
                elif not row.has_cyl_change(nxt):
                    if "right" in phase:
                        self.right_cyl_stable = True
                    else:
                        self.left_cyl_stable = True
                # Check 0.00 exception
                elif abs(row.r_cyl if "right" in phase else row.l_cyl) < 0.001:
                    if "Flip 1" in (row.patient_answer_intent or ""):
                        if "right" in phase:
                            self.right_cyl_stable = True
                        else:
                            self.left_cyl_stable = True
        
        # Update last question/occluder for confidence tracking
        if row.optometrist_question:
            self.last_question = row.optometrist_question
        self.last_occluder = row.occluder_state
    
    def should_transition(self, current_phase: str) -> Optional[str]:
        """
        Determine if a phase transition should occur.
        Returns next phase ID or None.
        """
        if current_phase == "right_eye_refraction" and self.right_sph_stable:
            return "jcc_axis_right"
        
        if current_phase == "jcc_axis_right" and self.right_axis_stable:
            return "jcc_power_right"
        
        if current_phase == "jcc_power_right" and self.right_cyl_stable:
            return "duochrome_right"
        
        if current_phase == "left_eye_refraction" and self.left_sph_stable:
            return "jcc_axis_left"
        
        if current_phase == "jcc_axis_left" and self.left_axis_stable:
            return "jcc_power_left"
        
        if current_phase == "jcc_power_left" and self.left_cyl_stable:
            return "duochrome_left"
        
        return None
    
    def get_phase_name(self, phase_id: str) -> str:
        """Get human-readable phase name."""
        phases = self.protocol.get("phases", {})
        phase_config = phases.get(phase_id, {})
        return phase_config.get("name", phase_id)
