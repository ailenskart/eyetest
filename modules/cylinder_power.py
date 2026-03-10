"""
Cylinder power refinement module (JCC Power).
Handles cylinder power adjustments using Flip1/Flip2 logic.
"""
from typing import Optional
from ..core.context import RowContext


class CylinderPowerModule:
    """Manages cylinder power refinement using JCC flips."""
    
    def __init__(self, thresholds: dict):
        self.thresholds = thresholds
        self.power_increment = thresholds["cylinder_refinement"]["power_increment"]
        self.zero_threshold = thresholds["cylinder_refinement"]["zero_cylinder_threshold"]
    
    def analyze_flip_pair(self, flip1_row: RowContext, flip2_row: RowContext,
                         next_row: Optional[RowContext], eye: str = "right") -> dict:
        """
        Analyze a Flip1→Flip2 pair and determine the patient's choice.
        
        Args:
            flip1_row: RowContext for Flip1
            flip2_row: RowContext for Flip2
            next_row: RowContext for the row after Flip2
            eye: "right" or "left"
        
        Returns:
            dict with analysis:
                - choice: "flip1", "flip2", "both_same", "no_cylinder"
                - cyl_change: float (diopters)
                - intent: str (GAP Power, RAM Power, Both Same)
                - next_cyl: float
        """
        current_cyl = flip2_row.r_cyl if eye == "right" else flip2_row.l_cyl
        
        # Check for 0.00 exception
        if abs(current_cyl) < self.zero_threshold:
            if flip1_row.is_flip1:  # Flip1 chosen at 0.00
                return {
                    "choice": "no_cylinder",
                    "cyl_change": 0.0,
                    "intent": "Both Same (no cylinder power)",
                    "next_cyl": 0.0,
                }
        
        if not next_row:
            return {
                "choice": "unknown",
                "cyl_change": 0.0,
                "intent": "Unknown",
                "next_cyl": current_cyl,
            }
        
        next_cyl = next_row.r_cyl if eye == "right" else next_row.l_cyl
        cyl_change = next_cyl - current_cyl
        
        # Determine choice based on cylinder change
        # Note: More positive/less negative = GAP (Flip1)
        #       More negative = RAM (Flip2)
        if abs(cyl_change) < self.zero_threshold:
            choice = "both_same"
            intent = "Both Same (no change needed)"
        elif cyl_change > 0:
            # Cylinder became more positive (less negative)
            choice = "flip1"
            intent = f"Flip 1: GAP Power (patient chose Flip 1, increase cylinder by +{abs(cyl_change):.2f}D)"
        else:
            # Cylinder became more negative
            choice = "flip2"
            intent = f"Flip 2: RAM Power (patient chose Flip 2, decrease cylinder by -{abs(cyl_change):.2f}D)"
        
        return {
            "choice": choice,
            "cyl_change": cyl_change,
            "intent": intent,
            "next_cyl": next_cyl,
        }
    
    def suggest_next_cyl(self, current_cyl: float, choice: str) -> float:
        """
        Suggest next cylinder value based on patient choice.
        
        Args:
            current_cyl: Current cylinder value
            choice: "flip1" (GAP) or "flip2" (RAM)
        
        Returns:
            Suggested cylinder value
        """
        if choice == "flip1":
            # GAP: increase cylinder (more positive/less negative)
            return current_cyl + self.power_increment
        elif choice == "flip2":
            # RAM: decrease cylinder (more negative)
            return current_cyl - self.power_increment
        else:
            return current_cyl
    
    def is_stable(self, recent_changes: list, current_cyl: float) -> bool:
        """
        Determine if cylinder power refinement is stable.
        
        Args:
            recent_changes: List of recent cylinder changes
            current_cyl: Current cylinder value
        
        Returns:
            True if stable
        """
        # Check for 0.00 cylinder
        if abs(current_cyl) < self.zero_threshold:
            return True
        
        if not recent_changes:
            return False
        
        # Check for "Both Same" in last attempt
        if abs(recent_changes[-1]) < self.zero_threshold:
            return True
        
        # Check for oscillation
        if len(recent_changes) >= 2:
            if recent_changes[-1] * recent_changes[-2] < 0:
                return True
        
        return False
