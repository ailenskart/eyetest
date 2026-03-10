"""
Patient Input Model: Captures all pre-test patient data.

Maps to the Patient_Input_Master sheet in FSMv2.
Sections A-G covering demographics, symptoms, history, and preferences.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from enum import Enum


# =============================================================================
# Enums for validated fields
# =============================================================================

class Gender(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    PREFER_NOT_TO_SAY = "Prefer not to say"


class Lifestyle(str, Enum):
    INDOOR = "Indoor"
    OUTDOOR = "Outdoor"
    HYBRID = "Hybrid"


class OccupationType(str, Enum):
    STUDENT = "Student"
    DESK_JOB = "Desk-job"
    FIELD_JOB = "Field-job"
    DRIVER = "Driver"
    HOMEMAKER = "Homemaker"
    RETIRED = "Retired"
    OTHER = "Other"


class PrimaryReason(str, Enum):
    BLURRED_DISTANCE = "Blurred distance"
    BLURRED_NEAR = "Blurred near"
    HEADACHE = "Headache"
    EYE_STRAIN = "Eye strain"
    EYEWEAR_FITTING_ISSUE = "Current eyewear fitting issue"
    NEW_EYEWEAR = "New eyewear desired"
    ROUTINE_CHECK = "Routine check"


class Symptom(str, Enum):
    GLARE_HALOS_NIGHT = "Glare/halos (night)"
    NIGHT_DRIVING_DIFFICULTY = "Night driving difficulty"
    FLUCTUATING_VISION = "Fluctuating vision"
    DOUBLE_VISION = "Double vision"
    DRYNESS_BURNING = "Dryness/burning"
    WATERING = "Watering"
    SUDDEN_VISION_CHANGE = "Sudden vision change"
    DIZZINESS = "Dizziness"
    DISTORTION = "Distortion"


class WearType(str, Enum):
    SINGLE_VISION = "Single Vision"
    BIFOCAL = "Bifocal"
    PROGRESSIVE = "Progressive"
    CONTACT_LENS = "Contact Lens"
    UNKNOWN = "Unknown"


class Satisfaction(str, Enum):
    SATISFIED = "Satisfied"
    PARTIALLY_SATISFIED = "Partially satisfied"
    NOT_SATISFIED = "Not satisfied"
    NOT_APPLICABLE = "Not applicable"


class Complaint(str, Enum):
    BLUR_DISTANCE = "Blur distance"
    BLUR_NEAR = "Blur near"
    DISCOMFORT = "Discomfort"
    HEADACHE = "Headache"
    DISTORTION = "Distortion"
    DIZZINESS = "Dizziness"
    POOR_NIGHT_VISION = "Poor night vision"


class PriorSurgery(str, Enum):
    NONE = "None"
    LASIK = "LASIK"
    CATARACT = "Cataract"
    OTHER = "Other"


class Priority(str, Enum):
    SHARPEST_VISION = "Sharpest vision"
    COMFORT_FIRST = "Comfort-first"
    BALANCED = "Balanced"


class DistanceTarget(str, Enum):
    AIM_6_6 = "Aim 6/6 if possible"
    ACCEPT_6_9 = "Accept 6/9 if needed"


class NearPriority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class AdaptationTolerance(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


# =============================================================================
# Patient Input Dataclass
# =============================================================================

@dataclass
class PatientInput:
    """
    Complete patient input for a test session.
    Populated from the intake form before the test begins.
    """

    # Section A: Identifiers & Session Context
    patient_id: str = ""
    visit_id: str = ""
    test_date_time: Optional[datetime] = None

    # Section B: Demographics & Usage Profile
    age_years: int = 0
    gender: str = Gender.OTHER.value
    lifestyle: str = Lifestyle.HYBRID.value
    occupation_type: str = OccupationType.OTHER.value
    screen_time_hours: float = 0.0
    driving_time_hours: float = 0.0

    # Section C: Reason for Visit & Symptoms
    primary_reason: str = PrimaryReason.ROUTINE_CHECK.value
    symptoms_multi: List[str] = field(default_factory=list)

    # Section D: Current Eyewear & Adaptation
    currently_wearing_glasses: bool = False
    wear_type: str = WearType.UNKNOWN.value
    wear_duration_months: int = 0
    satisfaction_with_current_rx: str = Satisfaction.NOT_APPLICABLE.value
    main_complaint_current_rx: List[str] = field(default_factory=list)

    # Section E: Recency & Stability Indicators
    last_eye_test_months_ago: Optional[int] = None
    rx_change_last_time_known: bool = False
    rx_change_was_large: bool = False
    fluctuating_vision_reported: bool = False

    # Section F: Medical & Ocular History
    diabetes: bool = False
    hypertension: bool = False
    thyroid_disorder: bool = False
    prior_eye_surgery: str = PriorSurgery.NONE.value
    known_keratoconus: bool = False
    known_amblyopia: bool = False
    current_eye_infection_or_inflammation: bool = False

    # Section G: Patient Preference & Outcome Target
    priority: str = Priority.BALANCED.value
    distance_target: str = DistanceTarget.AIM_6_6.value
    near_priority: str = NearPriority.MEDIUM.value
    adaptation_tolerance: str = AdaptationTolerance.MODERATE.value

    def to_dict(self) -> dict:
        """Convert to dictionary for API serialization."""
        return {
            "patient_id": self.patient_id,
            "visit_id": self.visit_id,
            "test_date_time": self.test_date_time.isoformat() if self.test_date_time else None,
            "age_years": self.age_years,
            "gender": self.gender,
            "lifestyle": self.lifestyle,
            "occupation_type": self.occupation_type,
            "screen_time_hours": self.screen_time_hours,
            "driving_time_hours": self.driving_time_hours,
            "primary_reason": self.primary_reason,
            "symptoms_multi": self.symptoms_multi,
            "currently_wearing_glasses": self.currently_wearing_glasses,
            "wear_type": self.wear_type,
            "wear_duration_months": self.wear_duration_months,
            "satisfaction_with_current_rx": self.satisfaction_with_current_rx,
            "main_complaint_current_rx": self.main_complaint_current_rx,
            "last_eye_test_months_ago": self.last_eye_test_months_ago,
            "rx_change_last_time_known": self.rx_change_last_time_known,
            "rx_change_was_large": self.rx_change_was_large,
            "fluctuating_vision_reported": self.fluctuating_vision_reported,
            "diabetes": self.diabetes,
            "hypertension": self.hypertension,
            "thyroid_disorder": self.thyroid_disorder,
            "prior_eye_surgery": self.prior_eye_surgery,
            "known_keratoconus": self.known_keratoconus,
            "known_amblyopia": self.known_amblyopia,
            "current_eye_infection_or_inflammation": self.current_eye_infection_or_inflammation,
            "priority": self.priority,
            "distance_target": self.distance_target,
            "near_priority": self.near_priority,
            "adaptation_tolerance": self.adaptation_tolerance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatientInput":
        """Create from dictionary (API deserialization)."""
        obj = cls()
        for key, value in data.items():
            if key == "test_date_time" and isinstance(value, str):
                obj.test_date_time = datetime.fromisoformat(value)
            elif hasattr(obj, key):
                setattr(obj, key, value)
        return obj

    def validate(self) -> List[str]:
        """
        Validate required fields. Returns list of error messages.
        Empty list means valid.
        """
        errors = []

        if not self.patient_id:
            errors.append("patient_id is required")
        if not self.visit_id:
            errors.append("visit_id is required")
        if self.age_years < 3:
            errors.append("age_years must be >= 3")
        if self.screen_time_hours < 0 or self.screen_time_hours > 24:
            errors.append("screen_time_hours must be 0-24")
        if self.driving_time_hours < 0 or self.driving_time_hours > 24:
            errors.append("driving_time_hours must be 0-24")

        return errors
