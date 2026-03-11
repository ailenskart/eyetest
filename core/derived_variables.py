"""
DerivedVariables: Calculates clinical parameters based on patient metadata and hardware readings.
Derived from FSMv2.2.xlsx logic.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import math

@dataclass
class PatientInput:
    """Raw patient data for risk and parameter derivation."""
    age_years: int = 30
    occupation_type: str = "Other"
    driving_time_hours: float = 0.0
    screen_time_hours: float = 4.0
    near_work_hours: float = 2.0
    near_priority: str = "Medium"  # High, Medium, Low
    symptoms: List[str] = field(default_factory=list)
    medical_history: List[str] = field(default_factory=list)
    satisfaction_with_current_rx: str = "Neutral"  # Yes, No, Neutral, Poor
    last_eye_test_months: int = 12
    comfort_first: bool = False
    blur_complaint: bool = False

@dataclass
class HardwareInput:
    """Initial hardware readings (AR and Lenso)."""
    ar_r_sph: float = 0.0
    ar_r_cyl: float = 0.0
    ar_r_axis: float = 180.0
    ar_l_sph: float = 0.0
    ar_l_cyl: float = 0.0
    ar_l_axis: float = 180.0
    
    lenso_r_sph: float = 0.0
    lenso_r_cyl: float = 0.0
    lenso_r_axis: float = 180.0
    lenso_r_add: float = 0.0
    lenso_l_sph: float = 0.0
    lenso_l_cyl: float = 0.0
    lenso_l_axis: float = 180.0
    lenso_l_add: float = 0.0

class DerivedVariables:
    """Calculates all 'dv_' variables for the intelligent FSM."""
    
    def __init__(self, patient: PatientInput, hardware: HardwareInput):
        self.p = patient
        self.h = hardware
        
        # Calculate all derived variables
        self.dv_age_bucket = self._derive_age_bucket()
        self.dv_distance_priority = self._derive_distance_priority()
        self.dv_near_priority = self._derive_near_priority()
        self.dv_symptom_risk_level = self._derive_symptom_risk()
        self.dv_medical_risk_level = self._derive_medical_risk()
        self.dv_stability_level = self._derive_stability_level()
        
        # Mismatch levels
        self.dv_mismatch_r = self._derive_mismatch("right")
        self.dv_mismatch_l = self._derive_mismatch("left")
        
        # Policies
        self.dv_start_source_policy = self._derive_start_policy()
        self.dv_add_expected = self._derive_add_expected()
        self.dv_fogging_policy = self._derive_fogging_policy()
        self.dv_endpoint_bias_policy = self._derive_endpoint_bias()
        
        # Starting RX
        self.dv_start_rx = self._derive_start_rx()
        
        # Thresholds and Guardrails
        self.dv_requires_optom_review = self._derive_optom_review()
        self.dv_target_distance_va = "6/9_acceptable" if (self.dv_symptom_risk_level == "High" or self.dv_stability_level == "Unstable") else "6/6_target"
        self.dv_step_size_policy = "Conservative" if (self.dv_stability_level != "Stable" or self.dv_medical_risk_level == "High") else "Standard"
        
        # Adaptive Tolerances based on Excel
        self.dv_axis_tolerance_deg = self._derive_axis_tolerance()
        self.dv_cyl_tolerance_D = 0.50 if self.dv_step_size_policy == "Conservative" else 0.25
        self.dv_duochrome_max_flips = 2 if self.dv_stability_level == "Unstable" else 4
        
        # Timeout and Step Limits
        self.dv_phase_timeout_seconds = self._derive_phase_timeout()
        self.dv_max_steps_per_phase = 10 if self.dv_stability_level == "Unstable" else 20
        
    def _derive_phase_timeout(self) -> Dict[str, int]:
        """Returns timeout in seconds for each phase."""
        standard_timeout = 180 # 3 mins
        long_timeout = 300 # 5 mins
        
        timeouts = {
            "distance_vision": standard_timeout,
            "jcc_axis_right": standard_timeout,
            "jcc_power_right": standard_timeout,
            "jcc_axis_left": standard_timeout,
            "jcc_power_left": standard_timeout,
            "validation_right": long_timeout,
            "validation_left": long_timeout,
            "binocular_balance": standard_timeout,
        }
        return timeouts
        
    def _derive_axis_tolerance(self) -> int:
        """Derived from Excel stability and risk levels."""
        if self.dv_stability_level == "Unstable": return 5
        if self.dv_medical_risk_level == "High": return 3
        return 1

    def _derive_age_bucket(self) -> str:
        if self.p.age_years < 18: return "Child"
        if self.p.age_years >= 40: return "Presbyope"
        return "Adult"

    def _derive_distance_priority(self) -> str:
        if self.p.driving_time_hours >= 2.0 or self.p.occupation_type in ["Driver", "Pilot"]:
            return "High"
        if self.p.comfort_first: return "Low"
        return "Medium"

    def _derive_near_priority(self) -> str:
        if self.p.near_priority == "High" or self.p.screen_time_hours >= 6.0 or self.p.near_work_hours >= 4.0:
            return "High"
        return "Medium"

    def _derive_symptom_risk(self) -> str:
        high_symptoms = ["Sudden vision loss", "Diplopia", "New flashes/floaters"]
        mod_symptoms = ["Glare", "Halos", "Night difficulty", "Fluctuating vision"]
        if any(s in high_symptoms for s in self.p.symptoms): return "High"
        if any(s in mod_symptoms for s in self.p.symptoms): return "Moderate"
        return "None"

    def _derive_medical_risk(self) -> str:
        high_history = ["Keratoconus", "Infection", "Glaucoma"]
        mod_history = ["Diabetes", "Surgery", "Amblyopia"]
        if any(h in high_history for h in self.p.medical_history): return "High"
        if any(h in mod_history for h in self.p.medical_history): return "Moderate"
        return "None"

    def _derive_stability_level(self) -> str:
        if "Fluctuating vision" in self.p.symptoms: return "Unstable"
        if self.p.last_eye_test_months > 24: return "Uncertain"
        return "Stable"

    def _derive_mismatch(self, eye: str) -> str:
        if eye == "right":
            dsph = abs(self.h.ar_r_sph - self.h.lenso_r_sph)
            dcyl = abs(self.h.ar_r_cyl - self.h.lenso_r_cyl)
            daxis = abs(self.h.ar_r_axis - self.h.lenso_r_axis)
        else:
            dsph = abs(self.h.ar_l_sph - self.h.lenso_l_sph)
            dcyl = abs(self.h.ar_l_cyl - self.h.lenso_l_cyl)
            daxis = abs(self.h.ar_l_axis - self.h.lenso_l_axis)
        
        # Normalize axis diff (0-90 loop)
        daxis = daxis % 180
        if daxis > 90: daxis = 180 - daxis
        
        if dsph >= 1.50 or dcyl >= 1.00 or daxis >= 30: return "Large"
        if dsph >= 0.75 or dcyl >= 0.50 or daxis >= 15: return "Medium"
        return "Small"

    def _derive_start_policy(self) -> str:
        if self.p.satisfaction_with_current_rx == "Yes" and self.dv_mismatch_r == "Small" and self.dv_mismatch_l == "Small":
            return "Start_Lenso"
        if self.p.satisfaction_with_current_rx in ["No", "Poor"] or self.p.blur_complaint:
            return "Start_AR"
        if "Large" in [self.dv_mismatch_r, self.dv_mismatch_l] or self.dv_stability_level == "Unstable":
            return "Hybrid"
        return "Start_AR"

    def _derive_add_expected(self) -> str:
        if self.p.age_years >= 42 or self.h.lenso_r_add > 0 or self.h.lenso_l_add > 0:
            return "Likely"
        if 38 <= self.p.age_years <= 41 and self.dv_near_priority == "High":
            return "Possible"
        return "None"

    def _derive_fogging_policy(self) -> str:
        if self.dv_age_bucket == "Presbyope" or self.dv_symptom_risk_level == "High":
            return "Strong_Fog"
        if self.dv_symptom_risk_level == "Moderate":
            return "Standard_Fog"
        return "No_Fog"

    def _derive_endpoint_bias(self) -> str:
        if self.dv_age_bucket == "Presbyope" and self.dv_near_priority == "High":
            return "Undercorrect"
        if self.dv_distance_priority == "High":
            return "Overcorrect"  # Cautious overcorrect for drivers
        return "Neutral"

    def _derive_optom_review(self) -> bool:
        if self.dv_symptom_risk_level == "High" or self.dv_medical_risk_level == "High":
            return True
        return False

    def _round_025(self, val: float) -> float:
        return round(val * 4) / 4

    def _derive_start_rx(self) -> Dict:
        policy = self.dv_start_source_policy
        rx = {"r": {}, "l": {}}
        
        if policy == "Start_AR":
            rx["r"] = {"sph": self.h.ar_r_sph, "cyl": self.h.ar_r_cyl, "axis": self.h.ar_r_axis}
            rx["l"] = {"sph": self.h.ar_l_sph, "cyl": self.h.ar_l_cyl, "axis": self.h.ar_l_axis}
        elif policy == "Start_Lenso":
            rx["r"] = {"sph": self.h.lenso_r_sph, "cyl": self.h.lenso_r_cyl, "axis": self.h.lenso_r_axis}
            rx["l"] = {"sph": self.h.lenso_l_sph, "cyl": self.h.lenso_l_cyl, "axis": self.h.lenso_l_axis}
        else: # Hybrid
            rx["r"] = {
                "sph": self._round_025((self.h.ar_r_sph + self.h.lenso_r_sph) / 2),
                "cyl": self._round_025((self.h.ar_r_cyl + self.h.lenso_r_cyl) / 2),
                "axis": round((self.h.ar_r_axis + self.h.lenso_r_axis) / 2)
            }
            rx["l"] = {
                "sph": self._round_025((self.h.ar_l_sph + self.h.lenso_l_sph) / 2),
                "cyl": self._round_025((self.h.ar_l_cyl + self.h.lenso_l_cyl) / 2),
                "axis": round((self.h.ar_l_axis + self.h.lenso_l_axis) / 2)
            }
        return rx
