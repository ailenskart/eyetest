"""
Output handling: Write session CSV logs, metadata JSON, and combined logs.
"""
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import sys as _sys
from pathlib import Path as _Path

# Support both package import and direct-file loading (via importlib.util)
try:
    from ..core.context import RowContext
except (ImportError, ValueError):
    _parent = str(_Path(__file__).resolve().parent.parent)
    if _parent not in _sys.path:
        _sys.path.insert(0, _parent)
    from core.context import RowContext


# 19-column schema matching the plan
SESSION_CSV_FIELDS = [
    "Row_Number",
    "Timestamp",
    "Manual_or_QnA",
    "R_SPH",
    "R_CYL",
    "R_AXIS",
    "R_ADD",
    "L_SPH",
    "L_CYL",
    "L_AXIS",
    "L_ADD",
    "Occluder_State",
    "Chart_Number",
    "Chart_Display",
    "Change_Delta",
    "Current_Phase",
    "Phase_ID",
    "Optometrist_Question",
    "Patient_Answer_Intent",
]


def _ensure_dir(path: Path) -> None:
    """Create parent directories if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _row_to_dict(row: RowContext) -> dict:
    """Convert a RowContext into a flat dict matching SESSION_CSV_FIELDS."""
    return {
        "Row_Number": row.row_number,
        "Timestamp": row.timestamp,
        "Manual_or_QnA": row.interaction_type,
        "R_SPH": row.r_sph,
        "R_CYL": row.r_cyl,
        "R_AXIS": row.r_axis,
        "R_ADD": row.r_add,
        "L_SPH": row.l_sph,
        "L_CYL": row.l_cyl,
        "L_AXIS": row.l_axis,
        "L_ADD": row.l_add,
        "Occluder_State": row.occluder_state,
        "Chart_Number": row.chart_number,
        "Chart_Display": row.chart_display,
        "Change_Delta": row.change_delta,
        "Current_Phase": row.phase_name or "",
        "Phase_ID": row.phase_id or "",
        "Optometrist_Question": row.optometrist_question or "",
        "Patient_Answer_Intent": row.patient_answer_intent or "",
    }


def session_csv_string(rows: List[RowContext]) -> str:
    """Return per-session CSV content as a string (19-column schema). For remote upload."""
    if not rows:
        return ""
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=SESSION_CSV_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(_row_to_dict(row))
    return buf.getvalue()


def write_session_csv(rows: List[RowContext], output_path: Path) -> None:
    """Write per-session CSV with the 19-column schema.

    Args:
        rows: List of RowContext objects with logging fields populated.
        output_path: Path to the output CSV file.
    """
    if not rows:
        return

    _ensure_dir(output_path)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SESSION_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_row_to_dict(row))


def write_session_metadata(metadata: dict, output_path: Path) -> None:
    """Write per-session metadata as JSON.

    Args:
        metadata: Session metadata dict.
        output_path: Path to the output JSON file.
    """
    _ensure_dir(output_path)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)


def append_to_combined_log(rows: List[RowContext], session_id: str,
                           combined_path: Path) -> None:
    """Append session rows to the growing combined CSV log.

    Adds a Session_ID column as the first field so rows from different
    sessions can be distinguished.

    Args:
        rows: List of RowContext objects.
        session_id: Session identifier to tag each row.
        combined_path: Path to the combined CSV file.
    """
    if not rows:
        return

    _ensure_dir(combined_path)
    fields = ["Session_ID"] + SESSION_CSV_FIELDS
    file_exists = combined_path.exists() and combined_path.stat().st_size > 0

    with combined_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            row_dict = {"Session_ID": session_id, **_row_to_dict(row)}
            writer.writerow(row_dict)


COMBINED_METADATA_FIELDS = [
    "Session_ID",
    "Phoropter_ID",
    "Operator_Name",
    "Customer_Name",
    "Customer_Age",
    "Customer_Gender",
    "Start_Time",
    "End_Time",
    "Duration_Seconds",
    "Completion_Status",
    "Total_Interactions",
    "Manual_Count",
    "QnA_Count",
    "Phase_Jump_Count",
    "Unable_To_Read_Count",
    "AR_R_SPH", "AR_R_CYL", "AR_R_AXIS",
    "AR_L_SPH", "AR_L_CYL", "AR_L_AXIS",
    "Lenso_R_SPH", "Lenso_R_CYL", "Lenso_R_AXIS",
    "Lenso_L_SPH", "Lenso_L_CYL", "Lenso_L_AXIS",
    "Final_R_SPH", "Final_R_CYL", "Final_R_AXIS", "Final_R_ADD",
    "Final_L_SPH", "Final_L_CYL", "Final_L_AXIS", "Final_L_ADD",
    "Phases_Completed",
]


def _safe_get(d: Optional[dict], *keys, default=""):
    """Safely traverse nested dicts."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current if current is not None else default


def append_to_combined_metadata(metadata: dict, combined_path: Path) -> None:
    """Append a single metadata row to the growing combined metadata CSV.

    Args:
        metadata: Session metadata dict.
        combined_path: Path to the combined metadata CSV file.
    """
    _ensure_dir(combined_path)
    file_exists = combined_path.exists() and combined_path.stat().st_size > 0

    qm = metadata.get("quality_metrics", {})
    final = metadata.get("final_prescription", {})
    ar = metadata.get("ar", {})
    lenso = metadata.get("lensometry", {})

    flat = {
        "Session_ID": metadata.get("session_id", ""),
        "Phoropter_ID": metadata.get("phoropter_id", ""),
        "Operator_Name": metadata.get("operator_name", ""),
        "Customer_Name": metadata.get("customer_name", ""),
        "Customer_Age": metadata.get("customer_age", ""),
        "Customer_Gender": metadata.get("customer_gender", ""),
        "Start_Time": metadata.get("session_start_time", ""),
        "End_Time": metadata.get("session_end_time", ""),
        "Duration_Seconds": metadata.get("session_duration_seconds", ""),
        "Completion_Status": metadata.get("test_completion_status", ""),
        "Total_Interactions": metadata.get("total_interactions", ""),
        "Manual_Count": qm.get("manual_adjustment_count", 0),
        "QnA_Count": qm.get("qna_interaction_count", 0),
        "Phase_Jump_Count": qm.get("phase_jump_count", 0),
        "Unable_To_Read_Count": qm.get("unable_to_read_count", 0),
        "AR_R_SPH": _safe_get(ar, "right", "sph"),
        "AR_R_CYL": _safe_get(ar, "right", "cyl"),
        "AR_R_AXIS": _safe_get(ar, "right", "axis"),
        "AR_L_SPH": _safe_get(ar, "left", "sph"),
        "AR_L_CYL": _safe_get(ar, "left", "cyl"),
        "AR_L_AXIS": _safe_get(ar, "left", "axis"),
        "Lenso_R_SPH": _safe_get(lenso, "right", "sph"),
        "Lenso_R_CYL": _safe_get(lenso, "right", "cyl"),
        "Lenso_R_AXIS": _safe_get(lenso, "right", "axis"),
        "Lenso_L_SPH": _safe_get(lenso, "left", "sph"),
        "Lenso_L_CYL": _safe_get(lenso, "left", "cyl"),
        "Lenso_L_AXIS": _safe_get(lenso, "left", "axis"),
        "Final_R_SPH": _safe_get(final, "right", "sph"),
        "Final_R_CYL": _safe_get(final, "right", "cyl"),
        "Final_R_AXIS": _safe_get(final, "right", "axis"),
        "Final_R_ADD": _safe_get(final, "right", "add"),
        "Final_L_SPH": _safe_get(final, "left", "sph"),
        "Final_L_CYL": _safe_get(final, "left", "cyl"),
        "Final_L_AXIS": _safe_get(final, "left", "axis"),
        "Final_L_ADD": _safe_get(final, "left", "add"),
        "Phases_Completed": "; ".join(metadata.get("phases_completed", [])),
    }

    with combined_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMBINED_METADATA_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(flat)


def build_session_metadata(
    session_id: str,
    phoropter_id: str,
    session_start_time: datetime,
    session_end_time: datetime,
    completion_status: str,
    rows: List[RowContext],
    ar: Optional[dict] = None,
    lensometry: Optional[dict] = None,
    phase_jump_count: int = 0,
    unable_to_read_count: int = 0,
    jcc_cycles_right: int = 0,
    jcc_cycles_left: int = 0,
    phases_completed: Optional[List[str]] = None,
    phases_skipped: Optional[List[str]] = None,
    duration_per_phase: Optional[Dict[str, float]] = None,
    operator_name: str = "",
    customer_name: str = "",
    customer_age: str = "",
    customer_gender: str = "",
    qualitative_feedback: str = "",
) -> dict:
    """Build the session metadata dict from session state.

    Args:
        session_id: Session identifier.
        phoropter_id: Phoropter device identifier.
        session_start_time: When the session started.
        session_end_time: When the session ended.
        completion_status: "completed", "aborted", or "jumped".
        rows: Full session_history list.
        ar: AR power dict (right/left with sph/cyl/axis).
        lensometry: Lensometry power dict (right/left with sph/cyl/axis).
        phase_jump_count: How many times the operator jumped phases.
        unable_to_read_count: How many "unable to read" responses.
        jcc_cycles_right: JCC cycle count for right eye.
        jcc_cycles_left: JCC cycle count for left eye.
        phases_completed: List of phase IDs that were completed.
        phases_skipped: List of phase IDs that were skipped.
        duration_per_phase: Dict mapping phase_id to seconds spent.
        operator_name: Name of the optometrist conducting the test.
        customer_name: Name of the customer/patient.
        customer_age: Customer age.
        customer_gender: Customer gender.
        qualitative_feedback: Optional free-text session feedback from optometrist.

    Returns:
        Metadata dict ready for JSON serialization.
    """
    duration = (session_end_time - session_start_time).total_seconds()

    manual_count = sum(1 for r in rows if r.interaction_type == "Manual")
    qna_count = sum(1 for r in rows if r.interaction_type == "QnA")

    final_rx = {}
    if rows:
        last = rows[-1]
        final_rx = {
            "right": {"sph": last.r_sph, "cyl": last.r_cyl,
                       "axis": last.r_axis, "add": last.r_add},
            "left": {"sph": last.l_sph, "cyl": last.l_cyl,
                      "axis": last.l_axis, "add": last.l_add},
        }

    metadata = {
        "session_id": session_id,
        "phoropter_id": phoropter_id,
        "operator_name": operator_name,
        "customer_name": customer_name or "",
        "customer_age": customer_age or "",
        "customer_gender": customer_gender or "",
        "session_start_time": session_start_time.isoformat(),
        "session_end_time": session_end_time.isoformat(),
        "session_duration_seconds": round(duration, 1),
        "test_completion_status": completion_status,
        "total_interactions": len(rows),
        "ar": ar or {},
        "lensometry": lensometry or {},
        "final_prescription": final_rx,
        "qualitative_feedback": qualitative_feedback or "",
        "phases_completed": phases_completed or [],
        "phases_skipped": phases_skipped or [],
        "quality_metrics": {
            "manual_adjustment_count": manual_count,
            "qna_interaction_count": qna_count,
            "phase_jump_count": phase_jump_count,
            "jcc_cycles_right": jcc_cycles_right,
            "jcc_cycles_left": jcc_cycles_left,
            "unable_to_read_count": unable_to_read_count,
            "duration_per_phase": duration_per_phase or {},
        },
    }

    return metadata


# Keep legacy function for backward compatibility
def write_annotated_csv(rows: List[RowContext], output_path: Path):
    """Legacy writer -- delegates to write_session_csv."""
    write_session_csv(rows, output_path)


def generate_summary(rows: List[RowContext]) -> dict:
    """Generate summary statistics for a test session."""
    if not rows:
        return {}

    phase_counts = {}
    for row in rows:
        if row.phase_id:
            phase_counts[row.phase_id] = phase_counts.get(row.phase_id, 0) + 1

    final_rx = {}
    if rows:
        last_row = rows[-1]
        final_rx = {
            "right_eye": {
                "sph": last_row.r_sph, "cyl": last_row.r_cyl,
                "axis": last_row.r_axis, "add": last_row.r_add,
            },
            "left_eye": {
                "sph": last_row.l_sph, "cyl": last_row.l_cyl,
                "axis": last_row.l_axis, "add": last_row.l_add,
            },
        }

    start_time = rows[0].timestamp if rows else ""
    end_time = rows[-1].timestamp if rows else ""

    return {
        "total_rows": len(rows),
        "phase_counts": phase_counts,
        "final_prescription": final_rx,
        "start_time": start_time,
        "end_time": end_time,
    }
