"""
Binocular balance module.
Handles final verification with both eyes open.
"""
from typing import List
from ..core.context import RowContext


class BinocularBalanceModule:
    """Manages binocular balance testing logic."""
    
    def __init__(self, thresholds: dict):
        self.thresholds = thresholds
    
    def analyze_sequence(self, rows: List[RowContext]) -> dict:
        """
        Analyze binocular balance sequence.
        
        Args:
            rows: List of RowContext objects for binocular balance phase
        
        Returns:
            dict with analysis:
                - is_balanced: bool
                - clarity_level: str
                - recommendation: str
        """
        if not rows:
            return {
                "is_balanced": False,
                "clarity_level": "unknown",
                "recommendation": "No data",
            }
        
        # Check last few rows for stability
        recent_intents = [r.patient_answer_intent for r in rows[-3:] if r.patient_answer_intent]
        
        able_count = sum(1 for intent in recent_intents if "Able to read" in intent)
        unable_count = sum(1 for intent in recent_intents if "Unable to read" in intent)
        
        if able_count >= 2:
            is_balanced = True
            clarity_level = "good"
            recommendation = "Test complete"
        elif unable_count >= 2:
            is_balanced = False
            clarity_level = "poor"
            recommendation = "Re-check refraction"
        else:
            is_balanced = False
            clarity_level = "uncertain"
            recommendation = "Continue testing"
        
        return {
            "is_balanced": is_balanced,
            "clarity_level": clarity_level,
            "recommendation": recommendation,
        }
    
    def is_complete(self, rows: List[RowContext]) -> bool:
        """
        Check if binocular balance is complete.
        
        Args:
            rows: List of RowContext objects
        
        Returns:
            True if balance verified
        """
        analysis = self.analyze_sequence(rows)
        return analysis["is_balanced"]
