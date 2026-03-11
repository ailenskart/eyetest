"""
Derived Variables Engine: Computes all 36 derived variables deterministically.

Maps to the Derived Variables Master Table in FSMv2.
Takes PatientInput + ARInput + LensoInput + calibration config
and produces a complete DerivedVariables dataclass.

All logic is deterministic and parameterized via calibration.yaml.
No randomness, no ML — pure rule-based derivation.
"""
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import yaml

from .patient_input import PatientInput
from .ar_lenso_input import (
    ARInput, LensoInput, EyeRx,
    compute_mismatch, hybrid_average, hybrid_axis_average, round_to_step,
)


# =============================================================================
# Derived Variables Dataclass
# =============================================================================

@dataclass
class DerivedVariables:
    """All 36 derived variables computed from patient data."""

    # Demographics
    dv_age_bucket: str = "Adult"                     # Child / Adult / Presbyope

    # Priority & Risk
    dv_distance_priority: str = "Medium"              # High / Medium / Low
    dv_near_priority: str = "Medium"                  # High / Medium / Low
    dv_symptom_risk_level: str = "None"               # None / Moderate / High
    dv_medical_risk_level: str = "None"               # None / Moderate / High
    dv_stability_level: str = "Stable"                # Stable / Uncertain / Unstable

    # Mismatch
    dv_ar_lenso_mismatch_level_RE: str = "Small"      # Small / Medium / Large
    dv_ar_lenso_mismatch_level_LE: str = "Small"      # Small / Medium / Large

    # Start Policy
    dv_start_source_policy: str = "Start_AR"          # Start_AR / Start_Lenso / Hybrid
    dv_start_rx_RE_sph: float = 0.0
    dv_start_rx_RE_cyl: float = 0.0
    dv_start_rx_RE_axis: float = 0.0
    dv_start_rx_LE_sph: float = 0.0
    dv_start_rx_LE_cyl: float = 0.0
    dv_start_rx_LE_axis: float = 0.0
    dv_start_rx_RE_add: float = 0.0
    dv_start_rx_LE_add: float = 0.0

    # Near / ADD
    dv_add_expected: str = "None"                     # None / Possible / Likely

    # Distance Target
    dv_target_distance_va: str = "6/6_target"         # 6/6_target / 6/9_acceptable

    # Endpoint & Step
    dv_endpoint_bias_policy: str = "Neutral"          # Neutral / Undercorrect / Overcorrect
    dv_step_size_policy: str = "Standard"             # Conservative / Standard / Aggressive

    # Safety Limits
    dv_max_delta_from_start_sph: float = 2.0
    dv_max_delta_from_ar_sph: float = 3.0

    # Tolerances
    dv_axis_tolerance_deg: int = 3
    dv_cyl_tolerance_D: float = 0.25

    # Flags
    dv_requires_optom_review: bool = False
    dv_anomaly_watch: bool = False

    # Convergence
    dv_expected_convergence_time: str = "Normal"      # Fast / Normal / Slow
    dv_branching_guardrails: str = "Normal"            # Strict / Normal / Relaxed
    dv_confidence_requirement: str = "Medium"          # Low / Medium / High

    # Fogging
    dv_fogging_policy: str = "No_Fog"                 # No_Fog / Standard_Fog / Strong_Fog
    dv_fogging_amount_D: float = 0.0
    dv_fogging_clearance_mode: str = "StepDown_0.25"
    dv_fogging_required_confirmation: str = "Low"     # Low / Medium / High
    dv_fogging_confirm_count: int = 1                # Actual count: Low=1, Medium=2, High=3

    # Axis / Cylinder
    dv_axis_step_policy: str = "Normal"               # Normal / Fine
    dv_duochrome_max_flips: int = 3

    # JCC power convergence
    dv_jcc_power_same_required: int = 1              # SAME confirmations needed for JCC power

    # Near test flag
    dv_near_test_required: bool = False

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {k: v for k, v in self.__dict__.items()}


# =============================================================================
# Calibration Loader
# =============================================================================

def load_calibration(config_path: Optional[str] = None) -> dict:
    """Load calibration parameters from YAML."""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "calibration.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


# =============================================================================
# Computation Engine
# =============================================================================

def compute_derived_variables(
    patient: PatientInput,
    ar: ARInput,
    lenso: LensoInput,
    calibration: Optional[dict] = None,
) -> DerivedVariables:
    """
    Compute all 36 derived variables from inputs + calibration.

    This is the core intelligence layer of the engine.
    Every decision in the FSM is parameterized by these variables.

    Args:
        patient: Patient demographics, symptoms, preferences
        ar: Autorefractor readings
        lenso: Current lens prescription (lensometry)
        calibration: Calibration config dict (loaded from calibration.yaml if None)

    Returns:
        DerivedVariables with all 36 fields populated
    """
    if calibration is None:
        calibration = load_calibration()

    dv = DerivedVariables()
    cfg_ptdv = calibration.get("PATIENT_TO_DV", {})
    cfg_mm = calibration.get("MISMATCH_THRESHOLDS", {})
    cfg_sp = calibration.get("START_POLICY", {})
    cfg_dt = calibration.get("DISTANCE_TARGET", {})
    cfg_eb = calibration.get("ENDPOINT_BIAS", {})
    cfg_step = calibration.get("STEP_POLICY", {})
    cfg_axis = calibration.get("AXIS_POLICY", {})
    cfg_cyl = calibration.get("CYL_POLICY", {})
    cfg_fog = calibration.get("FOGGING", {})
    cfg_duo = calibration.get("DUOCHROME", {})
    cfg_esc = calibration.get("ESCALATION", {})
    cfg_near = calibration.get("NEAR_WORKFLOW", {})
    cfg_timeout = calibration.get("PHASE_TIMEOUTS", {})

    # -------------------------------------------------------------------------
    # 1. dv_age_bucket
    # -------------------------------------------------------------------------
    age = patient.age_years
    age_child_max = cfg_ptdv.get("age_child_max", 17)
    age_presbyope_min = cfg_ptdv.get("age_presbyope_min", 40)

    if age < age_child_max:
        dv.dv_age_bucket = "Child"
    elif age >= age_presbyope_min:
        dv.dv_age_bucket = "Presbyope"
    else:
        dv.dv_age_bucket = "Adult"

    # -------------------------------------------------------------------------
    # 2. dv_distance_priority
    # -------------------------------------------------------------------------
    driving_high = cfg_ptdv.get("driving_hours_high", 2)

    # Spreadsheet: compute base, then Comfort-first reduces High→Medium, Medium→Low
    base_dist = "Medium"
    if (patient.driving_time_hours >= driving_high
            or patient.occupation_type == "Driver"):
        base_dist = "High"

    if patient.priority == "Comfort-first":
        dv.dv_distance_priority = "Medium" if base_dist == "High" else "Low"
    else:
        dv.dv_distance_priority = base_dist

    # -------------------------------------------------------------------------
    # 3. dv_near_priority
    # -------------------------------------------------------------------------
    screen_high = cfg_ptdv.get("screen_time_high", 6)
    near_work_high = cfg_ptdv.get("near_work_hours_high", 4)

    # Spreadsheet: if near_priority provided use it; else check screen_time OR primary_reason
    if patient.near_priority and patient.near_priority != "Medium":
        dv.dv_near_priority = patient.near_priority
    elif (patient.screen_time_hours >= screen_high
          or patient.primary_reason == "Blurred near"):
        dv.dv_near_priority = "High"
    else:
        dv.dv_near_priority = "Medium"

    # -------------------------------------------------------------------------
    # 4. dv_symptom_risk_level
    # -------------------------------------------------------------------------
    symptoms = set(patient.symptoms_multi)
    high_symptoms = {"Sudden vision change", "Double vision"}
    moderate_symptoms = {
        "Glare/halos (night)", "Night driving difficulty",
        "Fluctuating vision",
    }

    if symptoms & high_symptoms:
        dv.dv_symptom_risk_level = "High"
    elif symptoms & moderate_symptoms:
        dv.dv_symptom_risk_level = "Moderate"
    else:
        dv.dv_symptom_risk_level = "None"

    # -------------------------------------------------------------------------
    # 5. dv_medical_risk_level
    # -------------------------------------------------------------------------
    if patient.known_keratoconus or patient.current_eye_infection_or_inflammation:
        dv.dv_medical_risk_level = "High"
    elif (patient.diabetes
          or patient.prior_eye_surgery in ["LASIK", "Cataract", "Other"]
          or patient.known_amblyopia):
        dv.dv_medical_risk_level = "Moderate"
    else:
        dv.dv_medical_risk_level = "None"

    # -------------------------------------------------------------------------
    # 6. dv_stability_level
    # -------------------------------------------------------------------------
    uncertain_months = cfg_ptdv.get("last_eye_test_uncertain_months", 24)

    if patient.fluctuating_vision_reported or patient.rx_change_was_large:
        dv.dv_stability_level = "Unstable"
    elif (patient.diabetes
          or (patient.last_eye_test_months_ago is not None
              and patient.last_eye_test_months_ago > uncertain_months)):
        dv.dv_stability_level = "Uncertain"
    else:
        dv.dv_stability_level = "Stable"

    # -------------------------------------------------------------------------
    # 7-8. dv_ar_lenso_mismatch_level (RE / LE)
    # -------------------------------------------------------------------------
    if ar.has_data and lenso.has_data:
        dv.dv_ar_lenso_mismatch_level_RE = _classify_mismatch(
            ar.re, lenso.re, cfg_mm, "re"
        )
        dv.dv_ar_lenso_mismatch_level_LE = _classify_mismatch(
            ar.le, lenso.le, cfg_mm, "le"
        )
    else:
        # If only one source, no mismatch to compute
        dv.dv_ar_lenso_mismatch_level_RE = "Small"
        dv.dv_ar_lenso_mismatch_level_LE = "Small"

    # -------------------------------------------------------------------------
    # 9. dv_start_source_policy
    # -------------------------------------------------------------------------
    dv.dv_start_source_policy = _determine_start_policy(
        patient, ar, lenso, dv, cfg_sp
    )

    # -------------------------------------------------------------------------
    # 10-15. dv_start_rx (RE & LE — SPH, CYL, AXIS)
    # -------------------------------------------------------------------------
    _compute_start_rx(dv, ar, lenso, cfg_sp)

    # -------------------------------------------------------------------------
    # 16. dv_add_expected
    # -------------------------------------------------------------------------
    add_possible_min = cfg_ptdv.get("add_possible_min_age", 38)
    add_likely_min = cfg_ptdv.get("add_likely_min_age", 42)

    if (age >= add_likely_min
            or patient.wear_type in ["Progressive", "Bifocal"]
            or lenso.has_add):
        dv.dv_add_expected = "Likely"
    elif (age >= add_possible_min and dv.dv_near_priority == "High"):
        dv.dv_add_expected = "Possible"
    else:
        dv.dv_add_expected = "None"

    # -------------------------------------------------------------------------
    # 17. dv_target_distance_va
    # -------------------------------------------------------------------------
    # Spreadsheet: if distance_target is provided, use it directly;
    # only fall through to risk checks when not specified
    target_66 = cfg_dt.get("default_distance_target", "6/6_target")
    target_69 = cfg_dt.get("high_risk_distance_target", "6/9_acceptable")

    if patient.distance_target in ("Accept 6/9 if needed", "6/9 acceptable",
                                    "6/9_acceptable"):
        dv.dv_target_distance_va = target_69
    elif patient.distance_target and patient.distance_target != "":
        # Patient explicitly chose (e.g. "Aim 6/6 if possible") — honor it
        dv.dv_target_distance_va = target_66
    elif (dv.dv_symptom_risk_level == "High"
          or dv.dv_medical_risk_level == "High"
          or dv.dv_stability_level == "Unstable"):
        dv.dv_target_distance_va = target_69
    else:
        dv.dv_target_distance_va = target_66

    # -------------------------------------------------------------------------
    # 18. dv_endpoint_bias_policy
    # -------------------------------------------------------------------------
    # Spreadsheet: High symptom risk → always Neutral (safety override)
    if dv.dv_symptom_risk_level == "High":
        dv.dv_endpoint_bias_policy = "Neutral"
    elif (patient.priority == "Comfort-first"
            and dv.dv_age_bucket == "Presbyope"
            and dv.dv_near_priority == "High"):
        dv.dv_endpoint_bias_policy = "Undercorrect"
    elif (patient.occupation_type == "Driver"
          and (symptoms & {"Night driving difficulty", "Glare/halos (night)"})):
        dv.dv_endpoint_bias_policy = "Overcorrect"
    else:
        dv.dv_endpoint_bias_policy = "Neutral"

    # -------------------------------------------------------------------------
    # 19. dv_step_size_policy
    # -------------------------------------------------------------------------
    if (dv.dv_stability_level == "Unstable"
            or dv.dv_symptom_risk_level == "High"
            or dv.dv_medical_risk_level == "High"):
        dv.dv_step_size_policy = "Conservative"
    elif (dv.dv_stability_level == "Stable"
          and dv.dv_symptom_risk_level == "None"
          and dv.dv_medical_risk_level == "None"):
        dv.dv_step_size_policy = "Aggressive"
    else:
        dv.dv_step_size_policy = "Standard"

    # -------------------------------------------------------------------------
    # 20. dv_max_delta_from_start_sph
    # -------------------------------------------------------------------------
    if dv.dv_step_size_policy == "Conservative":
        dv.dv_max_delta_from_start_sph = cfg_esc.get(
            "max_delta_start_conservative", 1.25
        )
    elif dv.dv_step_size_policy == "Aggressive":
        dv.dv_max_delta_from_start_sph = cfg_esc.get(
            "max_delta_start_aggressive", 2.5
        )
    else:
        dv.dv_max_delta_from_start_sph = cfg_esc.get(
            "max_delta_start_standard", 2.0
        )

    # -------------------------------------------------------------------------
    # 21. dv_max_delta_from_ar_sph
    # -------------------------------------------------------------------------
    # Spreadsheet: always uses standard value (no medical risk variation)
    dv.dv_max_delta_from_ar_sph = cfg_esc.get("max_delta_ar_standard", 3.0)

    # -------------------------------------------------------------------------
    # 22. dv_axis_tolerance_deg
    # -------------------------------------------------------------------------
    dv.dv_branching_guardrails = _compute_guardrails(dv)

    if dv.dv_branching_guardrails == "Strict":
        dv.dv_axis_tolerance_deg = cfg_axis.get("axis_tol_strict", 1)
    elif dv.dv_branching_guardrails == "Relaxed":
        dv.dv_axis_tolerance_deg = cfg_axis.get("axis_tol_relaxed", 5)
    else:
        dv.dv_axis_tolerance_deg = cfg_axis.get("axis_tol_normal", 3)

    # -------------------------------------------------------------------------
    # 23. dv_cyl_tolerance_D
    # -------------------------------------------------------------------------
    if dv.dv_step_size_policy == "Aggressive":
        dv.dv_cyl_tolerance_D = cfg_cyl.get("cyl_tol_aggressive", 0.50)
    elif dv.dv_step_size_policy == "Conservative":
        dv.dv_cyl_tolerance_D = cfg_cyl.get("cyl_tol_conservative", 0.25)
    else:
        dv.dv_cyl_tolerance_D = cfg_cyl.get("cyl_tol_standard", 0.25)

    # -------------------------------------------------------------------------
    # 24. dv_requires_optom_review
    # -------------------------------------------------------------------------
    # Spreadsheet: always triggers on High symptom OR High medical OR infection
    dv.dv_requires_optom_review = (
        dv.dv_symptom_risk_level == "High"
        or dv.dv_medical_risk_level == "High"
        or patient.current_eye_infection_or_inflammation
    )

    # -------------------------------------------------------------------------
    # 25. dv_anomaly_watch
    # -------------------------------------------------------------------------
    anomaly_hybrid = cfg_esc.get("anomaly_watch_if_hybrid", True)
    anomaly_unstable = cfg_esc.get("anomaly_watch_if_unstable", True)
    anomaly_mismatch = cfg_esc.get("anomaly_watch_if_large_mismatch", True)

    # Spreadsheet: triggers on ANY non-Stable (Unstable OR Uncertain)
    dv.dv_anomaly_watch = (
        (dv.dv_stability_level != "Stable")
        or (dv.dv_start_source_policy == "Hybrid")
        or (dv.dv_ar_lenso_mismatch_level_RE == "Large"
            or dv.dv_ar_lenso_mismatch_level_LE == "Large")
    )

    # -------------------------------------------------------------------------
    # 26. dv_expected_convergence_time
    # -------------------------------------------------------------------------
    # Spreadsheet: Fast requires medical_risk=None; Slow includes non-Stable and High medical
    if (dv.dv_stability_level == "Stable"
            and dv.dv_age_bucket == "Adult"
            and dv.dv_symptom_risk_level == "None"
            and dv.dv_medical_risk_level == "None"):
        dv.dv_expected_convergence_time = "Fast"
    elif (dv.dv_age_bucket == "Presbyope"
          or dv.dv_stability_level != "Stable"
          or dv.dv_symptom_risk_level == "High"
          or dv.dv_medical_risk_level == "High"):
        dv.dv_expected_convergence_time = "Slow"
    else:
        dv.dv_expected_convergence_time = "Normal"

    # -------------------------------------------------------------------------
    # 27. dv_branching_guardrails (already computed above for axis tolerance)
    # -------------------------------------------------------------------------
    # (computed in step 22)

    # -------------------------------------------------------------------------
    # 28. dv_confidence_requirement
    # -------------------------------------------------------------------------
    if (dv.dv_stability_level != "Stable"
            or dv.dv_symptom_risk_level == "High"
            or dv.dv_medical_risk_level == "High"):
        dv.dv_confidence_requirement = "High"
    elif (dv.dv_symptom_risk_level == "Moderate"
          or dv.dv_medical_risk_level == "Moderate"):
        dv.dv_confidence_requirement = "Medium"
    else:
        dv.dv_confidence_requirement = "Low"

    # -------------------------------------------------------------------------
    # 29. dv_fogging_policy
    # -------------------------------------------------------------------------
    if (dv.dv_age_bucket == "Presbyope" and cfg_fog.get("strong_fog_if_presbyope", True)):
        dv.dv_fogging_policy = "Strong_Fog"
    elif (dv.dv_stability_level == "Unstable" and cfg_fog.get("strong_fog_if_unstable", True)):
        dv.dv_fogging_policy = "Strong_Fog"
    elif (dv.dv_medical_risk_level == "High" and cfg_fog.get("strong_fog_if_high_medical", True)):
        dv.dv_fogging_policy = "Strong_Fog"
    elif (dv.dv_symptom_risk_level == "High" and cfg_fog.get("strong_fog_if_high_symptom", True)):
        dv.dv_fogging_policy = "Strong_Fog"
    elif (dv.dv_age_bucket == "Adult"
          and dv.dv_stability_level == "Stable"
          and (dv.dv_symptom_risk_level == "Moderate"
               or dv.dv_medical_risk_level == "Moderate")
          and cfg_fog.get("standard_fog_if_adult_stable_moderate_risk", True)):
        dv.dv_fogging_policy = "Standard_Fog"
    else:
        dv.dv_fogging_policy = "No_Fog"

    # -------------------------------------------------------------------------
    # 30. dv_fogging_amount_D
    # Spec: Strong→1.00D; Standard→0.75D; No fog→0
    # -------------------------------------------------------------------------
    if dv.dv_fogging_policy == "Strong_Fog":
        dv.dv_fogging_amount_D = cfg_fog.get("strong_fog_amount", 1.0)
    elif dv.dv_fogging_policy == "Standard_Fog":
        dv.dv_fogging_amount_D = cfg_fog.get("standard_fog_amount", 0.75)
    else:
        dv.dv_fogging_amount_D = cfg_fog.get("no_fog_amount", 0.25)

    # -------------------------------------------------------------------------
    # 31. dv_fogging_clearance_mode
    # -------------------------------------------------------------------------
    if dv.dv_fogging_policy == "Strong_Fog":
        if dv.dv_target_distance_va == "6/9_acceptable":
            dv.dv_fogging_clearance_mode = cfg_fog.get(
                "stepdown_mode_strong_6_9", "Early_Stop_if_Risk"
            )
        else:
            dv.dv_fogging_clearance_mode = cfg_fog.get(
                "stepdown_mode_strong_6_6", "StepDown_0.25"
            )
    elif dv.dv_fogging_policy == "Standard_Fog":
        dv.dv_fogging_clearance_mode = cfg_fog.get(
            "stepdown_mode_standard", "StepDown_0.50_then_0.25"
        )
    else:
        dv.dv_fogging_clearance_mode = cfg_fog.get(
            "stepdown_mode_no_fog", "StepDown_0.50_then_0.25"
        )

    # -------------------------------------------------------------------------
    # 32. dv_fogging_required_confirmation
    # Maps confidence level to actual confirmation count from calibration
    # -------------------------------------------------------------------------
    # Computed independently per spreadsheet (not mapped from confidence_requirement):
    # Unstable OR High symptom → High; Moderate symptom/medical → Medium; else Low
    if (dv.dv_stability_level == "Unstable"
            or dv.dv_symptom_risk_level == "High"):
        dv.dv_fogging_required_confirmation = "High"
        dv.dv_fogging_confirm_count = int(cfg_fog.get("fog_confirm_high", 3))
    elif (dv.dv_symptom_risk_level == "Moderate"
          or dv.dv_medical_risk_level == "Moderate"):
        dv.dv_fogging_required_confirmation = "Medium"
        dv.dv_fogging_confirm_count = int(cfg_fog.get("fog_confirm_medium", 2))
    else:
        dv.dv_fogging_required_confirmation = "Low"
        dv.dv_fogging_confirm_count = int(cfg_fog.get("fog_confirm_low", 1))

    # -------------------------------------------------------------------------
    # 32b. dv_jcc_power_same_required
    # Maps confidence requirement to JCC power SAME confirmation count
    # -------------------------------------------------------------------------
    if dv.dv_confidence_requirement == "High":
        dv.dv_jcc_power_same_required = int(cfg_cyl.get("jcc_power_same_high", 2))
    elif dv.dv_confidence_requirement == "Medium":
        dv.dv_jcc_power_same_required = int(cfg_cyl.get("jcc_power_same_medium", 2))
    else:
        dv.dv_jcc_power_same_required = int(cfg_cyl.get("jcc_power_same_low", 1))

    # -------------------------------------------------------------------------
    # 33. dv_axis_step_policy
    # -------------------------------------------------------------------------
    if (dv.dv_stability_level == "Unstable"
            or dv.dv_symptom_risk_level == "High"
            or dv.dv_medical_risk_level == "High"):
        dv.dv_axis_step_policy = "Fine"
    else:
        dv.dv_axis_step_policy = "Normal"

    # -------------------------------------------------------------------------
    # 34. dv_duochrome_max_flips
    # Spec: Stable→2 flips; Normal→3; Unstable→4
    # Maps directly from stability_level, not branching_guardrails
    # -------------------------------------------------------------------------
    # Spreadsheet: maps from branching_guardrails (Strict/Normal/Relaxed)
    if dv.dv_branching_guardrails == "Strict":
        dv.dv_duochrome_max_flips = cfg_duo.get(
            "duochrome_max_flips_strict", 3
        )
    elif dv.dv_branching_guardrails == "Relaxed":
        dv.dv_duochrome_max_flips = cfg_duo.get(
            "duochrome_max_flips_relaxed", 5
        )
    else:
        dv.dv_duochrome_max_flips = cfg_duo.get(
            "duochrome_max_flips_normal", 4
        )

    # -------------------------------------------------------------------------
    # 35. dv_near_test_required
    # -------------------------------------------------------------------------
    trigger_possible = cfg_near.get(
        "trigger_near_if_dv_add_expected_possible", True
    )
    trigger_likely = cfg_near.get(
        "trigger_near_if_dv_add_expected_likely", True
    )
    allow_high_near = cfg_ptdv.get(
        "allow_high_near_priority_to_force_near", True
    )

    dv.dv_near_test_required = (
        (dv.dv_add_expected == "Likely" and trigger_likely)
        or (dv.dv_add_expected == "Possible" and trigger_possible)
        or (dv.dv_near_priority == "High" and allow_high_near)
    )

    return dv


# =============================================================================
# Helper Functions
# =============================================================================

def _classify_mismatch(
    ar_eye: EyeRx, lenso_eye: EyeRx, cfg: dict, eye_prefix: str
) -> str:
    """Classify AR vs Lenso mismatch for a single eye."""
    mm = compute_mismatch(ar_eye, lenso_eye)

    sph_large = cfg.get(f"{eye_prefix}_sph_large", 2.0)
    sph_medium = cfg.get(f"{eye_prefix}_sph_medium", 1.0)
    cyl_large = cfg.get(f"{eye_prefix}_cyl_large", 1.0)
    cyl_medium = cfg.get(f"{eye_prefix}_cyl_medium", 0.5)
    axis_large = cfg.get(f"{eye_prefix}_axis_large", 30)
    axis_medium = cfg.get(f"{eye_prefix}_axis_medium", 15)

    if (mm["delta_sph"] > sph_large
            or mm["delta_cyl"] > cyl_large
            or mm["delta_axis"] > axis_large):
        return "Large"
    elif (mm["delta_sph"] > sph_medium
          or mm["delta_cyl"] > cyl_medium
          or mm["delta_axis"] > axis_medium):
        return "Medium"
    else:
        return "Small"


def _determine_start_policy(
    patient: PatientInput,
    ar: ARInput,
    lenso: LensoInput,
    dv: DerivedVariables,
    cfg: dict,
) -> str:
    """Determine which Rx source to use for starting values."""
    has_ar = ar.has_data
    has_lenso = lenso.has_data

    # Only one source available
    if has_ar and not has_lenso:
        return cfg.get("if_only_ar", "Start_AR")
    if has_lenso and not has_ar:
        return cfg.get("if_only_lenso", "Start_Lenso")
    if not has_ar and not has_lenso:
        return "Start_AR"  # Fallback — should not happen in practice

    # Both available — decide based on conditions (order matches spreadsheet)
    satisfied = patient.satisfaction_with_current_rx == "Satisfied"
    small_mismatch = (
        dv.dv_ar_lenso_mismatch_level_RE == "Small"
        and dv.dv_ar_lenso_mismatch_level_LE == "Small"
    )

    # Spreadsheet checks satisfied+small FIRST
    if satisfied and small_mismatch:
        return cfg.get("if_satisfied_small_mismatch", "Start_Lenso")

    # Then unsatisfied or blur complaint
    unsatisfied_or_blur = (
        patient.satisfaction_with_current_rx == "Not satisfied"
        or patient.primary_reason in ["Blurred distance", "Blurred near"]
    )
    if unsatisfied_or_blur:
        return cfg.get("if_unsatisfied_or_blur", "Start_AR")

    # Then large mismatch or unstable
    large_mismatch = (
        dv.dv_ar_lenso_mismatch_level_RE == "Large"
        or dv.dv_ar_lenso_mismatch_level_LE == "Large"
    )
    unstable = dv.dv_stability_level == "Unstable"

    if large_mismatch or unstable:
        return cfg.get("if_large_mismatch_or_unstable", "Hybrid")

    # Fallback
    return "Start_AR"


def _compute_start_rx(
    dv: DerivedVariables,
    ar: ARInput,
    lenso: LensoInput,
    cfg: dict,
) -> None:
    """Compute starting Rx values based on start policy."""
    policy = dv.dv_start_source_policy
    step = cfg.get("hybrid_rounding_step", 0.25)

    if policy == "Start_AR":
        dv.dv_start_rx_RE_sph = ar.re.sph
        dv.dv_start_rx_RE_cyl = ar.re.cyl
        dv.dv_start_rx_RE_axis = ar.re.axis
        dv.dv_start_rx_LE_sph = ar.le.sph
        dv.dv_start_rx_LE_cyl = ar.le.cyl
        dv.dv_start_rx_LE_axis = ar.le.axis
    elif policy == "Start_Lenso":
        dv.dv_start_rx_RE_sph = lenso.re.sph
        dv.dv_start_rx_RE_cyl = lenso.re.cyl
        dv.dv_start_rx_RE_axis = lenso.re.axis
        dv.dv_start_rx_LE_sph = lenso.le.sph
        dv.dv_start_rx_LE_cyl = lenso.le.cyl
        dv.dv_start_rx_LE_axis = lenso.le.axis
    elif policy == "Hybrid":
        dv.dv_start_rx_RE_sph = hybrid_average(ar.re.sph, lenso.re.sph, step)
        dv.dv_start_rx_RE_cyl = hybrid_average(ar.re.cyl, lenso.re.cyl, step)
        # Spreadsheet: Hybrid axis uses AR value (no averaging)
        dv.dv_start_rx_RE_axis = ar.re.axis if ar.re.axis else lenso.re.axis
        dv.dv_start_rx_LE_sph = hybrid_average(ar.le.sph, lenso.le.sph, step)
        dv.dv_start_rx_LE_cyl = hybrid_average(ar.le.cyl, lenso.le.cyl, step)
        dv.dv_start_rx_LE_axis = ar.le.axis if ar.le.axis else lenso.le.axis
    else:
        # Fallback to AR
        dv.dv_start_rx_RE_sph = ar.re.sph
        dv.dv_start_rx_RE_cyl = ar.re.cyl
        dv.dv_start_rx_RE_axis = ar.re.axis
        dv.dv_start_rx_LE_sph = ar.le.sph
        dv.dv_start_rx_LE_cyl = ar.le.cyl
        dv.dv_start_rx_LE_axis = ar.le.axis

    # ADD always comes from Lenso (existing prescription) per spreadsheet
    dv.dv_start_rx_RE_add = lenso.re.add if lenso.re.add else 0.0
    dv.dv_start_rx_LE_add = lenso.le.add if lenso.le.add else 0.0


def _compute_guardrails(dv: DerivedVariables) -> str:
    """Compute branching guardrails from risk + stability."""
    if (dv.dv_symptom_risk_level == "High"
            or dv.dv_medical_risk_level == "High"
            or dv.dv_stability_level == "Unstable"):
        return "Strict"
    elif (dv.dv_stability_level == "Stable"
          and dv.dv_symptom_risk_level == "None"
          and dv.dv_medical_risk_level == "None"):
        return "Relaxed"
    else:
        return "Normal"
