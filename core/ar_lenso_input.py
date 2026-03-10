"""
AR & Lenso Input Models: Autorefractor and current lens prescription data.

Maps to the AR_Input and Lenso_Input sheets in FSMv2.
Provides per-eye Rx values used for mismatch detection and start policy.
"""
from dataclasses import dataclass
from typing import Optional, List
import math


@dataclass
class EyeRx:
    """Single-eye prescription values."""
    sph: float = 0.0     # Sphere (diopters)
    cyl: float = 0.0     # Cylinder (diopters, negative convention)
    axis: float = 0.0    # Axis (degrees, 0-180)
    add: float = 0.0     # ADD power (diopters, for presbyopia)

    def is_empty(self) -> bool:
        """Check if this Rx has no data (all zeros or defaults)."""
        return (
            abs(self.sph) < 0.001
            and abs(self.cyl) < 0.001
            and abs(self.axis) < 0.5
            and abs(self.add) < 0.001
        )

    def spherical_equivalent(self) -> float:
        """Calculate spherical equivalent: SPH + CYL/2."""
        return self.sph + self.cyl / 2.0

    def to_dict(self) -> dict:
        return {
            "sph": self.sph,
            "cyl": self.cyl,
            "axis": self.axis,
            "add": self.add,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EyeRx":
        return cls(
            sph=float(data.get("sph", 0.0)),
            cyl=float(data.get("cyl", 0.0)),
            axis=float(data.get("axis", 0.0)),
            add=float(data.get("add", 0.0)),
        )


@dataclass
class ARInput:
    """
    Autorefractor readings for both eyes.
    AR provides objective measurement of refractive error.
    """
    visit_id: str = ""
    re: EyeRx = None  # Right eye
    le: EyeRx = None  # Left eye

    def __post_init__(self):
        if self.re is None:
            self.re = EyeRx()
        if self.le is None:
            self.le = EyeRx()

    @property
    def has_data(self) -> bool:
        """Check if any AR data is present."""
        return not (self.re.is_empty() and self.le.is_empty())

    def to_dict(self) -> dict:
        return {
            "visit_id": self.visit_id,
            "re": self.re.to_dict(),
            "le": self.le.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ARInput":
        return cls(
            visit_id=data.get("visit_id", ""),
            re=EyeRx.from_dict(data.get("re", {})),
            le=EyeRx.from_dict(data.get("le", {})),
        )


@dataclass
class LensoInput:
    """
    Current lens prescription (lensometry) for both eyes.
    Lenso provides the patient's existing eyewear correction.
    Includes ADD for progressive/bifocal lenses.
    """
    visit_id: str = ""
    re: EyeRx = None  # Right eye
    le: EyeRx = None  # Left eye

    def __post_init__(self):
        if self.re is None:
            self.re = EyeRx()
        if self.le is None:
            self.le = EyeRx()

    @property
    def has_data(self) -> bool:
        """Check if any Lenso data is present."""
        return not (self.re.is_empty() and self.le.is_empty())

    @property
    def has_add(self) -> bool:
        """Check if either eye has ADD power (progressive/bifocal)."""
        return abs(self.re.add) > 0.001 or abs(self.le.add) > 0.001

    def to_dict(self) -> dict:
        return {
            "visit_id": self.visit_id,
            "re": self.re.to_dict(),
            "le": self.le.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LensoInput":
        return cls(
            visit_id=data.get("visit_id", ""),
            re=EyeRx.from_dict(data.get("re", {})),
            le=EyeRx.from_dict(data.get("le", {})),
        )


def compute_mismatch(ar_eye: EyeRx, lenso_eye: EyeRx) -> dict:
    """
    Compute mismatch between AR and Lenso for a single eye.
    Returns absolute differences for SPH, CYL, and AXIS.
    """
    delta_sph = abs(ar_eye.sph - lenso_eye.sph)
    delta_cyl = abs(ar_eye.cyl - lenso_eye.cyl)

    # Axis difference needs special handling for wrap-around (0-180)
    raw_axis_diff = abs(ar_eye.axis - lenso_eye.axis)
    delta_axis = min(raw_axis_diff, 180 - raw_axis_diff)

    return {
        "delta_sph": round(delta_sph, 2),
        "delta_cyl": round(delta_cyl, 2),
        "delta_axis": round(delta_axis, 1),
    }


def round_to_step(value: float, step: float = 0.25) -> float:
    """Round a diopter value to the nearest step (default 0.25D)."""
    return round(value / step) * step


def hybrid_average(ar_val: float, lenso_val: float, step: float = 0.25) -> float:
    """
    Compute hybrid average of AR and Lenso values.
    Result is rounded to the nearest step.
    """
    mean = (ar_val + lenso_val) / 2.0
    return round_to_step(mean, step)


def hybrid_axis_average(ar_axis: float, lenso_axis: float) -> float:
    """
    Compute hybrid average of two axis values with wrap-around handling.
    Axes are on a 0-180 range where 0 and 180 are equivalent.
    """
    # Convert to radians (double the angle for circular mean on 0-180)
    a1 = math.radians(2 * ar_axis)
    a2 = math.radians(2 * lenso_axis)

    # Circular mean
    sin_mean = (math.sin(a1) + math.sin(a2)) / 2.0
    cos_mean = (math.cos(a1) + math.cos(a2)) / 2.0

    mean_angle = math.degrees(math.atan2(sin_mean, cos_mean)) / 2.0

    # Normalize to 0-180
    if mean_angle < 0:
        mean_angle += 180.0
    if mean_angle >= 180.0:
        mean_angle -= 180.0

    return round(mean_angle)
