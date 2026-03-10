"""
Context module: Manages row-level context and normalization.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RowContext:
    """Normalized context for a single CSV row."""
    
    # Raw fields
    timestamp: str
    r_sph: float
    r_cyl: float
    r_axis: float
    r_add: float
    l_sph: float
    l_cyl: float
    l_axis: float
    l_add: float
    pd: str
    chart_number: int
    occluder_state: str
    chart_display: str
    ocr_fields_read: int
    anomalies_fixed: int
    
    # Derived fields (set in __post_init__)
    chart_type: str = ""  # snellen, echart, jcc, duochrome, near, number, pictorial
    is_flip1: bool = False
    is_flip2: bool = False
    is_axis_flip: bool = False
    is_power_flip: bool = False
    eye_tested: str = ""  # right, left, both, none
    
    # Conversation fields (if present)
    optometrist_question: Optional[str] = None
    patient_answer_intent: Optional[str] = None
    patient_confidence: Optional[str] = None
    
    # Phase tracking (populated by state machine)
    phase_id: Optional[str] = None
    phase_name: Optional[str] = None

    # Logging fields for CSV export
    row_number: int = 0
    interaction_type: str = ""  # "QnA" or "Manual"
    change_delta: str = ""  # human-readable description of what changed
    
    def __post_init__(self):
        """Derive fields after initialization."""
        self._derive_chart_type()
        self._derive_flip_state()
        self._derive_eye_tested()
    
    def _derive_chart_type(self):
        """Determine chart type from chart_display."""
        chart = self.chart_display.lower().strip()
        
        if chart.startswith("snellen_chart"):
            self.chart_type = "snellen"
        elif chart.startswith("echart"):
            self.chart_type = "echart"
        elif chart == "jcc_chart":
            self.chart_type = "jcc"
        elif chart == "duochrome":
            self.chart_type = "duochrome"
        elif chart == "near_vision":
            self.chart_type = "near"
        elif chart.startswith("number_chart"):
            self.chart_type = "number"
        elif chart == "pictorial_chart":
            self.chart_type = "pictorial"
        else:
            self.chart_type = "unknown"
    
    def _derive_flip_state(self):
        """Determine flip state from occluder."""
        occ = self.occluder_state.strip()
        
        self.is_flip1 = "Flip1" in occ
        self.is_flip2 = "Flip2" in occ
        self.is_axis_flip = "Axis" in occ
        self.is_power_flip = "Power" in occ
    
    def _derive_eye_tested(self):
        """Determine which eye is being tested."""
        occ = self.occluder_state.strip()
        
        if occ == "BINO":
            self.eye_tested = "both"
        elif occ == "Left_Occluded" or occ.startswith("Right_"):
            self.eye_tested = "right"
        elif occ == "Right_Occluded" or occ.startswith("Left_"):
            self.eye_tested = "left"
        elif occ == "Both_Occluded":
            self.eye_tested = "none"
        else:
            self.eye_tested = "unknown"
    
    def update_derived_fields(self):
        """Recalculate all derived fields after manual state changes."""
        self._derive_chart_type()
        self._derive_flip_state()
        self._derive_eye_tested()
    
    def has_sph_change(self, prev: Optional['RowContext']) -> bool:
        """Check if SPH changed from previous row."""
        if prev is None:
            return False
        
        tolerance = 0.001
        r_changed = abs(self.r_sph - prev.r_sph) > tolerance
        l_changed = abs(self.l_sph - prev.l_sph) > tolerance
        
        return r_changed or l_changed
    
    def has_cyl_change(self, prev: Optional['RowContext']) -> bool:
        """Check if CYL changed from previous row."""
        if prev is None:
            return False
        
        tolerance = 0.001
        r_changed = abs(self.r_cyl - prev.r_cyl) > tolerance
        l_changed = abs(self.l_cyl - prev.l_cyl) > tolerance
        
        return r_changed or l_changed
    
    def has_axis_change(self, prev: Optional['RowContext']) -> bool:
        """Check if AXIS changed from previous row."""
        if prev is None:
            return False
        
        tolerance = 0.5
        r_changed = abs(self.r_axis - prev.r_axis) > tolerance
        l_changed = abs(self.l_axis - prev.l_axis) > tolerance
        
        return r_changed or l_changed


def parse_row(row: dict) -> RowContext:
    """Parse a CSV row dict into a RowContext."""
    
    def safe_float(val, default=0.0):
        try:
            return float(val) if val and val.strip() else default
        except (ValueError, AttributeError):
            return default
    
    def safe_int(val, default=0):
        try:
            return int(val) if val and val.strip() else default
        except (ValueError, AttributeError):
            return default
    
    return RowContext(
        timestamp=row.get("Timestamp", ""),
        r_sph=safe_float(row.get("R_SPH")),
        r_cyl=safe_float(row.get("R_CYL")),
        r_axis=safe_float(row.get("R_AXIS")),
        r_add=safe_float(row.get("R_ADD")),
        l_sph=safe_float(row.get("L_SPH")),
        l_cyl=safe_float(row.get("L_CYL")),
        l_axis=safe_float(row.get("L_AXIS")),
        l_add=safe_float(row.get("L_ADD")),
        pd=row.get("PD", ""),
        chart_number=safe_int(row.get("Chart_Number"), -1),
        occluder_state=row.get("Occluder_State", ""),
        chart_display=row.get("Chart_Display", ""),
        ocr_fields_read=safe_int(row.get("OCR_Fields_Read")),
        anomalies_fixed=safe_int(row.get("Anomalies_Fixed")),
        optometrist_question=row.get("Optometrist_Question"),
        patient_answer_intent=row.get("Patient_Answer_Intent"),
        patient_confidence=row.get("Patient_Confidence"),
    )
