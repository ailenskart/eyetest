#!/usr/bin/env python3
"""
Interactive eye test session orchestrator.
Manages conversation flow with patient and phoropter API calls.
"""
import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

from core.state_machine import StateMachine
from core.context import RowContext


class InteractiveSession:
    """Orchestrates an interactive eye test session."""
    
    def __init__(self, base_url: str = "https://rajasthan-royals.preprod.lenskart.com",
                 phoropter_id: str = "phoropter-1"):
        self.base_url = base_url
        self.phoropter_id = phoropter_id
        self.api_endpoint = f"{base_url}/phoropter/{phoropter_id}/run-tests"
        
        # Initialize state machine
        self.state_machine = StateMachine()
        
        # Phase name mapping
        self.phase_names = {
            "distance_vision": "Phase A: Distance Vision (Step 2.1)",
            "right_eye_refraction": "Phase B: Right Eye Refraction (Step 6.1)",
            "jcc_axis_right": "Phase E: JCC Axis Right (Step 6.2)",
            "jcc_power_right": "Phase F: JCC Power Right (Step 6.2)",
            "duochrome_right": "Phase G: Duochrome Right (Step 6.2)",
            "validation_right": "Phase H: 20/20 Validation Right",
            "left_eye_refraction": "Phase I: Left Eye Refraction (Step 6.3)",
            "jcc_axis_left": "Phase J: JCC Axis Left (Step 6.4)",
            "jcc_power_left": "Phase K: JCC Power Left (Step 6.4)",
            "duochrome_left": "Phase L: Duochrome Left (Step 6.4)",
            "validation_left": "Phase M: 20/20 Validation Left",
            "validation_distance": "Phase N: 6/6 Validation (Distance)",
            "binocular_balance": "Phase O: Binocular Balance (Step 6.5)",
            "near_add_right": "Phase P: Near Vision - Right Eye ADD",
            "near_add_left": "Phase Q: Near Vision - Left Eye ADD",
            "near_add_bino": "Phase R: Near Vision - Binocular ADD",
        }
        
        # Current test state
        self.current_phase = "distance_vision"
        self.current_row = self._init_row()
        self.session_history: List[RowContext] = []
        
        # Session-level logging state
        self.session_start_time: Optional[datetime] = None
        self.session_end_time: Optional[datetime] = None
        self._row_counter = 0
        self._phase_jump_count = 0
        self._phase_start_times: Dict[str, datetime] = {}
        self._phases_visited: List[str] = []

        # Previous state tracking for "Prev State" functionality
        self.previous_state = None
        self.show_prev_state_option = False
        
        # JCC Power at 0.0 tracking
        self.jcc_power_zero_flip1_count = 0
        
        # Spherical equivalent compensation tracking
        # Track if we're at a -0.50D threshold (e.g., -0.50, -1.00, -1.50, etc.)
        # When crossing into threshold: SPH +0.25D
        # When crossing out of threshold: SPH -0.25D
        self.r_at_cyl_threshold = False
        self.l_at_cyl_threshold = False

        # ADD power tracking for near vision phases
        self.add_right = 0.0
        self.add_left = 0.0

        # 20/20 validation fallback tracking
        self.validation_right_fallback_power = None
        self.validation_left_fallback_power = None
        self.validation_right_status = None
        self.validation_left_status = None
        
        # Refraction state tracking
        # All available charts for selection
        self.all_charts = [
            "echart_400",
            "snellen_chart_200_150",
            "snellen_chart_100_80",
            "snellen_chart_70_60_50",
            "snellen_chart_40_30_25",
            "snellen_chart_25_20_15",
            "snellen_chart_20_20_20",
            "snellen_chart_20_15_10",
        ]
        # Snellen charts only (for automatic progression during refraction)
        self.snellen_charts = [
            "snellen_chart_200_150",
            "snellen_chart_100_80",
            "snellen_chart_70_60_50",
            "snellen_chart_40_30_25",
            "snellen_chart_25_20_15",
            "snellen_chart_20_20_20",
            "snellen_chart_20_15_10",
        ]
        self.current_chart_index = 0
        self.unable_read_count = 0
        self.jcc_flip_state = "flip1"  # flip1 or flip2
        self.jcc_cycle_count = 0
        self.jcc_last_choice: Optional[str] = None
        self.jcc_same_choice_count = 0
        self.duochrome_last_choice: Optional[str] = None
        self.duochrome_same_choice_count = 0
        
        # Chart mappings (snellen_20_20 used by protocol for validation phases)
        self.chart_map = {
            "echart_400": "chart_9",
            "snellen_chart_200_150": "chart_10",
            "snellen_chart_100_80": "chart_11",
            "snellen_chart_70_60_50": "chart_12",
            "snellen_chart_40_30_25": "chart_13",
            "snellen_chart_20_15_10": "chart_14",
            "snellen_chart_20_20_20": "chart_15",
            "snellen_20_20": "chart_15",
            "snellen_chart_25_20_15": "chart_16",
            "duochrome": "chart_17",
            "jcc_chart": "chart_19",
            "bino_chart": "chart_20",
            "near_chart": "chart_5",
        }
        # 20/20 validation fallback: when in 20/40 we track sub-state for Better/Same/Worse
        self._validation_fallback_active = None  # "right", "left", or None
        self._validation_fallback_refine_count = 0
        self._validation_fallback_max_refines = 4
    
    def _init_row(self) -> RowContext:
        """Initialize a row with restart state."""
        return RowContext(
            timestamp="00:00",
            r_sph=0.0, r_cyl=0.0, r_axis=180.0, r_add=0.0,
            l_sph=0.0, l_cyl=0.0, l_axis=180.0, l_add=0.0,
            pd="", chart_number=-1,
            occluder_state="BINO",
            chart_display="",
            ocr_fields_read=0,
            anomalies_fixed=0,
        )

    def _stamp_row(self, row: RowContext, interaction_type: str,
                   change_delta: str) -> None:
        """Populate logging fields on a row before appending to history."""
        self._row_counter += 1
        row.row_number = self._row_counter
        row.timestamp = datetime.now().isoformat(timespec="milliseconds")
        row.interaction_type = interaction_type
        row.change_delta = change_delta
        row.phase_id = self.current_phase
        row.phase_name = self.phase_names.get(self.current_phase, self.current_phase)
        row.optometrist_question = self.get_question()

    def _compute_change_delta(self, intent: str, interaction_type: str) -> str:
        """Compute a human-readable change description for the current row.

        For QnA rows the delta is the patient's response.  For manual
        adjustments it describes which parameters changed and by how much.
        """
        if interaction_type == "Manual":
            prev = self.session_history[-1] if self.session_history else None
            if prev is None:
                return "Manual Adjust"
            parts = []
            tol = 0.001
            for eye, prefix in [("R", "r_"), ("L", "l_")]:
                for param in ["sph", "cyl", "axis"]:
                    old_val = getattr(prev, f"{prefix}{param}")
                    new_val = getattr(self.current_row, f"{prefix}{param}")
                    diff = new_val - old_val
                    if abs(diff) > tol:
                        sign = "+" if diff > 0 else ""
                        if param == "axis":
                            parts.append(f"{param.upper()} {sign}{int(diff)} [{eye}]")
                        else:
                            parts.append(f"{param.upper()} {sign}{diff:.2f} [{eye}]")
            if parts:
                return "Manual Adjust: " + ", ".join(parts)
            return "Manual Adjust"

        return f"Response: {intent}"

    def _track_phase_entry(self, phase: str) -> None:
        """Record phase entry for duration tracking."""
        self._phase_start_times[phase] = datetime.now()
        if phase not in self._phases_visited:
            self._phases_visited.append(phase)

    def get_duration_per_phase(self) -> Dict[str, float]:
        """Calculate time spent in each phase based on rows."""
        durations: Dict[str, float] = {}
        if not self.session_history:
            return durations
        for i, row in enumerate(self.session_history):
            pid = row.phase_id or "unknown"
            if i + 1 < len(self.session_history):
                try:
                    t0 = datetime.fromisoformat(row.timestamp)
                    t1 = datetime.fromisoformat(self.session_history[i + 1].timestamp)
                    durations[pid] = durations.get(pid, 0.0) + (t1 - t0).total_seconds()
                except (ValueError, TypeError):
                    pass
        return durations

    def _reset_jcc_choice_tracking(self) -> None:
        """Reset JCC flip choice tracking for reversal detection."""
        self.jcc_last_choice = None
        self.jcc_same_choice_count = 0

    def _record_jcc_choice(self, choice: str) -> bool:
        """Record a JCC flip choice and return True on reversal after a streak.

        A reversal occurs when the patient selects the opposite flip after
        choosing the same flip at least once in a row.
        """
        if choice == self.jcc_last_choice:
            self.jcc_same_choice_count += 1
            return False

        reversal = self.jcc_last_choice is not None and self.jcc_same_choice_count >= 1
        self.jcc_last_choice = choice
        self.jcc_same_choice_count = 1
        return reversal

    def _reset_duochrome_choice_tracking(self) -> None:
        """Reset duochrome color choice tracking for reversal detection."""
        self.duochrome_last_choice = None
        self.duochrome_same_choice_count = 0

    def _record_duochrome_choice(self, choice: str) -> bool:
        """Record a duochrome color choice and return True on reversal after a streak.

        A reversal occurs when the patient selects the opposite color after
        choosing the same color at least once in a row.
        """
        if choice == self.duochrome_last_choice:
            self.duochrome_same_choice_count += 1
            return False

        reversal = (
            self.duochrome_last_choice is not None
            and self.duochrome_same_choice_count >= 1
        )
        self.duochrome_last_choice = choice
        self.duochrome_same_choice_count = 1
        return reversal
    
    def _post_to_phoropter(self, url: str, payload: dict) -> None:
        """Send a JSON POST to the phoropter broker via urllib (cloud-safe, no curl)."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        print(f"[PHOROPTER] POST {url} payload={json.dumps(payload)}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                print(f"[PHOROPTER] Response {resp.getcode()}: {body[:200]}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            print(f"[PHOROPTER] HTTP Error {e.code}: {body[:200]}")
        except Exception as e:
            print(f"[PHOROPTER] Request failed: {e}")

    def reset_phoropter(self):
        """Reset phoropter to neutral state."""
        url = f"{self.base_url}/phoropter/{self.phoropter_id}/reset"
        print(f"[CMD] POST {url}")
        self._post_to_phoropter(url, {})
        print("✓ Phoropter reset to 0/0/180")
    
    def set_chart(self, chart_name: str, size: Optional[str] = None, tab: str = "Chart1"):
        """Display a chart on the phoropter. Optional size for VA charts (e.g. '40' for 20/40, '20_1' for 20/20)."""
        chart_id = self.chart_map.get(chart_name)
        if not chart_id:
            print(f"Warning: Unknown chart {chart_name}")
            return
        chart_items = [chart_id] if size is None else [chart_id, size]
        payload = {
            "test_cases": [{
                "chart": {
                    "tab": tab,
                    "chart_items": chart_items
                }
            }]
        }
        self._post_to_phoropter(self.api_endpoint, payload)
        self.current_row.chart_display = chart_name
        print(f"✓ Displaying: {chart_name}" + (f" size={size}" if size else ""))

    def set_chart_near(self):
        """Switch to Near Vision tab (Chart 5). Required before ADD adjustment."""
        payload = {
            "test_cases": [{
                "chart": {"tab": "Chart5", "chart_items": ["chart_5"]}
            }]
        }
        self._post_to_phoropter(self.api_endpoint, payload)
        self.current_row.chart_display = "near_chart"
        print("✓ Displaying: Near chart (Chart 5)")
    
    def set_power(self, r_sph: float = None, r_cyl: float = None, r_axis: float = None,
                  l_sph: float = None, l_cyl: float = None, l_axis: float = None,
                  r_add: float = None, l_add: float = None, occluder: str = None):
        """Set power and occluder on phoropter. Optional r_add/l_add for near vision."""
        # Build payload
        right_eye = {}
        if r_sph is not None:
            right_eye["sph"] = r_sph
            self.current_row.r_sph = r_sph
        if r_cyl is not None:
            right_eye["cyl"] = r_cyl
            self.current_row.r_cyl = r_cyl
        if r_axis is not None:
            right_eye["axis"] = r_axis
            self.current_row.r_axis = r_axis
        if r_add is not None:
            right_eye["add"] = r_add
            self.add_right = r_add
            self.current_row.r_add = r_add

        left_eye = {}
        if l_sph is not None:
            left_eye["sph"] = l_sph
            self.current_row.l_sph = l_sph
        if l_cyl is not None:
            left_eye["cyl"] = l_cyl
            self.current_row.l_cyl = l_cyl
        if l_axis is not None:
            left_eye["axis"] = l_axis
            self.current_row.l_axis = l_axis
        if l_add is not None:
            left_eye["add"] = l_add
            self.add_left = l_add
            self.current_row.l_add = l_add

        payload = {"test_cases": [{}]}
        
        if right_eye:
            payload["test_cases"][0]["right_eye"] = right_eye
        if left_eye:
            payload["test_cases"][0]["left_eye"] = left_eye
        
        # Map occluder and set JCC eye mode for non-JCC phases
        jcc_eye_mode = None
        is_jcc_phase = self.current_phase in ["jcc_axis_right", "jcc_power_right", "jcc_axis_left", "jcc_power_left"]
        
        if occluder:
            # Note: AuxLens control removed - phoropter handles this automatically
            # Only track occluder state and JCC eye mode mapping
            if occluder == "Left_Occluded":
                jcc_eye_mode = "R"  # Use L when left is occluded
            elif occluder == "Right_Occluded":
                jcc_eye_mode = "L"  # Use R when right is occluded
            elif occluder == "BINO":
                jcc_eye_mode = "BINO"
            self.current_row.occluder_state = occluder
        
        self._post_to_phoropter(self.api_endpoint, payload)
        print(f"✓ Power set: R({r_sph}/{r_cyl}/{r_axis}) L({l_sph}/{l_cyl}/{l_axis}) Occ: {occluder}")
        
        # Set JCC eye mode for non-JCC phases only
        # JCC phases handle their own state when chart is displayed
        if jcc_eye_mode and not is_jcc_phase:
            self.jcc_control(jcc_eye_mode)
            print(f"✓ JCC eye mode set: {jcc_eye_mode}")
    
    def set_power_with_prev_state(self, 
                                   prev_r_sph: float, prev_r_cyl: float, prev_r_axis: float,
                                   prev_l_sph: float, prev_l_cyl: float, prev_l_axis: float,
                                   r_sph: float, r_cyl: float, r_axis: float,
                                   l_sph: float, l_cyl: float, l_axis: float,
                                   prev_aux_lens: str = None, aux_lens: str = None,
                                   r_add: float = None, l_add: float = None,
                                   prev_r_add: float = None, prev_l_add: float = None):
        """Set power with previous state for accurate click calculations.
        Optional r_add/l_add for near vision target ADD values.
        Optional prev_r_add/prev_l_add: the ADD the phoropter is currently at
        so the broker computes the correct delta instead of assuming prev ADD = 0.
        """
        prev_right = {"sph": prev_r_sph, "cyl": prev_r_cyl, "axis": prev_r_axis}
        prev_left = {"sph": prev_l_sph, "cyl": prev_l_cyl, "axis": prev_l_axis}
        if prev_r_add is not None:
            prev_right["add"] = prev_r_add
        if prev_l_add is not None:
            prev_left["add"] = prev_l_add
        right_eye = {"sph": r_sph, "cyl": r_cyl, "axis": r_axis}
        left_eye = {"sph": l_sph, "cyl": l_cyl, "axis": l_axis}
        if r_add is not None:
            right_eye["add"] = r_add
            self.add_right = r_add
            self.current_row.r_add = r_add
        if l_add is not None:
            left_eye["add"] = l_add
            self.add_left = l_add
            self.current_row.l_add = l_add

        payload = {
            "test_cases": [{
                "case_id": 1,
                "prev_right_eye": prev_right,
                "prev_left_eye": prev_left,
                "right_eye": right_eye,
                "left_eye": left_eye
            }]
        }
        if prev_aux_lens:
            payload["test_cases"][0]["prev_aux_lens"] = prev_aux_lens
        if aux_lens:
            payload["test_cases"][0]["aux_lens"] = aux_lens

        # Update internal state
        self.current_row.r_sph = r_sph
        self.current_row.r_cyl = r_cyl
        self.current_row.r_axis = r_axis
        self.current_row.l_sph = l_sph
        self.current_row.l_cyl = l_cyl
        self.current_row.l_axis = l_axis
        
        self._post_to_phoropter(self.api_endpoint, payload)
        print(f"✓ Power set with prev state: R({r_sph}/{r_cyl}/{r_axis}) L({l_sph}/{l_cyl}/{l_axis})")
        print(f"  Previous state: R({prev_r_sph}/{prev_r_cyl}/{prev_r_axis}) L({prev_l_sph}/{prev_l_cyl}/{prev_l_axis})")

    def _set_add_bino_delta_only(self, prev_add: float, new_add: float) -> None:
        """Send ONLY right-eye ADD delta for Phase R (binocular).
        Omits left add entirely so broker issues single click - binocular ADD
        uses one physical control; including both R+L causes two clicks.
        """
        prev_right = {
            "sph": self.current_row.r_sph, "cyl": self.current_row.r_cyl, "axis": self.current_row.r_axis,
            "add": prev_add
        }
        prev_left = {
            "sph": self.current_row.l_sph, "cyl": self.current_row.l_cyl, "axis": self.current_row.l_axis
        }
        right_eye = {
            "sph": self.current_row.r_sph, "cyl": self.current_row.r_cyl, "axis": self.current_row.r_axis,
            "add": new_add
        }
        left_eye = {
            "sph": self.current_row.l_sph, "cyl": self.current_row.l_cyl, "axis": self.current_row.l_axis
        }
        payload = {
            "test_cases": [{
                "case_id": 1,
                "prev_right_eye": prev_right,
                "prev_left_eye": prev_left,
                "right_eye": right_eye,
                "left_eye": left_eye,
                "aux_lens": "BINO"
            }]
        }
        self._post_to_phoropter(self.api_endpoint, payload)
        print(f"✓ ADD bino delta only: {prev_add} -> {new_add} (single click)")
    
    def jcc_control(self, action: str):
        """Perform JCC action (handle, increase, decrease, etc.)."""
        payload = {"test_cases": [{"jcc": action}]}
        self._post_to_phoropter(self.api_endpoint, payload)
        print(f"✓ JCC action: {action}")
    
    def set_pinhole(self):
        """Set pinhole on the phoropter."""
        url = f"{self.base_url}/phoropter/{self.phoropter_id}/pinhole"
        print(f"[CMD] POST {url}")
        self._post_to_phoropter(url, {})
        print("✓ Pinhole activated")
    
    def get_question(self) -> str:
        """Get current question based on phase and state."""
        phase_config = self.state_machine.protocol["phases"].get(self.current_phase, {})
        questions = phase_config.get("questions", [])
        
        if isinstance(questions, dict):
            # JCC phase with flip1/flip2
            if self.current_row.is_flip1:
                return questions.get("flip1", "")
            elif self.current_row.is_flip2:
                return questions.get("flip2", "")
            return questions.get("flip1", "")
        elif isinstance(questions, list) and questions:
            return questions[0]
        
        return "Please describe what you see."
    
    def get_intents(self) -> List[str]:
        """Get available intents for current phase."""
        phase_config = self.state_machine.protocol["phases"].get(self.current_phase, {})
        intents = phase_config.get("intents", [])
        
        if isinstance(intents, dict):
            # JCC phase
            if self.current_row.is_flip1:
                flip1_intents = intents.get("flip1", [])
                # Return empty list for flip1 (no response needed, auto-flip)
                return flip1_intents if isinstance(flip1_intents, list) else []
            elif self.current_row.is_flip2:
                flip2_intents = intents.get("flip2", [])
                return flip2_intents if isinstance(flip2_intents, list) else [flip2_intents]
            return []
        elif isinstance(intents, list):
            # Add "Prev State" option if we have a previous state to restore
            if self.show_prev_state_option and self.previous_state is not None:
                return intents + ["Prev State"]
            return intents
        
        return ["Responds to instruction."]
    
    def start_distance_vision(self):
        """Start Phase A: Distance Vision."""
        self.session_start_time = datetime.now()
        self.current_phase = "distance_vision"
        self._track_phase_entry(self.current_phase)
        
        print("\n" + "="*60)
        print(self.phase_names[self.current_phase].upper())
        print("="*60)
        
        # Note: Frontend already calls resetPhoropter() before starting session
        # self.reset_phoropter()
        self.current_chart_index = 0
        self.set_chart(self.all_charts[0])
        self.current_row.occluder_state = "BINO"
        self.current_row.chart_display = self.all_charts[0]
        
        question = self.get_question()
        intents = self.get_intents()
        
        return {
            "phase": self.phase_names[self.current_phase],
            "question": question,
            "intents": intents,
            "chart": self.all_charts[0],
            "occluder": "BINO",
            "power": {
                "right": {"sph": 0.0, "cyl": 0.0, "axis": 180.0},
                "left": {"sph": 0.0, "cyl": 0.0, "axis": 180.0},
            },
            "chart_info": {
                "available_charts": self.all_charts,
                "current_index": self.current_chart_index,
                "current_chart": self.all_charts[self.current_chart_index]
            }
        }
    
    def process_response(self, intent: str) -> Dict:
        """Process patient response and return next question."""
        # Record current row with logging fields
        self.current_row.patient_answer_intent = intent
        delta = self._compute_change_delta(intent, "QnA")
        self._stamp_row(self.current_row, "QnA", delta)
        self.session_history.append(self.current_row)
        
        # Process based on current phase
        if self.current_phase == "distance_vision":
            return self._process_distance_vision(intent)
        elif self.current_phase == "right_eye_refraction":
            return self._process_right_eye_refraction(intent)
        elif self.current_phase == "jcc_axis_right":
            return self._process_jcc_axis_right(intent)
        elif self.current_phase == "jcc_power_right":
            return self._process_jcc_power_right(intent)
        elif self.current_phase == "duochrome_right":
            return self._process_duochrome_right(intent)
        elif self.current_phase == "validation_right":
            return self._process_validation_right(intent)
        elif self.current_phase == "left_eye_refraction":
            return self._process_left_eye_refraction(intent)
        elif self.current_phase == "jcc_axis_left":
            return self._process_jcc_axis_left(intent)
        elif self.current_phase == "jcc_power_left":
            return self._process_jcc_power_left(intent)
        elif self.current_phase == "duochrome_left":
            return self._process_duochrome_left(intent)
        elif self.current_phase == "validation_left":
            return self._process_validation_left(intent)
        elif self.current_phase == "validation_distance":
            return self._process_validation_distance(intent)
        elif self.current_phase == "binocular_balance":
            return self._process_binocular_balance(intent)
        elif self.current_phase == "near_add_right":
            return self._process_near_add_right(intent)
        elif self.current_phase == "near_add_left":
            return self._process_near_add_left(intent)
        elif self.current_phase == "near_add_bino":
            return self._process_near_add_bino(intent)
        
        # Default: complete
        return {
            "phase": "complete",
            "status": "complete",
            "question": "Test complete!",
            "intents": [],
        }
    
    def switch_chart(self, chart_index: int) -> Dict:
        """Switch to a different chart during distance vision or refraction phase.
        
        Args:
            chart_index: Index of the chart in the appropriate chart list
            
        Returns:
            Response dict with updated state
        """
        # Determine which chart list to use based on current phase
        if self.current_phase == "distance_vision":
            chart_list = self.all_charts
            phase_name = "distance vision"
        elif self.current_phase in ["right_eye_refraction", "left_eye_refraction"]:
            chart_list = self.snellen_charts
            phase_name = "refraction"
        else:
            raise ValueError(f"Chart switching not allowed in phase: {self.current_phase}")
        
        # Validate chart index
        if chart_index < 0 or chart_index >= len(chart_list):
            raise ValueError(f"Invalid chart index: {chart_index}")
        
        # Update chart index
        self.current_chart_index = chart_index
        
        # Update current row
        self.current_row = self._copy_row_state()
        self.current_row.chart_display = chart_list[chart_index]
        
        # Set the chart on phoropter
        self.set_chart(chart_list[chart_index])
        
        print(f"✓ Switched to chart {chart_index}: {chart_list[chart_index]}")
        
        # Return updated state
        return self._build_response()
    
    def _process_distance_vision(self, intent: str) -> Dict:
        """Process distance vision phase."""
        if intent in ("Unable to read", "Unable to read / Apply pinhole"):
            # Add pinhole and test again
            print(f"\n→ Patient unable to read, adding pinhole (keeping current chart: {self.current_row.chart_display})")
            self.set_pinhole()
            
            # Update question to ask with pinhole (keep current chart)
            self.current_row = self._copy_row_state()
            # Don't change chart_display - keep whatever chart is currently displayed
            
            # Return response with pinhole question
            response = self._build_response()
            response['question'] = "With pinhole: Can you see clearly now?"
            response['intents'] = ["Able to read with pinhole", "Still unable to read"]
            return response
        
        elif intent == "Able to read with pinhole":
            # Pinhole helped, move to right eye refraction
            print("✓ Pinhole improved vision, proceeding to refraction")
            return self._transition_to_right_eye_refraction()
        
        elif intent == "Still unable to read":
            # Pinhole didn't help, still move to refraction but flag for further evaluation
            print("⚠️ Pinhole did not improve vision, proceeding to refraction")
            return self._transition_to_right_eye_refraction()
        
        # Default: "Able to read" or "Blurry"
        return self._transition_to_right_eye_refraction()
    
    def _transition_to_right_eye_refraction(self) -> Dict:
        """Transition to right eye refraction."""
        self.current_phase = "right_eye_refraction"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        
        self.current_chart_index = 0  # Start with largest chart
        self.unable_read_count = 0
        
        # Carry forward current power (preserves AR/Lenso values if applied)
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Left_Occluded"
        self.current_row.chart_display = self.snellen_charts[0]
        
        # Set phoropter
        self.set_chart(self.snellen_charts[0])
        self.set_power(occluder="Left_Occluded")
        
        return self._build_response()
    
    def _process_right_eye_refraction(self, intent: str) -> Dict:
        """Process right eye refraction with chart progression."""
        current_chart = self.snellen_charts[self.current_chart_index]
        
        # Handle "Prev State" intent to restore previous power
        if intent == "Prev State":
            if self.previous_state is not None:
                # Get current state
                curr_r_sph = self.current_row.r_sph
                
                # Get previous state
                prev_r_sph = self.previous_state['r_sph']
                
                # Use vision correction API to restore
                self.set_power_with_prev_state(
                    prev_r_sph=curr_r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                    prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                    r_sph=prev_r_sph, r_cyl=self.previous_state['r_cyl'], r_axis=self.previous_state['r_axis'],
                    l_sph=self.previous_state['l_sph'], l_cyl=self.previous_state['l_cyl'], l_axis=self.previous_state['l_axis'],
                    prev_aux_lens="AuxLensL",
                    aux_lens="AuxLensL"
                )
                
                self.previous_state = None
                self.show_prev_state_option = False
                print("✓ Restored to previous state")
            return self._build_response()
        
        # Reset prev state option for non-power-changing responses
        if intent not in ["Blurry", "Unable to read"]:
            self.show_prev_state_option = False
        
        if intent == "Able to read":
            # Move to next smaller chart
            if current_chart == "snellen_chart_20_20_20":
                # Target reached, move to JCC
                return self._transition_to_jcc_axis_right()
            elif self.current_chart_index < len(self.snellen_charts) - 1:
                self.current_chart_index += 1
                self.unable_read_count = 0
                self.current_row = self._copy_row_state()
                self.current_row.chart_display = self.snellen_charts[self.current_chart_index]
                self.set_chart(self.snellen_charts[self.current_chart_index])
            else:
                # Reached smallest chart, move to JCC
                return self._transition_to_jcc_axis_right()
        
        elif intent == "Blurry":
            # Save current state before making changes
            prev_r_sph = self.current_row.r_sph
            
            self.previous_state = {
                'r_sph': prev_r_sph,
                'r_cyl': self.current_row.r_cyl,
                'r_axis': self.current_row.r_axis,
                'l_sph': self.current_row.l_sph,
                'l_cyl': self.current_row.l_cyl,
                'l_axis': self.current_row.l_axis,
                'occluder_state': self.current_row.occluder_state,
                'chart_display': self.current_row.chart_display,
            }
            
            # Add -0.25D SPH, stay on same chart
            new_r_sph = prev_r_sph - 0.25
            
            # Use vision correction API with previous state
            self.set_power_with_prev_state(
                prev_r_sph=prev_r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=new_r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                prev_aux_lens="AuxLensL",
                aux_lens="AuxLensL"
            )
            
            self.unable_read_count = 0
            # Enable "Prev State" option for next response
            self.show_prev_state_option = True
        
        elif intent == "Unable to read":
            # Save current state before making changes
            prev_r_sph = self.current_row.r_sph
            
            self.previous_state = {
                'r_sph': prev_r_sph,
                'r_cyl': self.current_row.r_cyl,
                'r_axis': self.current_row.r_axis,
                'l_sph': self.current_row.l_sph,
                'l_cyl': self.current_row.l_cyl,
                'l_axis': self.current_row.l_axis,
                'occluder_state': self.current_row.occluder_state,
                'chart_display': self.current_row.chart_display,
            }
            
            # Add -0.25D SPH, stay on same chart
            new_r_sph = prev_r_sph - 0.25
            
            # Use vision correction API with previous state
            self.set_power_with_prev_state(
                prev_r_sph=prev_r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=new_r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                prev_aux_lens="AuxLensL",
                aux_lens="AuxLensL"
            )
            
            self.unable_read_count += 1
            # Enable "Prev State" option for next response
            self.show_prev_state_option = True
            
            # Check exit condition: 2 consecutive "Unable to read"
            if self.unable_read_count >= 2:
                return self._transition_to_jcc_axis_right()
        
        elif intent == "Getting better":
            # Continue with current power, move to smaller chart
            if self.current_chart_index < len(self.snellen_charts) - 1:
                self.current_chart_index += 1
                self.unable_read_count = 0
                self.current_row = self._copy_row_state()
                self.current_row.chart_display = self.snellen_charts[self.current_chart_index]
                self.set_chart(self.snellen_charts[self.current_chart_index])
            else:
                return self._transition_to_jcc_axis_right()
        
        return self._build_response()
    
    def _process_left_eye_refraction(self, intent: str) -> Dict:
        """Process left eye refraction (same logic as right eye)."""
        current_chart = self.snellen_charts[self.current_chart_index]
        
        # Handle "Prev State" intent to restore previous power
        if intent == "Prev State":
            if self.previous_state is not None:
                # Get current state
                curr_l_sph = self.current_row.l_sph
                
                # Get previous state
                prev_l_sph = self.previous_state['l_sph']
                
                # Use vision correction API to restore
                self.set_power_with_prev_state(
                    prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                    prev_l_sph=curr_l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                    r_sph=self.previous_state['r_sph'], r_cyl=self.previous_state['r_cyl'], r_axis=self.previous_state['r_axis'],
                    l_sph=prev_l_sph, l_cyl=self.previous_state['l_cyl'], l_axis=self.previous_state['l_axis'],
                    prev_aux_lens="AuxLensR",
                    aux_lens="AuxLensR"
                )
                
                self.previous_state = None
                self.show_prev_state_option = False
                print("✓ Restored to previous state")
            return self._build_response()
        
        # Reset prev state option for non-power-changing responses
        if intent not in ["Blurry", "Unable to read"]:
            self.show_prev_state_option = False
        
        if intent == "Able to read":
            if current_chart == "snellen_chart_20_20_20":
                return self._transition_to_jcc_axis_left()
            elif self.current_chart_index < len(self.snellen_charts) - 1:
                self.current_chart_index += 1
                self.unable_read_count = 0
                self.current_row = self._copy_row_state()
                self.current_row.chart_display = self.snellen_charts[self.current_chart_index]
                self.set_chart(self.snellen_charts[self.current_chart_index])
            else:
                return self._transition_to_jcc_axis_left()
        
        elif intent == "Blurry":
            # Save current state before making changes
            prev_l_sph = self.current_row.l_sph
            
            self.previous_state = {
                'r_sph': self.current_row.r_sph,
                'r_cyl': self.current_row.r_cyl,
                'r_axis': self.current_row.r_axis,
                'l_sph': prev_l_sph,
                'l_cyl': self.current_row.l_cyl,
                'l_axis': self.current_row.l_axis,
                'occluder_state': self.current_row.occluder_state,
                'chart_display': self.current_row.chart_display,
            }
            
            # Add -0.25D SPH, stay on same chart
            new_l_sph = prev_l_sph - 0.25
            
            # Use vision correction API with previous state
            self.set_power_with_prev_state(
                prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=prev_l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=new_l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                prev_aux_lens="AuxLensR",
                aux_lens="AuxLensR"
            )
            
            self.unable_read_count = 0
            # Enable "Prev State" option for next response
            self.show_prev_state_option = True
        
        elif intent == "Unable to read":
            # Save current state before making changes
            prev_l_sph = self.current_row.l_sph
            
            self.previous_state = {
                'r_sph': self.current_row.r_sph,
                'r_cyl': self.current_row.r_cyl,
                'r_axis': self.current_row.r_axis,
                'l_sph': prev_l_sph,
                'l_cyl': self.current_row.l_cyl,
                'l_axis': self.current_row.l_axis,
                'occluder_state': self.current_row.occluder_state,
                'chart_display': self.current_row.chart_display,
            }
            
            # Add -0.25D SPH, stay on same chart
            new_l_sph = prev_l_sph - 0.25
            
            # Use vision correction API with previous state
            self.set_power_with_prev_state(
                prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=prev_l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=new_l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                prev_aux_lens="AuxLensR",
                aux_lens="AuxLensR"
            )
            
            self.unable_read_count += 1
            # Enable "Prev State" option for next response
            self.show_prev_state_option = True
            
            if self.unable_read_count >= 2:
                return self._transition_to_jcc_axis_left()
        
        elif intent == "Getting better":
            if self.current_chart_index < len(self.snellen_charts) - 1:
                self.current_chart_index += 1
                self.unable_read_count = 0
                self.current_row = self._copy_row_state()
                self.current_row.chart_display = self.snellen_charts[self.current_chart_index]
                self.set_chart(self.snellen_charts[self.current_chart_index])
            else:
                return self._transition_to_jcc_axis_left()
        
        return self._build_response()
    
    def _process_jcc_axis_right(self, intent: str) -> Dict:
        """Process JCC axis refinement for right eye."""
        if self.jcc_flip_state == "flip1":
            # Auto-progress from Flip1 to Flip2
            if intent == "AUTO_FLIP":
                # This is the automatic call after 2 seconds
                # Call handle to flip from position 1 to position 2
                self.jcc_flip_state = "flip2"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Right_Axis_Flip2")
                self.jcc_control("handle")  # Flip to position 2
                return self._build_response()
            else:
                # Initial entry - show Flip1 and request auto-flip
                response = self._build_response()
                response['auto_flip'] = True  # Tell frontend to auto-progress
                response['flip_wait_seconds'] = 2
                return response
        
        elif self.jcc_flip_state == "flip2":
            # Process Flip2 response
            if "Repeat" in intent:
                # Repeat the flip cycle - reset to flip1 and request auto-flip
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Right_Axis_Flip1")
                # Note: JCC handle was already called, just need to show Flip1 again
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            if "MUCH better" in intent and ("GAP Axis" in intent or "Flip 1" in intent):
                # Patient chose Flip 1 MUCH better - increase axis by 10°
                reversal = self._record_jcc_choice("flip1")
                # Call increase twice for 10° total (5° + 5°)
                self.jcc_control("increase")
                self.jcc_control("increase")
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.r_axis += 10
                if self.current_row.r_axis > 180:
                    self.current_row.r_axis -= 180

                if reversal:
                    return self._transition_to_jcc_power_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "GAP Axis" in intent or "Flip 1" in intent:
                # Patient chose Flip 1 - Use JCC increase operation
                reversal = self._record_jcc_choice("flip1")
                self.jcc_control("increase")  # Phoropter increases axis by 5°
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.r_axis += 5
                if self.current_row.r_axis > 180:
                    self.current_row.r_axis -= 180

                if reversal:
                    return self._transition_to_jcc_power_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "MUCH better" in intent and ("RAM Axis" in intent or "Flip 2" in intent):
                # Patient chose Flip 2 MUCH better - decrease axis by 10°
                reversal = self._record_jcc_choice("flip2")
                # Call decrease twice for 10° total (5° + 5°)
                self.jcc_control("decrease")
                self.jcc_control("decrease")
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.r_axis -= 10
                if self.current_row.r_axis < 0:
                    self.current_row.r_axis += 180

                if reversal:
                    return self._transition_to_jcc_power_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "RAM Axis" in intent or "Flip 2" in intent:
                # Patient chose Flip 2 - Use JCC decrease operation
                reversal = self._record_jcc_choice("flip2")
                self.jcc_control("decrease")  # Phoropter decreases axis by 5°
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.r_axis -= 5
                if self.current_row.r_axis < 0:
                    self.current_row.r_axis += 180

                if reversal:
                    return self._transition_to_jcc_power_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "Both Same" in intent or "Reverse" in intent:
                # Move to JCC Power
                return self._transition_to_jcc_power_right()
            

        return self._build_response()
    
    def _process_jcc_axis_left(self, intent: str) -> Dict:
        """Process JCC axis refinement for left eye."""
        if self.jcc_flip_state == "flip1":
            # Auto-progress from Flip1 to Flip2
            if intent == "AUTO_FLIP":
                self.jcc_flip_state = "flip2"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Left_Axis_Flip2")
                self.jcc_control("handle")
                return self._build_response()
            else:
                # Initial entry - show Flip1 and request auto-flip
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
        
        elif self.jcc_flip_state == "flip2":
            if "Repeat" in intent:
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Left_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            if "MUCH better" in intent and ("GAP Axis" in intent or "Flip 1" in intent):
                # Patient chose Flip 1 MUCH better - increase axis by 10°
                reversal = self._record_jcc_choice("flip1")
                # Call increase twice for 10° total (5° + 5°)
                self.jcc_control("increase")
                self.jcc_control("increase")
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.l_axis += 10
                if self.current_row.l_axis > 180:
                    self.current_row.l_axis -= 180

                if reversal:
                    return self._transition_to_jcc_power_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "GAP Axis" in intent or "Flip 1" in intent:
                # Patient chose Flip 1 - Use JCC increase operation
                reversal = self._record_jcc_choice("flip1")
                self.jcc_control("increase")  # Phoropter increases axis by 5°
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.l_axis += 5
                if self.current_row.l_axis > 180:
                    self.current_row.l_axis -= 180

                if reversal:
                    return self._transition_to_jcc_power_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "MUCH better" in intent and ("RAM Axis" in intent or "Flip 2" in intent):
                # Patient chose Flip 2 MUCH better - decrease axis by 10°
                reversal = self._record_jcc_choice("flip2")
                # Call decrease twice for 10° total (5° + 5°)
                self.jcc_control("decrease")
                self.jcc_control("decrease")
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.l_axis -= 10
                if self.current_row.l_axis < 0:
                    self.current_row.l_axis += 180

                if reversal:
                    return self._transition_to_jcc_power_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "RAM Axis" in intent or "Flip 2" in intent:
                # Patient chose Flip 2 - Use JCC decrease operation
                reversal = self._record_jcc_choice("flip2")
                self.jcc_control("decrease")  # Phoropter decreases axis by 5°
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.l_axis -= 5
                if self.current_row.l_axis < 0:
                    self.current_row.l_axis += 180

                if reversal:
                    return self._transition_to_jcc_power_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Axis_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "Both Same" in intent or "Reverse" in intent:
                return self._transition_to_jcc_power_left()
            

        return self._build_response()
    
    def _process_jcc_power_right(self, intent: str) -> Dict:
        """Process JCC power refinement for right eye."""
        if self.jcc_flip_state == "flip1":
            # Auto-progress from Flip1 to Flip2
            if intent == "AUTO_FLIP":
                self.jcc_flip_state = "flip2"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Right_Power_Flip2")
                self.jcc_control("handle")
                return self._build_response()
            else:
                # Initial entry - show Flip1 and request auto-flip
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
        
        elif self.jcc_flip_state == "flip2":
            if "Repeat" in intent:
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Right_Power_Flip1")
                # Already at Flip1, just request auto-flip
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            if "MUCH better" in intent and ("GAP Power" in intent or "Flip 1" in intent):
                # Patient chose Flip 1 MUCH better - increase cylinder by 0.50D
                
                # Special handling: If cylinder is 0.0, cannot increase (would go positive)
                if self.current_row.r_cyl == 0.0:
                    self.jcc_power_zero_flip1_count += 1
                    
                    if self.jcc_power_zero_flip1_count == 1:
                        # First time: Repeat the flip cycle
                        print("⚠️  Cylinder is 0.0, cannot increase. Repeating flip cycle...")
                        self.jcc_control("handle")
                        self.jcc_flip_state = "flip1"
                        self.current_row = self._copy_row_state()
                        self._update_state(occluder="Right_Power_Flip1")
                        response = self._build_response()
                        response['auto_flip'] = True
                        response['flip_wait_seconds'] = 2
                        return response
                    else:
                        # Second time: Move to next phase
                        print("⚠️  Cylinder is 0.0 and patient chose Flip 1 again. Moving to duochrome...")
                        self.jcc_power_zero_flip1_count = 0  # Reset counter
                        return self._transition_to_duochrome_right()
                
                # Normal case: increase by 0.50D (call increase twice)
                reversal = self._record_jcc_choice("flip1")
                
                # Track spherical equivalent for each 0.25D step
                self.current_row = self._copy_row_state()
                
                # First 0.25D increase
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                self.jcc_control("increase")
                self.current_row.r_cyl += 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                if was_at_threshold and not now_at_threshold:
                    self.current_row.r_sph -= 0.25
                    print(f"✓ Spherical equivalent reversion: SPH decreased by -0.25D (now {self.current_row.r_sph:.2f}D)")
                
                # Second 0.25D increase
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                self.jcc_control("increase")
                self.current_row.r_cyl += 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                if was_at_threshold and not now_at_threshold:
                    self.current_row.r_sph -= 0.25
                    print(f"✓ Spherical equivalent reversion: SPH decreased by -0.25D (now {self.current_row.r_sph:.2f}D)")

                if reversal:
                    return self._transition_to_duochrome_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "GAP Power" in intent or "Flip 1" in intent:
                # Patient chose Flip 1 - Use JCC increase operation
                
                # Special handling: If cylinder is 0.0, cannot increase (would go positive)
                if self.current_row.r_cyl == 0.0:
                    self.jcc_power_zero_flip1_count += 1
                    
                    if self.jcc_power_zero_flip1_count == 1:
                        # First time: Repeat the flip cycle
                        print("⚠️  Cylinder is 0.0, cannot increase. Repeating flip cycle...")
                        self.jcc_control("handle")
                        self.jcc_flip_state = "flip1"
                        self.current_row = self._copy_row_state()
                        self._update_state(occluder="Right_Power_Flip1")
                        response = self._build_response()
                        response['auto_flip'] = True
                        response['flip_wait_seconds'] = 2
                        return response
                    else:
                        # Second time: Move to next phase
                        print("⚠️  Cylinder is 0.0 and patient chose Flip 1 again. Moving to duochrome...")
                        self.jcc_power_zero_flip1_count = 0  # Reset counter
                        return self._transition_to_duochrome_right()
                
                # Normal case: cylinder is not 0.0
                reversal = self._record_jcc_choice("flip1")
                
                # Check if we're currently at a -0.50D threshold before increase
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                
                self.jcc_control("increase")  # Phoropter increases cylinder by 0.25D
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.r_cyl += 0.25
                
                # Check if we crossed out of a -0.50D threshold
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                
                if was_at_threshold and not now_at_threshold:
                    # Crossed out of threshold (e.g., -0.50 → -0.25)
                    # Revert spherical equivalent compensation: SPH -0.25D
                    self.current_row.r_sph -= 0.25
                    print(f"✓ Spherical equivalent reversion: SPH decreased by -0.25D (now {self.current_row.r_sph:.2f}D)")
                    # Note: Phoropter handles this automatically, we just track it

                if reversal:
                    return self._transition_to_duochrome_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "MUCH better" in intent and ("RAM Power" in intent or "Flip 2" in intent):
                # Patient chose Flip 2 MUCH better - decrease cylinder by 0.50D
                reversal = self._record_jcc_choice("flip2")
                
                # Track spherical equivalent for each 0.25D step
                self.current_row = self._copy_row_state()
                
                # First 0.25D decrease
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                self.jcc_control("decrease")
                self.current_row.r_cyl -= 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                if not was_at_threshold and now_at_threshold:
                    self.current_row.r_sph += 0.25
                    print(f"✓ Spherical equivalent compensation: SPH increased by +0.25D (now {self.current_row.r_sph:.2f}D)")
                
                # Second 0.25D decrease
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                self.jcc_control("decrease")
                self.current_row.r_cyl -= 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                if not was_at_threshold and now_at_threshold:
                    self.current_row.r_sph += 0.25
                    print(f"✓ Spherical equivalent compensation: SPH increased by +0.25D (now {self.current_row.r_sph:.2f}D)")

                if reversal:
                    return self._transition_to_duochrome_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "RAM Power" in intent or "Flip 2" in intent:
                # Patient chose Flip 2 - Use JCC decrease operation
                reversal = self._record_jcc_choice("flip2")
                
                # Check if we're currently at a -0.50D threshold before decrease
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                
                self.jcc_control("decrease")  # Phoropter decreases cylinder by 0.25D
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.r_cyl -= 0.25
                
                # Check if we crossed into a -0.50D threshold
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.r_cyl)
                
                if not was_at_threshold and now_at_threshold:
                    # Crossed into threshold (e.g., -0.25 → -0.50)
                    # Apply spherical equivalent compensation: SPH +0.25D
                    self.current_row.r_sph += 0.25
                    print(f"✓ Spherical equivalent compensation: SPH increased by +0.25D (now {self.current_row.r_sph:.2f}D)")
                    # Note: Phoropter handles this automatically, we just track it

                if reversal:
                    return self._transition_to_duochrome_right()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Right_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "Both Same" in intent or "Reverse" in intent or (self.current_row.r_cyl == 0.0 and "GAP" in intent):
                return self._transition_to_duochrome_right()
            

        return self._build_response()
    
    def _process_jcc_power_left(self, intent: str) -> Dict:
        """Process JCC power refinement for left eye."""
        if self.jcc_flip_state == "flip1":
            # Auto-progress from Flip1 to Flip2
            if intent == "AUTO_FLIP":
                self.jcc_flip_state = "flip2"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Left_Power_Flip2")
                self.jcc_control("handle")
                return self._build_response()
            else:
                # Initial entry - show Flip1 and request auto-flip
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
        
        elif self.jcc_flip_state == "flip2":
            if "Repeat" in intent:
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self.current_row = self._copy_row_state()
                self._update_state(occluder="Left_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            if "MUCH better" in intent and ("GAP Power" in intent or "Flip 1" in intent):
                # Patient chose Flip 1 MUCH better - increase cylinder by 0.50D
                
                # Special handling: If cylinder is 0.0, cannot increase (would go positive)
                if self.current_row.l_cyl == 0.0:
                    self.jcc_power_zero_flip1_count += 1
                    
                    if self.jcc_power_zero_flip1_count == 1:
                        # First time: Repeat the flip cycle
                        print("⚠️  Cylinder is 0.0, cannot increase. Repeating flip cycle...")
                        self.jcc_control("handle")
                        self.jcc_flip_state = "flip1"
                        self.current_row = self._copy_row_state()
                        self._update_state(occluder="Left_Power_Flip1")
                        response = self._build_response()
                        response['auto_flip'] = True
                        response['flip_wait_seconds'] = 2
                        return response
                    else:
                        # Second time: Move to next phase
                        print("⚠️  Cylinder is 0.0 and patient chose Flip 1 again. Moving to duochrome...")
                        self.jcc_power_zero_flip1_count = 0  # Reset counter
                        return self._transition_to_duochrome_left()
                
                # Normal case: increase by 0.50D (call increase twice)
                reversal = self._record_jcc_choice("flip1")
                
                # Track spherical equivalent for each 0.25D step
                self.current_row = self._copy_row_state()
                
                # First 0.25D increase
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                self.jcc_control("increase")
                self.current_row.l_cyl += 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                if was_at_threshold and not now_at_threshold:
                    self.current_row.l_sph -= 0.25
                    print(f"✓ Spherical equivalent reversion: SPH decreased by -0.25D (now {self.current_row.l_sph:.2f}D)")
                
                # Second 0.25D increase
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                self.jcc_control("increase")
                self.current_row.l_cyl += 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                if was_at_threshold and not now_at_threshold:
                    self.current_row.l_sph -= 0.25
                    print(f"✓ Spherical equivalent reversion: SPH decreased by -0.25D (now {self.current_row.l_sph:.2f}D)")

                if reversal:
                    return self._transition_to_duochrome_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "GAP Power" in intent or "Flip 1" in intent:
                # Patient chose Flip 1 - Use JCC increase operation
                
                # Special handling: If cylinder is 0.0, cannot increase (would go positive)
                if self.current_row.l_cyl == 0.0:
                    self.jcc_power_zero_flip1_count += 1
                    
                    if self.jcc_power_zero_flip1_count == 1:
                        # First time: Repeat the flip cycle
                        print("⚠️  Cylinder is 0.0, cannot increase. Repeating flip cycle...")
                        self.jcc_control("handle")
                        self.jcc_flip_state = "flip1"
                        self.current_row = self._copy_row_state()
                        self._update_state(occluder="Left_Power_Flip1")
                        response = self._build_response()
                        response['auto_flip'] = True
                        response['flip_wait_seconds'] = 2
                        return response
                    else:
                        # Second time: Move to next phase
                        print("⚠️  Cylinder is 0.0 and patient chose Flip 1 again. Moving to duochrome...")
                        self.jcc_power_zero_flip1_count = 0  # Reset counter
                        return self._transition_to_duochrome_left()
                
                # Normal case: cylinder is not 0.0
                reversal = self._record_jcc_choice("flip1")
                
                # Check if we're currently at a -0.50D threshold before increase
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                
                self.jcc_control("increase")  # Phoropter increases cylinder by 0.25D
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.l_cyl += 0.25
                
                # Check if we crossed out of a -0.50D threshold
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                
                if was_at_threshold and not now_at_threshold:
                    # Crossed out of threshold (e.g., -0.50 → -0.25)
                    # Revert spherical equivalent compensation: SPH -0.25D
                    self.current_row.l_sph -= 0.25
                    print(f"✓ Spherical equivalent reversion: SPH decreased by -0.25D (now {self.current_row.l_sph:.2f}D)")
                    # Note: Phoropter handles this automatically, we just track it

                if reversal:
                    return self._transition_to_duochrome_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "MUCH better" in intent and ("RAM Power" in intent or "Flip 2" in intent):
                # Patient chose Flip 2 MUCH better - decrease cylinder by 0.50D
                reversal = self._record_jcc_choice("flip2")
                
                # Track spherical equivalent for each 0.25D step
                self.current_row = self._copy_row_state()
                
                # First 0.25D decrease
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                self.jcc_control("decrease")
                self.current_row.l_cyl -= 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                if not was_at_threshold and now_at_threshold:
                    self.current_row.l_sph += 0.25
                    print(f"✓ Spherical equivalent compensation: SPH increased by +0.25D (now {self.current_row.l_sph:.2f}D)")
                
                # Second 0.25D decrease
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                self.jcc_control("decrease")
                self.current_row.l_cyl -= 0.25
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                if not was_at_threshold and now_at_threshold:
                    self.current_row.l_sph += 0.25
                    print(f"✓ Spherical equivalent compensation: SPH increased by +0.25D (now {self.current_row.l_sph:.2f}D)")

                if reversal:
                    return self._transition_to_duochrome_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            elif "RAM Power" in intent or "Flip 2" in intent:
                # Patient chose Flip 2 - Use JCC decrease operation
                reversal = self._record_jcc_choice("flip2")
                
                # Check if we're currently at a -0.50D threshold before decrease
                was_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                
                self.jcc_control("decrease")  # Phoropter decreases cylinder by 0.25D
                
                # Update internal state (phoropter handles actual value)
                self.current_row = self._copy_row_state()
                self.current_row.l_cyl -= 0.25
                
                # Check if we crossed into a -0.50D threshold
                now_at_threshold = self._is_at_cyl_threshold(self.current_row.l_cyl)
                
                if not was_at_threshold and now_at_threshold:
                    # Crossed into threshold (e.g., -0.25 → -0.50)
                    # Apply spherical equivalent compensation: SPH +0.25D
                    self.current_row.l_sph += 0.25
                    print(f"✓ Spherical equivalent compensation: SPH increased by +0.25D (now {self.current_row.l_sph:.2f}D)")
                    # Note: Phoropter handles this automatically, we just track it

                if reversal:
                    return self._transition_to_duochrome_left()
                
                # Reset to Flip1 for next cycle
                self.jcc_control("handle")
                self.jcc_flip_state = "flip1"
                self._update_state(occluder="Left_Power_Flip1")
                response = self._build_response()
                response['auto_flip'] = True
                response['flip_wait_seconds'] = 2
                return response
            
            elif "Both Same" in intent or "Reverse" in intent or (self.current_row.l_cyl == 0.0 and "GAP" in intent):
                return self._transition_to_duochrome_left()
            

        return self._build_response()
    
    def _process_duochrome_right(self, intent: str) -> Dict:
        """Process duochrome test for right eye.
        
        Duochrome logic:
        - Red selected → RAM (Red Add Minus) → JCC decrease, SPH -= 0.25
        - Green selected → GAP (Green Add Plus) → JCC increase, SPH += 0.25
        - Both Same → Complete process (move to next phase)
        - Reversal → Complete process (move to next phase)
        - Prev State → Restore previous power values
        """
        if intent == "Red":
            # Save current state before making changes
            self.previous_state = self._copy_row_state()
            self.show_prev_state_option = True
            
            # RAM: Red Add Minus - decrease SPH
            reversal = self._record_duochrome_choice("red")
            self.jcc_control("decrease")  # Phoropter decreases SPH by 0.25D
            self.current_row = self._copy_row_state()
            self.current_row.r_sph -= 0.25
            if reversal:
                response = self._transition_to_validation_right()
                response['power'] = self._build_response()['power']
                return response
            return self._build_response()

        elif intent == "Green":
            self.previous_state = self._copy_row_state()
            self.show_prev_state_option = True
            reversal = self._record_duochrome_choice("green")
            self.jcc_control("increase")
            self.current_row = self._copy_row_state()
            self.current_row.r_sph += 0.25
            if reversal:
                response = self._transition_to_validation_right()
                response['power'] = self._build_response()['power']
                return response
            return self._build_response()

        elif intent == "Both Same":
            return self._transition_to_validation_right()
        
        elif intent == "Prev State" and self.previous_state:
            # Restore previous state
            prev_r_sph = self.previous_state.r_sph
            prev_r_cyl = self.previous_state.r_cyl
            prev_r_axis = self.previous_state.r_axis
            prev_l_sph = self.previous_state.l_sph
            prev_l_cyl = self.previous_state.l_cyl
            prev_l_axis = self.previous_state.l_axis
            
            # Current state before restoration
            curr_r_sph = self.current_row.r_sph
            curr_r_cyl = self.current_row.r_cyl
            curr_r_axis = self.current_row.r_axis
            curr_l_sph = self.current_row.l_sph
            curr_l_cyl = self.current_row.l_cyl
            curr_l_axis = self.current_row.l_axis
            
            # Restore previous state
            self.current_row = self._copy_row_state()
            self.current_row.r_sph = prev_r_sph
            self.current_row.r_cyl = prev_r_cyl
            self.current_row.r_axis = prev_r_axis
            self.current_row.l_sph = prev_l_sph
            self.current_row.l_cyl = prev_l_cyl
            self.current_row.l_axis = prev_l_axis
            
            # Use set_power_with_prev_state to restore
            self.set_power_with_prev_state(
                prev_r_sph=curr_r_sph, prev_r_cyl=curr_r_cyl, prev_r_axis=curr_r_axis,
                prev_l_sph=curr_l_sph, prev_l_cyl=curr_l_cyl, prev_l_axis=curr_l_axis,
                r_sph=prev_r_sph, r_cyl=prev_r_cyl, r_axis=prev_r_axis,
                l_sph=prev_l_sph, l_cyl=prev_l_cyl, l_axis=prev_l_axis,
                prev_aux_lens="AuxLensL",
                aux_lens="AuxLensL"
            )
            
            # Clear previous state after restoration
            self.previous_state = None
            self.show_prev_state_option = False
            
            return self._build_response()
        
        # Default fallback
        return self._build_response()
    
    def _process_duochrome_left(self, intent: str) -> Dict:
        """Process duochrome test for left eye.
        
        Duochrome logic:
        - Red selected → RAM (Red Add Minus) → JCC decrease, SPH -= 0.25
        - Green selected → GAP (Green Add Plus) → JCC increase, SPH += 0.25
        - Both Same → Complete process (move to next phase)
        - Reversal → Complete process (move to next phase)
        - Prev State → Restore previous power values
        """
        if intent == "Red":
            # Save current state before making changes
            self.previous_state = self._copy_row_state()
            self.show_prev_state_option = True
            
            # RAM: Red Add Minus - decrease SPH
            reversal = self._record_duochrome_choice("red")
            self.jcc_control("decrease")  # Phoropter decreases SPH by 0.25D
            self.current_row = self._copy_row_state()
            self.current_row.l_sph -= 0.25
            if reversal:
                response = self._transition_to_validation_left()
                if 'power' not in response:
                    response['power'] = self._build_response()['power']
                return response
            return self._build_response()

        elif intent == "Green":
            self.previous_state = self._copy_row_state()
            self.show_prev_state_option = True
            reversal = self._record_duochrome_choice("green")
            self.jcc_control("increase")
            self.current_row = self._copy_row_state()
            self.current_row.l_sph += 0.25
            if reversal:
                response = self._transition_to_validation_left()
                if 'power' not in response:
                    response['power'] = self._build_response()['power']
                return response
            return self._build_response()

        elif intent == "Both Same":
            return self._transition_to_validation_left()
        
        elif intent == "Prev State" and self.previous_state:
            # Restore previous state
            prev_r_sph = self.previous_state.r_sph
            prev_r_cyl = self.previous_state.r_cyl
            prev_r_axis = self.previous_state.r_axis
            prev_l_sph = self.previous_state.l_sph
            prev_l_cyl = self.previous_state.l_cyl
            prev_l_axis = self.previous_state.l_axis
            
            # Current state before restoration
            curr_r_sph = self.current_row.r_sph
            curr_r_cyl = self.current_row.r_cyl
            curr_r_axis = self.current_row.r_axis
            curr_l_sph = self.current_row.l_sph
            curr_l_cyl = self.current_row.l_cyl
            curr_l_axis = self.current_row.l_axis
            
            # Restore previous state
            self.current_row = self._copy_row_state()
            self.current_row.r_sph = prev_r_sph
            self.current_row.r_cyl = prev_r_cyl
            self.current_row.r_axis = prev_r_axis
            self.current_row.l_sph = prev_l_sph
            self.current_row.l_cyl = prev_l_cyl
            self.current_row.l_axis = prev_l_axis
            
            # Use set_power_with_prev_state to restore
            self.set_power_with_prev_state(
                prev_r_sph=curr_r_sph, prev_r_cyl=curr_r_cyl, prev_r_axis=curr_r_axis,
                prev_l_sph=curr_l_sph, prev_l_cyl=curr_l_cyl, prev_l_axis=curr_l_axis,
                r_sph=prev_r_sph, r_cyl=prev_r_cyl, r_axis=prev_r_axis,
                l_sph=prev_l_sph, l_cyl=prev_l_cyl, l_axis=prev_l_axis,
                prev_aux_lens="AuxLensR",
                aux_lens="AuxLensR"
            )
            
            # Clear previous state after restoration
            self.previous_state = None
            self.show_prev_state_option = False
            
            return self._build_response()
        
        # Default fallback
        return self._build_response()
    
    def _process_binocular_balance(self, intent: str) -> Dict:
        """Process binocular balance phase.
        
        BINO balancing logic:
        - Top is blurry [Right Eye] → Add 0.25D Sph in Left Eye
        - Bottom is blurry [Left Eye] → Add 0.25D Sph in Right Eye
        - Both are same → Test complete
        - Worse: Go to previous state → Restore previous power
        """
        if intent == "Top is blurry [Right Eye]":
            # Save current state before making changes
            prev_r_sph = self.current_row.r_sph
            prev_r_cyl = self.current_row.r_cyl
            prev_r_axis = self.current_row.r_axis
            prev_l_sph = self.current_row.l_sph
            prev_l_cyl = self.current_row.l_cyl
            prev_l_axis = self.current_row.l_axis
            
            self.previous_state = {
                'r_sph': prev_r_sph,
                'r_cyl': prev_r_cyl,
                'r_axis': prev_r_axis,
                'l_sph': prev_l_sph,
                'l_cyl': prev_l_cyl,
                'l_axis': prev_l_axis,
                'occluder_state': self.current_row.occluder_state,
                'chart_display': self.current_row.chart_display,
            }
            
            # Add 0.25D Sph in Left Eye
            new_l_sph = prev_l_sph + 0.25
            
            # Use vision correction API with previous state for accurate clicks
            # Both eyes are open in BINO phase, so aux_lens is "BINO"
            self.set_power_with_prev_state(
                prev_r_sph=prev_r_sph, prev_r_cyl=prev_r_cyl, prev_r_axis=prev_r_axis,
                prev_l_sph=prev_l_sph, prev_l_cyl=prev_l_cyl, prev_l_axis=prev_l_axis,
                r_sph=prev_r_sph, r_cyl=prev_r_cyl, r_axis=prev_r_axis,
                l_sph=new_l_sph, l_cyl=prev_l_cyl, l_axis=prev_l_axis,
                # prev_aux_lens="BINO",
                # aux_lens="BINO"
            )
            
            # Enable "Prev State" option for next response
            self.show_prev_state_option = True
            return self._build_response()
        
        elif intent == "Bottom is blurry [Left Eye]":
            # Save current state before making changes
            prev_r_sph = self.current_row.r_sph
            prev_r_cyl = self.current_row.r_cyl
            prev_r_axis = self.current_row.r_axis
            prev_l_sph = self.current_row.l_sph
            prev_l_cyl = self.current_row.l_cyl
            prev_l_axis = self.current_row.l_axis
            
            self.previous_state = {
                'r_sph': prev_r_sph,
                'r_cyl': prev_r_cyl,
                'r_axis': prev_r_axis,
                'l_sph': prev_l_sph,
                'l_cyl': prev_l_cyl,
                'l_axis': prev_l_axis,
                'occluder_state': self.current_row.occluder_state,
                'chart_display': self.current_row.chart_display,
            }
            
            # Add 0.25D Sph in Right Eye
            new_r_sph = prev_r_sph + 0.25
            
            # Use vision correction API with previous state for accurate clicks
            # Both eyes are open in BINO phase, so aux_lens is "BINO"
            self.set_power_with_prev_state(
                prev_r_sph=prev_r_sph, prev_r_cyl=prev_r_cyl, prev_r_axis=prev_r_axis,
                prev_l_sph=prev_l_sph, prev_l_cyl=prev_l_cyl, prev_l_axis=prev_l_axis,
                r_sph=new_r_sph, r_cyl=prev_r_cyl, r_axis=prev_r_axis,
                l_sph=prev_l_sph, l_cyl=prev_l_cyl, l_axis=prev_l_axis,
                # prev_aux_lens="BINO",
                # aux_lens="BINO"
            )
            
            # Enable "Prev State" option for next response
            self.show_prev_state_option = True
            return self._build_response()
        
        elif intent == "Both are same":
            # Binocular balance complete → Near Vision Right Eye (Phase P)
            return self._transition_to_near_add_right()
        
        elif intent == "Prev State":
            # Restore previous state
            if self.previous_state is not None:
                # Get current state before restoring
                curr_r_sph = self.current_row.r_sph
                curr_r_cyl = self.current_row.r_cyl
                curr_r_axis = self.current_row.r_axis
                curr_l_sph = self.current_row.l_sph
                curr_l_cyl = self.current_row.l_cyl
                curr_l_axis = self.current_row.l_axis
                
                # Get previous state values
                prev_r_sph = self.previous_state['r_sph']
                prev_r_cyl = self.previous_state['r_cyl']
                prev_r_axis = self.previous_state['r_axis']
                prev_l_sph = self.previous_state['l_sph']
                prev_l_cyl = self.previous_state['l_cyl']
                prev_l_axis = self.previous_state['l_axis']
                
                # Use vision correction API with previous state to restore
                # Both eyes are open in BINO phase, so aux_lens is "BINO"
                self.set_power_with_prev_state(
                    prev_r_sph=curr_r_sph, prev_r_cyl=curr_r_cyl, prev_r_axis=curr_r_axis,
                    prev_l_sph=curr_l_sph, prev_l_cyl=curr_l_cyl, prev_l_axis=curr_l_axis,
                    r_sph=prev_r_sph, r_cyl=prev_r_cyl, r_axis=prev_r_axis,
                    l_sph=prev_l_sph, l_cyl=prev_l_cyl, l_axis=prev_l_axis,
                    # prev_aux_lens="BINO",
                    # aux_lens="BINO"
                )
                
                self.previous_state = None
                self.show_prev_state_option = False
                print("✓ Restored to previous state")
            return self._build_response()
        
        # Default fallback
        return self._build_response()

    def _process_validation_right(self, intent: str) -> Dict:
        """Process 20/20 validation for right eye (Phase H).
        Yes → next phase. No/Blurry/Stressful → 20/40 fallback. Better/Same/Worse → refine or revert.
        """
        # Already in fallback: handle Better / Same / Worse
        if self._validation_fallback_active == "right":
            if intent == "Same":
                self._validation_fallback_active = None
                self.validation_right_status = "passed"
                return self._transition_to_left_eye_refraction()
            if intent == "Worse":
                # Revert right eye to fallback power
                fb = self.validation_right_fallback_power
                curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
                self.current_row.r_sph = fb["r_sph"]
                self.current_row.r_cyl = fb["r_cyl"]
                self.current_row.r_axis = fb["r_axis"]
                self.set_power_with_prev_state(
                    prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                    prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                    r_sph=fb["r_sph"], r_cyl=fb["r_cyl"], r_axis=fb["r_axis"],
                    l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
                )
                self._validation_fallback_active = None
                self.validation_right_status = "reverted"
                return self._transition_to_left_eye_refraction()
            if intent == "Better":
                # Refine: -0.25 SPH right eye
                self._validation_fallback_refine_count += 1
                self.jcc_control("decrease")
                self.current_row = self._copy_row_state()
                self.current_row.r_sph -= 0.25
                curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
                self.set_power_with_prev_state(
                    prev_r_sph=self.current_row.r_sph + 0.25, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                    prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                    r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                    l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
                )
                if self._validation_fallback_refine_count >= self._validation_fallback_max_refines:
                    self._validation_fallback_active = None
                    self._validation_fallback_refine_count = 0
                    self.validation_right_status = "passed"
                    return self._transition_to_left_eye_refraction()
                resp = self._build_response()
                resp["status"] = "fallback_active"
                resp["question"] = "Is this better, same, or worse?"
                resp["intents"] = ["Better", "Same", "Worse"]
                resp["message"] = "Refined -0.25D SPH. Is this better, same, or worse?"
                return resp
            return self._build_response()

        # Save current right eye power as fallback before any branch
        self.validation_right_fallback_power = {
            'r_sph': self.current_row.r_sph,
            'r_cyl': self.current_row.r_cyl,
            'r_axis': self.current_row.r_axis,
        }

        if intent == "Yes":
            self.validation_right_status = "passed"
            return self._transition_to_left_eye_refraction()

        if intent in ["No", "Blurry", "Too stressful"]:
            self.validation_right_status = "fallback_to_20_40"
            self._validation_fallback_active = "right"
            self._validation_fallback_refine_count = 0
            self.set_chart("snellen_chart_40_30_25", size="40")  # 20/40
            self.current_row.chart_display = "snellen_20_40"
            return {
                "phase": self.phase_names.get(self.current_phase, self.current_phase),
                "status": "fallback_active",
                "question": "Trying 20/40 chart. Can you read this? Is it better, same, or worse?",
                "intents": ["Better", "Same", "Worse"],
                "message": "20/20 not clear. Switched to 20/40 for refinement.",
                "chart": "snellen_20_40",
                "occluder": self.current_row.occluder_state,
                "power": self._build_response()["power"],
            }

        return self._build_response()

    def _process_validation_left(self, intent: str) -> Dict:
        """Process 20/20 validation for left eye (Phase M). Mirror of _process_validation_right."""
        if self._validation_fallback_active == "left":
            if intent == "Same":
                self._validation_fallback_active = None
                self.validation_left_status = "passed"
                return self._transition_to_validation_distance()
            if intent == "Worse":
                fb = self.validation_left_fallback_power
                curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
                self.current_row.l_sph = fb["l_sph"]
                self.current_row.l_cyl = fb["l_cyl"]
                self.current_row.l_axis = fb["l_axis"]
                self.set_power_with_prev_state(
                    prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                    prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                    r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                    l_sph=fb["l_sph"], l_cyl=fb["l_cyl"], l_axis=fb["l_axis"],
                )
                self._validation_fallback_active = None
                self.validation_left_status = "reverted"
                return self._transition_to_validation_distance()
            if intent == "Better":
                self._validation_fallback_refine_count += 1
                self.jcc_control("decrease")
                self.current_row = self._copy_row_state()
                self.current_row.l_sph -= 0.25
                curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
                self.set_power_with_prev_state(
                    prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                    prev_l_sph=self.current_row.l_sph + 0.25, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                    r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                    l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                )
                if self._validation_fallback_refine_count >= self._validation_fallback_max_refines:
                    self._validation_fallback_active = None
                    self._validation_fallback_refine_count = 0
                    self.validation_left_status = "passed"
                    return self._transition_to_validation_distance()
                resp = self._build_response()
                resp["status"] = "fallback_active"
                resp["question"] = "Is this better, same, or worse?"
                resp["intents"] = ["Better", "Same", "Worse"]
                resp["message"] = "Refined -0.25D SPH. Is this better, same, or worse?"
                return resp
            return self._build_response()

        self.validation_left_fallback_power = {
            'l_sph': self.current_row.l_sph,
            'l_cyl': self.current_row.l_cyl,
            'l_axis': self.current_row.l_axis,
        }

        if intent == "Yes":
            self.validation_left_status = "passed"
            return self._transition_to_validation_distance()

        if intent in ["No", "Blurry", "Too stressful"]:
            self.validation_left_status = "fallback_to_20_40"
            self._validation_fallback_active = "left"
            self._validation_fallback_refine_count = 0
            self.set_chart("snellen_chart_40_30_25", size="40")
            self.current_row.chart_display = "snellen_20_40"
            return {
                "phase": self.phase_names.get(self.current_phase, self.current_phase),
                "status": "fallback_active",
                "question": "Trying 20/40 chart. Can you read this? Is it better, same, or worse?",
                "intents": ["Better", "Same", "Worse"],
                "message": "20/20 not clear. Switched to 20/40 for refinement.",
                "chart": "snellen_20_40",
                "occluder": self.current_row.occluder_state,
                "power": self._build_response()["power"],
            }

        return self._build_response()

    def _process_validation_distance(self, intent: str) -> Dict:
        """Process 6/6 binocular validation (Phase N). Yes → binocular balance."""
        if intent == "Yes":
            return self._transition_to_binocular_balance()

        elif intent in ["No", "Blurry"]:
            # Allow minor refinement or proceed with caution
            return {
                "phase": self.current_phase,
                "status": "refinement_offered",
                "question": "Would you like minor binocular refinement (±0.25D) or shall we proceed?",
                "intents": ["Refine", "Proceed"],
            }

        return self._build_response()

    def _process_near_add_right(self, intent: str) -> Dict:
        """Process near vision ADD adjustment for Right eye only (Phase P).

        Right eye is tested while left is occluded. Adjusts add_right independently.
        - Blurry → +0.25D to R_ADD
        - Clear → Offer -0.25D reduction
        - Comfortable → Accept and transition to Left Eye near test
        """
        if intent == "Blurry":
            prev_add_right = self.add_right  # capture before increment
            self.add_right += 0.25
            self.current_row.r_add = self.add_right
            self.set_power_with_prev_state(
                prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                r_add=self.add_right, l_add=self.add_left,
                prev_r_add=prev_add_right, prev_l_add=self.add_left,
            )
            response = self._build_response()
            response["question"] = f"Right eye near at ADD +{self.add_right:.2f}D. Can you read clearly now?"
            response["intents"] = ["Blurry", "Clear", "Comfortable"]
            return response

        elif intent == "Clear":
            return {
                "phase": self.phase_names.get(self.current_phase, self.current_phase),
                "status": "add_refinement_offered",
                "question": "Would you like to try reducing Right eye ADD by 0.25D for more comfort?",
                "intents": ["Try reduction", "Stay current"],
                "occluder": self.current_row.occluder_state,
                "chart": self.current_row.chart_display,
                "power": self._build_response()["power"],
            }

        elif intent == "Try reduction":
            prev_add_right = self.add_right  # capture before decrement
            self.add_right = max(0.0, self.add_right - 0.25)
            self.current_row.r_add = self.add_right
            self.set_power_with_prev_state(
                prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                r_add=self.add_right, l_add=self.add_left,
                prev_r_add=prev_add_right, prev_l_add=self.add_left,
            )
            response = self._build_response()
            response["question"] = f"Right eye near at ADD +{self.add_right:.2f}D. How is this?"
            response["intents"] = ["Blurry", "Clear"]
            return response

        elif intent in ("Comfortable", "Stay current"):
            # Exit to next phase — no power change needed; ADD is already set correctly
            return self._transition_to_near_add_left()

        return self._build_response()

    def _process_near_add_left(self, intent: str) -> Dict:
        """Process near vision ADD adjustment for Left eye only (Phase Q).

        Left eye is tested while right is occluded. Adjusts add_left independently.
        - Blurry → +0.25D to L_ADD
        - Clear → Offer -0.25D reduction
        - Comfortable → Accept and transition to Binocular near test
        """
        if intent == "Blurry":
            prev_add_left = self.add_left  # capture before increment
            self.add_left += 0.25
            self.current_row.l_add = self.add_left
            self.set_power_with_prev_state(
                prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                r_add=self.add_right, l_add=self.add_left,
                prev_r_add=self.add_right, prev_l_add=prev_add_left,
            )
            response = self._build_response()
            response["question"] = f"Left eye near at ADD +{self.add_left:.2f}D. Can you read clearly now?"
            response["intents"] = ["Blurry", "Clear", "Comfortable"]
            return response

        elif intent == "Clear":
            return {
                "phase": self.phase_names.get(self.current_phase, self.current_phase),
                "status": "add_refinement_offered",
                "question": "Would you like to try reducing Left eye ADD by 0.25D for more comfort?",
                "intents": ["Try reduction", "Stay current"],
                "occluder": self.current_row.occluder_state,
                "chart": self.current_row.chart_display,
                "power": self._build_response()["power"],
            }

        elif intent == "Try reduction":
            prev_add_left = self.add_left  # capture before decrement
            self.add_left = max(0.0, self.add_left - 0.25)
            self.current_row.l_add = self.add_left
            self.set_power_with_prev_state(
                prev_r_sph=self.current_row.r_sph, prev_r_cyl=self.current_row.r_cyl, prev_r_axis=self.current_row.r_axis,
                prev_l_sph=self.current_row.l_sph, prev_l_cyl=self.current_row.l_cyl, prev_l_axis=self.current_row.l_axis,
                r_sph=self.current_row.r_sph, r_cyl=self.current_row.r_cyl, r_axis=self.current_row.r_axis,
                l_sph=self.current_row.l_sph, l_cyl=self.current_row.l_cyl, l_axis=self.current_row.l_axis,
                r_add=self.add_right, l_add=self.add_left,
                prev_r_add=self.add_right, prev_l_add=prev_add_left,
            )
            response = self._build_response()
            response["question"] = f"Left eye near at ADD +{self.add_left:.2f}D. How is this?"
            response["intents"] = ["Blurry", "Clear"]
            return response

        elif intent in ("Comfortable", "Stay current"):
            # Exit to next phase — no power change needed; ADD is already set correctly
            return self._transition_to_near_add_bino()

        return self._build_response()

    def _process_near_add_bino(self, intent: str) -> Dict:
        """Process near vision binocular ADD verification (Phase R).

        Both eyes open. Final binocular near vision check.
        Uses _set_add_bino_delta_only: sends ONLY right-eye ADD (omit left add entirely)
        so broker issues single click. Including both R+L in run-tests causes two clicks.
        - Blurry → +0.25D (single click)
        - Clear → Offer -0.25D reduction
        - Try reduction → -0.25D (single click)
        """
        ADD_STEP = 0.25
        if intent == "Blurry":
            prev_add = self.add_right
            self.add_right += ADD_STEP
            self.add_left += ADD_STEP
            self.current_row.r_add = self.add_right
            self.current_row.l_add = self.add_left
            self._set_add_bino_delta_only(prev_add=prev_add, new_add=self.add_right)
            response = self._build_response()
            response["question"] = f"Binocular near at ADD R+{self.add_right:.2f}D / L+{self.add_left:.2f}D. Comfortable now?"
            response["intents"] = ["Blurry", "Clear", "Comfortable", "Confirmed"]
            return response

        elif intent == "Clear":
            return {
                "phase": self.phase_names.get(self.current_phase, self.current_phase),
                "status": "add_refinement_offered",
                "question": "Would you like to try reducing binocular ADD by 0.25D for more comfort?",
                "intents": ["Try reduction", "Stay current", "Confirmed"],
                "occluder": self.current_row.occluder_state,
                "chart": self.current_row.chart_display,
                "power": self._build_response()["power"],
            }

        elif intent == "Try reduction":
            prev_add = self.add_right
            self.add_right = max(0.0, self.add_right - ADD_STEP)
            self.add_left = max(0.0, self.add_left - ADD_STEP)
            self.current_row.r_add = self.add_right
            self.current_row.l_add = self.add_left
            self._set_add_bino_delta_only(prev_add=prev_add, new_add=self.add_right)
            response = self._build_response()
            response["question"] = f"Binocular near at ADD R+{self.add_right:.2f}D / L+{self.add_left:.2f}D. How is this?"
            response["intents"] = ["Blurry", "Clear", "Confirmed"]
            return response

        elif intent in ("Comfortable", "Stay current"):
            # Exit to test complete — no power change needed; ADD is already set correctly
            response = self._build_response()
            response["question"] = "Excellent! Near vision comfortable with both eyes. Ready to finalize?"
            response["intents"] = ["Confirmed"]
            return response

        elif intent == "Confirmed":
            return {
                "phase": "complete",
                "status": "complete",
                "question": "Eye test complete! Near vision prescription finalized.",
                "intents": [],
                "power": {
                    "right": {
                        "sph": self.current_row.r_sph,
                        "cyl": self.current_row.r_cyl,
                        "axis": self.current_row.r_axis,
                        "add": self.add_right,
                    },
                    "left": {
                        "sph": self.current_row.l_sph,
                        "cyl": self.current_row.l_cyl,
                        "axis": self.current_row.l_axis,
                        "add": self.add_left,
                    }
                }
            }

        return self._build_response()


    def _copy_row_state(self) -> RowContext:
        """Copy current row state to new row."""
        new_row = self._init_row()
        new_row.r_sph = self.current_row.r_sph
        new_row.r_cyl = self.current_row.r_cyl
        new_row.r_axis = self.current_row.r_axis
        new_row.l_sph = self.current_row.l_sph
        new_row.l_cyl = self.current_row.l_cyl
        new_row.l_axis = self.current_row.l_axis
        new_row.occluder_state = self.current_row.occluder_state
        new_row.chart_display = self.current_row.chart_display
        return new_row
    
    def _copy_row_from_dict(self, state_dict: dict) -> RowContext:
        """Copy row state from a saved state dictionary."""
        new_row = self._init_row()
        new_row.r_sph = state_dict.get('r_sph', 0.0)
        new_row.r_cyl = state_dict.get('r_cyl', 0.0)
        new_row.r_axis = state_dict.get('r_axis', 180.0)
        new_row.l_sph = state_dict.get('l_sph', 0.0)
        new_row.l_cyl = state_dict.get('l_cyl', 0.0)
        new_row.l_axis = state_dict.get('l_axis', 180.0)
        new_row.occluder_state = state_dict.get('occluder_state', 'BINO')
        new_row.chart_display = state_dict.get('chart_display', '')
        return new_row
    
    def _is_at_cyl_threshold(self, cyl_value: float) -> bool:
        """Check if cylinder value is at a -0.50D threshold.
        
        Returns True if cyl is at -0.50, -1.00, -1.50, -2.00, etc.
        These are the points where spherical equivalent compensation is applied.
        """
        # Check if cylinder is a multiple of -0.50D
        # Account for floating point precision
        return abs(cyl_value % 0.50) < 0.01 and cyl_value < -0.01
    
    def _update_state(self, occluder: str = None, chart: str = None):
        """Update occluder and/or chart state and refresh derived fields."""
        if occluder is not None:
            self.current_row.occluder_state = occluder
        if chart is not None:
            self.current_row.chart_display = chart
        # Recalculate derived fields after manual changes
        self.current_row.update_derived_fields()
    
    def _build_response(self) -> Dict:
        """Build response with current state."""
        question = self.get_question()
        intents = self.get_intents()
        
        # Get formatted phase name with letter (A, B, etc.)
        phase_display = self.phase_names.get(self.current_phase, self.current_phase)
        
        response = {
            "phase": phase_display,
            "question": question,
            "intents": intents,
            "chart": self.current_row.chart_display,
            "occluder": self.current_row.occluder_state,
            "power": {
                "right": {
                    "sph": self.current_row.r_sph,
                    "cyl": self.current_row.r_cyl,
                    "axis": self.current_row.r_axis,
                    "add": getattr(self, "add_right", 0.0),
                },
                "left": {
                    "sph": self.current_row.l_sph,
                    "cyl": self.current_row.l_cyl,
                    "axis": self.current_row.l_axis,
                    "add": getattr(self, "add_left", 0.0),
                }
            }
        }
        
        # Add chart information if in Phase A (distance vision) or Phase B (refraction phases)
        if self.current_phase == "distance_vision":
            response["chart_info"] = {
                "available_charts": self.all_charts,
                "current_index": self.current_chart_index,
                "current_chart": self.all_charts[self.current_chart_index]
            }
        elif self.current_phase in ["right_eye_refraction", "left_eye_refraction"]:
            response["chart_info"] = {
                "available_charts": self.snellen_charts,
                "current_index": self.current_chart_index,
                "current_chart": self.snellen_charts[self.current_chart_index]
            }
        
        return response
    
    def _transition_to_jcc_axis_right(self) -> Dict:
        """Transition to JCC axis refinement for right eye."""
        self.current_phase = "jcc_axis_right"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")

        self._reset_jcc_choice_tracking()
        
        # JCC chart automatically displays when entering JCC mode - no explicit call needed
        # The phoropter defaults to Flip 1 of Axis when JCC chart is shown

        self.jcc_flip_state = "flip1"
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Right_Axis_Flip1"
        self.current_row.chart_display = "jcc_chart"
        
        # Tell frontend to auto-flip after 2 seconds
        response = self._build_response()
        response['auto_flip'] = True
        response['flip_wait_seconds'] = 2
        return response
    
    def _transition_to_jcc_axis_left(self) -> Dict:
        """Transition to JCC axis refinement for left eye."""
        self.current_phase = "jcc_axis_left"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")

        self._reset_jcc_choice_tracking()
        
        # JCC chart automatically displays when entering JCC mode - no explicit call needed
        # The phoropter defaults to Flip 1 of Axis when JCC chart is shown

        self.jcc_flip_state = "flip1"
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Left_Axis_Flip1"
        self.current_row.chart_display = "jcc_chart"
        
        # JCC chart already displayed, no need to call any JCC APIs
        # Note: Chart maintains its state, defaults to Flip 1
        
        # Tell frontend to auto-flip after 2 seconds
        response = self._build_response()
        response['auto_flip'] = True
        response['flip_wait_seconds'] = 2
        return response
    
    def _transition_to_jcc_power_right(self) -> Dict:
        """Transition to JCC power refinement for right eye."""
        self.current_phase = "jcc_power_right"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")

        self._reset_jcc_choice_tracking()
        self.jcc_power_zero_flip1_count = 0  # Reset counter for new phase
        
        self.jcc_flip_state = "flip1"
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Right_Power_Flip1"
        # self.current_row.chart_display = "jcc_chart"
        
        self.jcc_control("power_axis_switch")  # Switch to power mode - this resets to Flip 1
        
        # Tell frontend to auto-flip after 2 seconds
        response = self._build_response()
        response['auto_flip'] = True
        response['flip_wait_seconds'] = 2
        return response
    
    def _transition_to_jcc_power_left(self) -> Dict:
        """Transition to JCC power refinement for left eye."""
        self.current_phase = "jcc_power_left"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")

        self._reset_jcc_choice_tracking()
        self.jcc_power_zero_flip1_count = 0  # Reset counter for new phase
        
        self.jcc_flip_state = "flip1"
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Left_Power_Flip1"
        # self.current_row.chart_display = "jcc_chart"
        
        self.jcc_control("power_axis_switch")  # Switch to power mode - this resets to Flip 1
        
        # Tell frontend to auto-flip after 2 seconds
        response = self._build_response()
        response['auto_flip'] = True
        response['flip_wait_seconds'] = 2
        return response
    
    def _transition_to_duochrome_right(self) -> Dict:
        """Transition to duochrome test for right eye."""
        self.current_phase = "duochrome_right"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")

        self._reset_duochrome_choice_tracking()

        self._reset_jcc_choice_tracking()
        
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Left_Occluded"
        self.current_row.chart_display = "duochrome"
        
        self.set_chart("duochrome")
        
        return self._build_response()
    
    def _transition_to_duochrome_left(self) -> Dict:
        """Transition to duochrome test for left eye."""
        self.current_phase = "duochrome_left"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")

        self._reset_duochrome_choice_tracking()

        self._reset_jcc_choice_tracking()
        
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Right_Occluded"
        self.current_row.chart_display = "duochrome"
        
        self.set_chart("duochrome")
        
        return self._build_response()
    
    def _transition_to_left_eye_refraction(self) -> Dict:
        """Transition to left eye refraction.
        
        Uses vision correction API with previous state to ensure accurate click calculations
        when transitioning from right to left eye. Sets both previous and current values
        as the same to maintain current power while switching occluder.
        """
        self.current_phase = "left_eye_refraction"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        
        self.current_chart_index = 0  # Start with largest chart
        self.unable_read_count = 0
        
        # Get current power values
        curr_r_sph = self.current_row.r_sph
        curr_r_cyl = self.current_row.r_cyl
        curr_r_axis = self.current_row.r_axis
        curr_l_sph = self.current_row.l_sph
        curr_l_cyl = self.current_row.l_cyl
        curr_l_axis = self.current_row.l_axis
        
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Right_Occluded"
        self.current_row.chart_display = self.snellen_charts[0]
        
        # self.set_chart(self.snellen_charts[0])
        
        # Use vision correction API with previous state
        # Set both previous and current values as the same to maintain power while switching occluder
        self.set_power_with_prev_state(
            prev_r_sph=curr_r_sph, prev_r_cyl=curr_r_cyl, prev_r_axis=curr_r_axis,
            prev_l_sph=curr_l_sph, prev_l_cyl=curr_l_cyl, prev_l_axis=curr_l_axis,
            r_sph=curr_r_sph, r_cyl=curr_r_cyl, r_axis=curr_r_axis,
            l_sph=curr_l_sph, l_cyl=curr_l_cyl, l_axis=curr_l_axis,
            # prev_aux_lens="AuxLensL",  # Previous state was testing right eye (left occluded)
            # aux_lens="AuxLensR"  # Now testing left eye (right occluded)
        )
        
        # Explicitly click L button to activate left eye testing mode
        self.jcc_control("L")
        
        return self._build_response()
    
    def _transition_to_binocular_balance(self) -> Dict:
        """Transition to binocular balance.
        
        Uses vision correction API with previous state to ensure accurate click calculations
        when transitioning from left eye duochrome to binocular balance.
        """
        self.current_phase = "binocular_balance"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        
        # Reset previous state tracking
        self.previous_state = None
        self.show_prev_state_option = False
        
        # Get current power values
        curr_r_sph = self.current_row.r_sph
        curr_r_cyl = self.current_row.r_cyl
        curr_r_axis = self.current_row.r_axis
        curr_l_sph = self.current_row.l_sph
        curr_l_cyl = self.current_row.l_cyl
        curr_l_axis = self.current_row.l_axis
        
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "BINO"
        self.current_row.chart_display = "bino_chart"
        
        # Display BINO chart (chart_20)
        self.set_chart("bino_chart")
        
        # Use vision correction API with previous state
        # Previous state was testing left eye (right occluded), now both eyes open
        self.set_power_with_prev_state(
            prev_r_sph=curr_r_sph, prev_r_cyl=curr_r_cyl, prev_r_axis=curr_r_axis,
            prev_l_sph=curr_l_sph, prev_l_cyl=curr_l_cyl, prev_l_axis=curr_l_axis,
            r_sph=curr_r_sph, r_cyl=curr_r_cyl, r_axis=curr_r_axis,
            l_sph=curr_l_sph, l_cyl=curr_l_cyl, l_axis=curr_l_axis,
            # prev_aux_lens="AuxLensR",  # Previous state was testing left eye (right occluded)
            # aux_lens="BINO"  # Now both eyes open
        )
        
        self.jcc_control("BINO")
        
        return self._build_response()

    def _transition_to_validation_right(self) -> Dict:
        """Transition to 20/20 validation for right eye (Phase H)."""
        self.current_phase = "validation_right"
        self._track_phase_entry(self.current_phase)
        self._validation_fallback_active = None
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Left_Occluded"
        self.current_row.chart_display = "snellen_20_20"
        self.set_chart("snellen_20_20", size="20_1")
        curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
        curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
        self.set_power_with_prev_state(
            prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
            prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
            r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
            l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
        )
        self.jcc_control("R")
        return self._build_response()

    def _transition_to_validation_left(self) -> Dict:
        """Transition to 20/20 validation for left eye (Phase M)."""
        self.current_phase = "validation_left"
        self._track_phase_entry(self.current_phase)
        self._validation_fallback_active = None
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Right_Occluded"
        self.current_row.chart_display = "snellen_20_20"
        self.set_chart("snellen_20_20", size="20_1")
        curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
        curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
        self.set_power_with_prev_state(
            prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
            prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
            r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
            l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
        )
        self.jcc_control("L")
        return self._build_response()

    def _transition_to_validation_distance(self) -> Dict:
        """Transition to 6/6 binocular validation (Phase N)."""
        self.current_phase = "validation_distance"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "BINO"
        self.current_row.chart_display = "snellen_20_20"
        self.set_chart("snellen_20_20", size="20_1")
        curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
        curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
        self.set_power_with_prev_state(
            prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
            prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
            r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
            l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
        )
        self.jcc_control("BINO")
        return self._build_response()

    def _transition_to_near_add_right(self) -> Dict:
        """Transition to Near Vision ADD adjustment for Right eye (Phase P)."""
        self.current_phase = "near_add_right"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Left_Occluded"
        self.current_row.chart_display = "near_chart"
        self.set_chart_near()
        curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
        curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
        self.set_power_with_prev_state(
            prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
            prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
            r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
            l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
            r_add=self.add_right, l_add=self.add_left,
        )
        self.jcc_control("R")
        return self._build_response()

    def _transition_to_near_add_left(self) -> Dict:
        """Transition to Near Vision ADD adjustment for Left eye (Phase Q)."""
        self.current_phase = "near_add_left"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "Right_Occluded"
        self.current_row.chart_display = "near_chart"
        self.set_chart_near()
        # Do NOT re-apply power here: ADD was already set on the phoropter during
        # the Blurry iterations. Re-sending via run-tests would cause the broker
        # to recalculate ADD clicks from its stale baseline (0.00), doubling the movement.
        self.jcc_control("L")
        return self._build_response()

    def _transition_to_near_add_bino(self) -> Dict:
        """Transition to Near Vision binocular ADD verification (Phase R)."""
        self.current_phase = "near_add_bino"
        self._track_phase_entry(self.current_phase)
        print(f"\n→ Transitioning to {self.phase_names[self.current_phase]}")
        self.current_row = self._copy_row_state()
        self.current_row.occluder_state = "BINO"
        self.current_row.chart_display = "near_chart"
        self.set_chart_near()
        # Do NOT re-apply power here: ADD was already set on the phoropter during
        # the Blurry iterations. Re-sending via run-tests would cause the broker
        # to recalculate ADD clicks from its stale baseline (0.00), doubling the movement.
        self.jcc_control("BINO")
        return self._build_response()
    
    def _determine_next_phase(self, intent: str) -> str:
        """Determine next phase based on current phase and intent."""
        phase_flow = {
            "distance_vision": "right_eye_refraction",
            "right_eye_refraction": "jcc_axis_right",
            "jcc_axis_right": "jcc_power_right",
            "jcc_power_right": "duochrome_right",
            "duochrome_right": "validation_right",
            "validation_right": "left_eye_refraction",
            "left_eye_refraction": "jcc_axis_left",
            "jcc_axis_left": "jcc_power_left",
            "jcc_power_left": "duochrome_left",
            "duochrome_left": "validation_left",
            "validation_left": "validation_distance",
            "validation_distance": "binocular_balance",
            "binocular_balance": "near_add_right",
            "near_add_right": "near_add_left",
            "near_add_left": "near_add_bino",
            "near_add_bino": "complete",
        }
        return phase_flow.get(self.current_phase, "complete")
    
    def _setup_phase(self, phase: str) -> Dict:
        """Setup phoropter for the given phase.
        
        This method is used for the "Jump to Phase" feature to directly navigate
        to any phase with correct charts, sequences, and state initialization.
        
        Returns:
            Response dict with phase state, including auto_flip flag for JCC phases
        """
        # Set current phase
        self.current_phase = phase
        self._track_phase_entry(phase)
        self._phase_jump_count += 1
        print(f"\n→ Jumping to {self.phase_names.get(phase, phase)}")
        
        # Create new row for this phase
        prev_row = self.current_row
        self.current_row = self._init_row()
        
        # Copy power from previous row
        self.current_row.r_sph = prev_row.r_sph
        self.current_row.r_cyl = prev_row.r_cyl
        self.current_row.r_axis = prev_row.r_axis
        self.current_row.l_sph = prev_row.l_sph
        self.current_row.l_cyl = prev_row.l_cyl
        self.current_row.l_axis = prev_row.l_axis
        
        # Reset refraction state
        self.current_chart_index = 0
        self.unable_read_count = 0
        
        if phase == "distance_vision":
            self.set_chart("echart_400")
            self.set_power(occluder="BINO")
            self._update_state(occluder="BINO", chart="echart_400")
            
        elif phase == "right_eye_refraction":
            # Start with the first chart in the sequence (largest)
            self.current_chart_index = 0
            self.set_chart(self.snellen_charts[0])
            self.set_power(occluder="Left_Occluded")
            self._update_state(occluder="Left_Occluded", chart=self.snellen_charts[0])
            
        elif phase == "jcc_axis_right":
            # Reset JCC choice tracking
            self._reset_jcc_choice_tracking()
            self.jcc_flip_state = "flip1"
            # Display JCC chart
            self.set_chart("jcc_chart")
            # Set JCC eye mode to R (testing right eye)
            self.jcc_control("R")
            self._update_state(occluder="Right_Axis_Flip1", chart="jcc_chart")
            # Return response with auto_flip flag
            response = self._build_response()
            response['auto_flip'] = True
            response['flip_wait_seconds'] = 2
            return response
            
        elif phase == "jcc_power_right":
            # Reset JCC choice tracking and zero flip counter
            self._reset_jcc_choice_tracking()
            self.jcc_power_zero_flip1_count = 0
            self.jcc_flip_state = "flip1"
            # Display JCC chart if not already shown
            self.set_chart("jcc_chart")
            # Set JCC eye mode to R
            self.jcc_control("R")
            # Switch to power mode
            self.jcc_control("power_axis_switch")
            self._update_state(occluder="Right_Power_Flip1", chart="jcc_chart")
            # Return response with auto_flip flag
            response = self._build_response()
            response['auto_flip'] = True
            response['flip_wait_seconds'] = 2
            return response
            
        elif phase == "duochrome_right":
            # Reset duochrome choice tracking
            self._reset_duochrome_choice_tracking()
            self.set_chart("duochrome")
            self.set_power(occluder="Left_Occluded")
            self._update_state(occluder="Left_Occluded", chart="duochrome")
            
        elif phase == "left_eye_refraction":
            # Start with the first chart in the sequence (largest)
            self.current_chart_index = 0
            self.set_chart(self.snellen_charts[0])
            self.set_power(occluder="Right_Occluded")
            self._update_state(occluder="Right_Occluded", chart=self.snellen_charts[0])
            
        elif phase == "jcc_axis_left":
            # Reset JCC choice tracking
            self._reset_jcc_choice_tracking()
            self.jcc_flip_state = "flip1"
            # Display JCC chart
            self.set_chart("jcc_chart")
            # Set JCC eye mode to L (testing left eye)
            self.jcc_control("L")
            self._update_state(occluder="Left_Axis_Flip1", chart="jcc_chart")
            # Return response with auto_flip flag
            response = self._build_response()
            response['auto_flip'] = True
            response['flip_wait_seconds'] = 2
            return response
            
        elif phase == "jcc_power_left":
            # Reset JCC choice tracking and zero flip counter
            self._reset_jcc_choice_tracking()
            self.jcc_power_zero_flip1_count = 0
            self.jcc_flip_state = "flip1"
            # Display JCC chart if not already shown
            self.set_chart("jcc_chart")
            # Set JCC eye mode to L
            self.jcc_control("L")
            # Switch to power mode
            self.jcc_control("power_axis_switch")
            self._update_state(occluder="Left_Power_Flip1", chart="jcc_chart")
            # Return response with auto_flip flag
            response = self._build_response()
            response['auto_flip'] = True
            response['flip_wait_seconds'] = 2
            return response
            
        elif phase == "duochrome_left":
            self._reset_duochrome_choice_tracking()
            self.set_chart("duochrome")
            self.set_power(occluder="Right_Occluded")
            self._update_state(occluder="Right_Occluded", chart="duochrome")

        elif phase == "validation_right":
            self._validation_fallback_active = None
            self.current_row.occluder_state = "Left_Occluded"
            self.current_row.chart_display = "snellen_20_20"
            self.set_chart("snellen_20_20", size="20_1")
            self.set_power(occluder="Left_Occluded")
            self.jcc_control("R")
            self._update_state(occluder="Left_Occluded", chart="snellen_20_20")

        elif phase == "validation_left":
            self._validation_fallback_active = None
            self.current_row.occluder_state = "Right_Occluded"
            self.current_row.chart_display = "snellen_20_20"
            self.set_chart("snellen_20_20", size="20_1")
            curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
            curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
            self.set_power_with_prev_state(
                prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
            )
            self.jcc_control("L")
            self._update_state(occluder="Right_Occluded", chart="snellen_20_20")

        elif phase == "validation_distance":
            self.current_row.occluder_state = "BINO"
            self.current_row.chart_display = "snellen_20_20"
            self.set_chart("snellen_20_20", size="20_1")
            curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
            curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
            self.set_power_with_prev_state(
                prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
            )
            self.jcc_control("BINO")
            self._update_state(occluder="BINO", chart="snellen_20_20")

        elif phase == "near_add_right":
            self.current_row.occluder_state = "Left_Occluded"
            self.current_row.chart_display = "near_chart"
            self.set_chart_near()
            curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
            curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
            self.set_power_with_prev_state(
                prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
                r_add=self.add_right, l_add=self.add_left,
            )
            self.jcc_control("R")
            self._update_state(occluder="Left_Occluded", chart="near_chart")

        elif phase == "near_add_left":
            self.current_row.occluder_state = "Right_Occluded"
            self.current_row.chart_display = "near_chart"
            self.set_chart_near()
            curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
            curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
            self.set_power_with_prev_state(
                prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
                r_add=self.add_right, l_add=self.add_left,
            )
            self.jcc_control("L")
            self._update_state(occluder="Right_Occluded", chart="near_chart")

        elif phase == "near_add_bino":
            self.current_row.occluder_state = "BINO"
            self.current_row.chart_display = "near_chart"
            self.set_chart_near()
            curr_r = (self.current_row.r_sph, self.current_row.r_cyl, self.current_row.r_axis)
            curr_l = (self.current_row.l_sph, self.current_row.l_cyl, self.current_row.l_axis)
            self.set_power_with_prev_state(
                prev_r_sph=curr_r[0], prev_r_cyl=curr_r[1], prev_r_axis=curr_r[2],
                prev_l_sph=curr_l[0], prev_l_cyl=curr_l[1], prev_l_axis=curr_l[2],
                r_sph=curr_r[0], r_cyl=curr_r[1], r_axis=curr_r[2],
                l_sph=curr_l[0], l_cyl=curr_l[1], l_axis=curr_l[2],
                r_add=self.add_right, l_add=self.add_left,
            )
            self.jcc_control("BINO")
            self._update_state(occluder="BINO", chart="near_chart")
            
        elif phase == "binocular_balance":
            # Reset previous state tracking
            self.previous_state = None
            self.show_prev_state_option = False
            self.set_chart("bino_chart")
            self.set_power(occluder="BINO")
            self.jcc_control("BINO")
            self._update_state(occluder="BINO", chart="bino_chart")
        
        # Return standard response for non-JCC phases
        return self._build_response()


def main():
    """Interactive CLI demo."""
    session = InteractiveSession()
    
    print("\n" + "="*60)
    print("EYE TEST ENGINE - INTERACTIVE SESSION")
    print("="*60)
    
    # Start test
    state = session.start_distance_vision()
    
    print(f"\n📋 Phase: {state['phase']}")
    print(f"👁️  Chart: {state['chart']}")
    print(f"🔒 Occluder: {state['occluder']}")
    print(f"\n❓ Question: {state['question']}")
    print(f"\n💬 Available Intents:")
    for i, intent in enumerate(state['intents'], 1):
        print(f"   {i}. {intent}")
    
    print(f"\n🔧 Power: R({state['power']['right']['sph']}/{state['power']['right']['cyl']}/{state['power']['right']['axis']})")
    print(f"          L({state['power']['left']['sph']}/{state['power']['left']['cyl']}/{state['power']['left']['axis']})")
    
    # Wait for user input
    print(f"\n{'='*60}")
    print("Select an intent number (1-{}) or 'q' to quit:".format(len(state['intents'])))
    choice = input("> ")
    
    if choice.lower() == 'q':
        print("Session ended.")
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(state['intents']):
            selected_intent = state['intents'][idx]
            print(f"\n✓ Patient response: {selected_intent}")
            
            # Process response
            next_state = session.process_response(selected_intent)
            
            print(f"\n📋 Next Phase: {next_state['phase']}")
            print(f"❓ Next Question: {next_state['question']}")
            print(f"\n💬 Available Intents:")
            for i, intent in enumerate(next_state['intents'], 1):
                print(f"   {i}. {intent}")
        else:
            print("Invalid choice.")
    except ValueError:
        print("Invalid input.")


if __name__ == "__main__":
    main()
