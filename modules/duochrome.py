"""
Duochrome test module.
Handles red/green balance testing.
"""
from ..core.context import RowContext


class DuochromeModule:
    """Manages duochrome (red/green) testing logic."""
    
    def __init__(self, thresholds: dict):
        self.thresholds = thresholds
    
    def analyze_response(self, row: RowContext) -> dict:
        """
        Analyze duochrome response.
        
        Args:
            row: RowContext for duochrome row
        
        Returns:
            dict with analysis:
                - response: "red", "green", "both_same"
                - recommendation: str (adjustment suggestion)
                - eye: "right" or "left"
        """
        intent = (row.patient_answer_intent or "").lower()
        
        # Determine which eye is being tested
        if row.occluder_state == "Left_Occluded":
            eye = "right"
        elif row.occluder_state == "Right_Occluded":
            eye = "left"
        else:
            eye = "both"
        
        # Parse response
        if "red" in intent:
            response = "red"
            recommendation = "Add +0.25D (patient is slightly myopic)"
        elif "green" in intent:
            response = "green"
            recommendation = "Add -0.25D (patient is slightly hyperopic)"
        elif "both" in intent or "same" in intent:
            response = "both_same"
            recommendation = "Balanced - no adjustment needed"
        else:
            response = "unknown"
            recommendation = "Unable to determine"
        
        return {
            "response": response,
            "recommendation": recommendation,
            "eye": eye,
        }
    
    def is_complete(self, row: RowContext) -> bool:
        """
        Check if duochrome test is complete.
        
        Args:
            row: RowContext for duochrome row
        
        Returns:
            True if response received
        """
        return row.patient_answer_intent is not None and row.patient_answer_intent.strip() != ""
