"""
Dashboard configuration: read/write for tests_enabled, daily_limit, per_phoropter_enabled.
Used by api_server to enforce session start and by dashboard API/UI.
"""
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "tests_enabled": True,
    "daily_limit": None,
    "daily_limit_scope": "global",
    "per_phoropter_enabled": {},
}


def get_config_path(logs_dir: Path) -> Path:
    """Config file path under logs dir."""
    return logs_dir / "dashboard_config.json"


def read_config(config_path: Path) -> Dict[str, Any]:
    """Read dashboard config from JSON file. Returns default if missing or invalid."""
    out = dict(DEFAULT_CONFIG)
    if not config_path.exists():
        return out
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "tests_enabled" in data:
                out["tests_enabled"] = bool(data["tests_enabled"])
            if "daily_limit" in data:
                v = data["daily_limit"]
                out["daily_limit"] = int(v) if v is not None and str(v).strip() != "" else None
            if "daily_limit_scope" in data and data["daily_limit_scope"] in ("global", "per_phoropter"):
                out["daily_limit_scope"] = data["daily_limit_scope"]
            if "per_phoropter_enabled" in data and isinstance(data["per_phoropter_enabled"], dict):
                out["per_phoropter_enabled"] = {
                    str(k): bool(v) for k, v in data["per_phoropter_enabled"].items()
                }
    except (json.JSONDecodeError, IOError, TypeError):
        pass
    return out


def write_config(config_path: Path, config: Dict[str, Any]) -> None:
    """Write dashboard config to JSON file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tests_enabled": config.get("tests_enabled", DEFAULT_CONFIG["tests_enabled"]),
        "daily_limit": config.get("daily_limit", DEFAULT_CONFIG["daily_limit"]),
        "daily_limit_scope": config.get("daily_limit_scope", DEFAULT_CONFIG["daily_limit_scope"]),
        "per_phoropter_enabled": config.get("per_phoropter_enabled", DEFAULT_CONFIG["per_phoropter_enabled"]),
    }
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
