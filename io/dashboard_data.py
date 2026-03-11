"""
Read combined_metadata.csv for dashboard stats, R&R aggregates, and today's session count.
"""
import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Reuse field list from outputs if available
try:
    from .outputs import COMBINED_METADATA_FIELDS
except ImportError:
    COMBINED_METADATA_FIELDS = [
        "Session_ID", "Phoropter_ID", "Operator_Name", "Customer_Name", "Customer_Age", "Customer_Gender",
        "Start_Time", "End_Time", "Duration_Seconds", "Completion_Status", "Total_Interactions",
        "Manual_Count", "QnA_Count", "Phase_Jump_Count", "Unable_To_Read_Count",
        "AR_R_SPH", "AR_R_CYL", "AR_R_AXIS", "AR_L_SPH", "AR_L_CYL", "AR_L_AXIS",
        "Lenso_R_SPH", "Lenso_R_CYL", "Lenso_R_AXIS", "Lenso_L_SPH", "Lenso_L_CYL", "Lenso_L_AXIS",
        "Final_R_SPH", "Final_R_CYL", "Final_R_AXIS", "Final_R_ADD",
        "Final_L_SPH", "Final_L_CYL", "Final_L_AXIS", "Final_L_ADD",
        "Phases_Completed",
    ]


def _parse_date(s: str) -> Optional[date]:
    """Parse Start_Time or End_Time string to date (YYYY-MM-DD)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if len(s) >= 10:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            pass
    return None


def _to_float(s: Any, default: float = 0.0) -> float:
    if s is None or s == "":
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _to_int(s: Any, default: int = 0) -> int:
    if s is None or s == "":
        return default
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return default


def load_metadata_rows(combined_path: Path) -> List[Dict[str, Any]]:
    """Load all rows from combined_metadata.csv as list of dicts."""
    rows: List[Dict[str, Any]] = []
    if not combined_path.exists() or combined_path.stat().st_size == 0:
        return rows
    with combined_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Session_ID") and row.get("Session_ID") != "Session_ID":
                rows.append(row)
    return rows


def filter_rows(
    rows: List[Dict[str, Any]],
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    operator: Optional[str] = None,
    phoropter: Optional[str] = None,
    completion_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter rows by date range, operator, phoropter, completion status."""
    out = []
    for r in rows:
        start_d = _parse_date(r.get("Start_Time") or "")
        if from_date and (start_d is None or start_d < from_date):
            continue
        if to_date and (start_d is None or start_d > to_date):
            continue
        if operator and (r.get("Operator_Name") or "").strip() != operator.strip():
            continue
        if phoropter and (r.get("Phoropter_ID") or "").strip() != phoropter.strip():
            continue
        if completion_status and (r.get("Completion_Status") or "").strip() != completion_status.strip():
            continue
        out.append(r)
    return out


def count_today(
    combined_path: Path,
    scope: str = "global",
    phoropter_id: Optional[str] = None,
) -> int:
    """
    Count sessions that started today.
    scope: "global" -> total count; "per_phoropter" -> count for given phoropter_id.
    """
    today = date.today()
    rows = load_metadata_rows(combined_path)
    count = 0
    for r in rows:
        start_d = _parse_date(r.get("Start_Time") or "")
        if start_d != today:
            continue
        if scope == "per_phoropter" and phoropter_id is not None:
            if (r.get("Phoropter_ID") or "").strip() != (phoropter_id or "").strip():
                continue
        count += 1
    return count


def get_rr_aggregates(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    R&R aggregates: by operator and by phoropter.
    Returns {
      "by_operator": { "op1": { "count", "mean_duration_seconds", "completion_rate", "mean_phase_jump_rate" }, ... },
      "by_phoropter": { "ph1": { ... }, ... }
    }
    """
    by_op: Dict[str, List[Dict]] = {}
    by_ph: Dict[str, List[Dict]] = {}
    for r in rows:
        op = (r.get("Operator_Name") or "").strip() or "_unknown"
        ph = (r.get("Phoropter_ID") or "").strip() or "_unknown"
        by_op.setdefault(op, []).append(r)
        by_ph.setdefault(ph, []).append(r)

    def _agg(grp: List[Dict]) -> Dict[str, Any]:
        n = len(grp)
        if n == 0:
            return {"count": 0, "mean_duration_seconds": 0.0, "completion_rate": 0.0, "mean_phase_jump_rate": 0.0}
        durations = [_to_float(r.get("Duration_Seconds")) for r in grp]
        completed = sum(1 for r in grp if (r.get("Completion_Status") or "").strip().lower() == "completed")
        total_int = [_to_int(r.get("Total_Interactions"), 1) for r in grp]
        phase_jumps = [_to_int(r.get("Phase_Jump_Count")) for r in grp]
        mean_dur = sum(durations) / n
        comp_rate = completed / n
        # phase_jump_rate per session: phase_jumps / max(total_interactions, 1)
        jump_rates = [p / max(t, 1) for p, t in zip(phase_jumps, total_int)]
        mean_jump_rate = sum(jump_rates) / n if n else 0.0
        return {
            "count": n,
            "mean_duration_seconds": round(mean_dur, 1),
            "completion_rate": round(comp_rate, 3),
            "mean_phase_jump_rate": round(mean_jump_rate, 4),
        }

    return {
        "by_operator": {k: _agg(v) for k, v in by_op.items()},
        "by_phoropter": {k: _agg(v) for k, v in by_ph.items()},
    }


def export_metadata_columns() -> List[str]:
    """Column order for CSV export (matches combined_metadata.csv)."""
    return list(COMBINED_METADATA_FIELDS)
