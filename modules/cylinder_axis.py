"""
Cylinder axis refinement module (JCC Axis).
Handles axis adjustments using Flip1/Flip2 logic.
"""
from typing import Optional
from ..core.context import RowContext


class CylinderAxisModule:
    """Manages cylinder axis refinement using JCC flips."""
    
    def __init__(self, thresholds: dict):
        self.thresholds = thresholds
        self.axis_increment = thresholds["cylinder_refinement"]["axis_increment"]
    
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
                - choice: "flip1", "flip2", "both_same"
                - axis_change: float (degrees)
                - intent: str (GAP Axis, RAM Axis, Both Same)
                - next_axis: float
        """
        if not next_row:
            return {
                "choice": "unknown",
                "axis_change": 0.0,
                "intent": "Unknown",
                "next_axis": flip2_row.r_axis if eye == "right" else flip2_row.l_axis,
            }
        
        current_axis = flip2_row.r_axis if eye == "right" else flip2_row.l_axis
        next_axis = next_row.r_axis if eye == "right" else next_row.l_axis
        axis_change = next_axis - current_axis
        
        # Determine choice based on axis change
        if abs(axis_change) < 1.0:
            choice = "both_same"
            intent = "Both Same (no change needed)"
        elif axis_change > 0:
            choice = "flip1"
            intent = f"Flip 1: GAP Axis (patient chose Flip 1, increase axis by {abs(axis_change):.0f}°)"
        else:
            choice = "flip2"
            intent = f"Flip 2: RAM Axis (patient chose Flip 2, decrease axis by {abs(axis_change):.0f}°)"
        
        return {
            "choice": choice,
            "axis_change": axis_change,
            "intent": intent,
            "next_axis": next_axis,
        }
    
    def suggest_next_axis(self, current_axis: float, choice: str) -> float:
        """
        Suggest next axis value based on patient choice.
        
        Args:
            current_axis: Current axis value
            choice: "flip1" (GAP) or "flip2" (RAM)
        
        Returns:
            Suggested axis value
        """
        if choice == "flip1":
            # GAP: increase axis
            return (current_axis + self.axis_increment) % 180
        elif choice == "flip2":
            # RAM: decrease axis
            return (current_axis - self.axis_increment) % 180
        else:
            return current_axis
    
    def is_stable(self, recent_changes: list) -> bool:
        """
        Determine if axis refinement is stable.
        
        Args:
            recent_changes: List of recent axis changes
        
        Returns:
            True if stable (no change or oscillating)
        """
        if not recent_changes:
            return False
        
        # Check for "Both Same" in last attempt
        if abs(recent_changes[-1]) < 1.0:
            return True
        
        # Check for oscillation (change then reverse)
        if len(recent_changes) >= 2:
            if recent_changes[-1] * recent_changes[-2] < 0:
                return True
        
        return False
