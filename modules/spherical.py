"""
Spherical refinement module.
Handles sphere (SPH) adjustments and decision logic.
"""
from typing import List, Optional
from ..core.context import RowContext


class SphericalModule:
    """Manages spherical power refinement logic."""
    
    def __init__(self, thresholds: dict):
        self.thresholds = thresholds
        self.unable_read_threshold = thresholds["sphere_refinement"]["unable_read_threshold"]
    
    def analyze_sequence(self, rows: List[RowContext], eye: str = "right") -> dict:
        """
        Analyze a sequence of refraction rows for sphere refinement.
        
        Args:
            rows: List of RowContext objects for the current phase
            eye: "right" or "left"
        
        Returns:
            dict with analysis results:
                - is_stable: bool
                - unable_read_count: int
                - sph_changes: List[float]
                - recommendation: str
        """
        unable_count = 0
        sph_changes = []
        
        for i, row in enumerate(rows):
            prev = rows[i - 1] if i > 0 else None
            
            if prev and row.has_sph_change(prev):
                sph_field = row.r_sph if eye == "right" else row.l_sph
                prev_sph = prev.r_sph if eye == "right" else prev.l_sph
                sph_changes.append(sph_field - prev_sph)
                
                if row.patient_answer_intent == "Unable to read":
                    unable_count += 1
                elif row.patient_answer_intent in ["Able to read", "Getting better"]:
                    unable_count = 0  # Reset on improvement
        
        is_stable = unable_count >= self.unable_read_threshold
        
        recommendation = "continue"
        if is_stable:
            recommendation = "move_to_cylinder"
        elif unable_count == self.unable_read_threshold - 1:
            recommendation = "one_more_attempt"
        
        return {
            "is_stable": is_stable,
            "unable_read_count": unable_count,
            "sph_changes": sph_changes,
            "recommendation": recommendation,
        }
    
    def suggest_next_sph(self, current_sph: float, intent: str, history: List[float]) -> Optional[float]:
        """
        Suggest next SPH value based on current state and history.
        
        Args:
            current_sph: Current SPH value
            intent: Patient answer intent
            history: List of recent SPH changes
        
        Returns:
            Suggested SPH value or None
        """
        if intent == "Unable to read":
            # Increase negative power (more minus)
            return current_sph - 0.25
        elif intent == "Blurry":
            # Small adjustment
            return current_sph - 0.25
        elif intent == "Getting better":
            # Continue in same direction
            if history and history[-1] < 0:
                return current_sph - 0.25
            else:
                return current_sph + 0.25
        
        return None
