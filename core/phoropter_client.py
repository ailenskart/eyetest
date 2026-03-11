"""
Phoropter Client: HTTP interface for controlling the phoropter device.

Extracted from InteractiveSession to allow reuse by the FSM-based workflow.
All phoropter commands go through POST {base_url}/phoropter/{device_id}/run-tests.
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger(__name__)


class PhoropterClient:
    """Sends lens power and chart commands to a remote phoropter device."""

    def __init__(self, base_url: str, phoropter_id: str):
        self.base_url = base_url.rstrip("/")
        self.phoropter_id = phoropter_id
        self.api_endpoint = f"{self.base_url}/phoropter/{self.phoropter_id}/run-tests"

        # Track last-sent power for delta (prev_state) calculations
        self._prev_re = {"sph": 0.0, "cyl": 0.0, "axis": 180.0, "add": 0.0}
        self._prev_le = {"sph": 0.0, "cyl": 0.0, "axis": 180.0, "add": 0.0}

    # -----------------------------------------------------------------
    # Low-level HTTP
    # -----------------------------------------------------------------

    def _post(self, url: str, payload: dict) -> Optional[dict]:
        """Send a JSON POST to the phoropter broker."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        logger.info(f"POST {url} payload={json.dumps(payload)}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                logger.info(f"Response {resp.getcode()}: {body[:200]}")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"HTTP Error {e.code}: {body[:200]}")
            return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

    # -----------------------------------------------------------------
    # Power commands
    # -----------------------------------------------------------------

    def set_power(
        self,
        re_sph: float, re_cyl: float, re_axis: float,
        le_sph: float, le_cyl: float, le_axis: float,
        re_add: float = 0.0, le_add: float = 0.0,
        occluder: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Set absolute lens power on the phoropter with prev-state deltas.

        Uses the previously-sent values as prev_state so the broker
        computes the correct click count.

        Args:
            re_sph, re_cyl, re_axis: Right eye power
            le_sph, le_cyl, le_axis: Left eye power
            re_add, le_add: Near ADD power
            occluder: 'Left_Occluded', 'Right_Occluded', 'BINO', or None
        """
        right_eye = {"sph": re_sph, "cyl": re_cyl, "axis": re_axis}
        left_eye = {"sph": le_sph, "cyl": le_cyl, "axis": le_axis}
        if re_add:
            right_eye["add"] = re_add
        if le_add:
            left_eye["add"] = le_add

        payload = {
            "test_cases": [{
                "prev_right_eye": dict(self._prev_re),
                "prev_left_eye": dict(self._prev_le),
                "right_eye": right_eye,
                "left_eye": left_eye,
            }]
        }

        result = self._post(self.api_endpoint, payload)

        # Update prev state on success
        if result is not None:
            self._prev_re = dict(right_eye)
            self._prev_le = dict(left_eye)

        # Set JCC eye mode for occluder
        if occluder:
            jcc_mode = {
                "Left_Occluded": "R",
                "Right_Occluded": "L",
                "BINO": "BINO",
            }.get(occluder)
            if jcc_mode:
                self.jcc_control(jcc_mode)

        return result

    def set_chart(self, chart_name: str, size: Optional[str] = None, tab: str = "Chart1") -> Optional[dict]:
        """Display a chart on the phoropter."""
        # Standard chart ID mapping
        chart_map = {
            "snellen": "chart_1", "landolt_c": "chart_2",
            "red_green": "chart_3", "cross_cylinder": "chart_4",
            "near_chart": "chart_5",
        }
        chart_id = chart_map.get(chart_name, chart_name)
        chart_items = [chart_id] if size is None else [chart_id, size]
        payload = {
            "test_cases": [{
                "chart": {"tab": tab, "chart_items": chart_items}
            }]
        }
        return self._post(self.api_endpoint, payload)

    def jcc_control(self, action: str) -> Optional[dict]:
        """Perform JCC action (R, L, BINO, handle, increase, decrease)."""
        payload = {"test_cases": [{"jcc": action}]}
        return self._post(self.api_endpoint, payload)

    def reset(self) -> Optional[dict]:
        """Reset phoropter to neutral state (0/0/180)."""
        url = f"{self.base_url}/phoropter/{self.phoropter_id}/reset"
        result = self._post(url, {})
        self._prev_re = {"sph": 0.0, "cyl": 0.0, "axis": 180.0, "add": 0.0}
        self._prev_le = {"sph": 0.0, "cyl": 0.0, "axis": 180.0, "add": 0.0}
        return result

    def sync_state(self, re: dict, le: dict) -> Optional[dict]:
        """
        Sync broker internal state without physical clicks.
        Use when the FSM knows the current phoropter state but
        the prev-state tracker is out of date.
        """
        url = f"{self.base_url}/phoropter/{self.phoropter_id}/sync-state"
        payload = {"right_eye": re, "left_eye": le}
        result = self._post(url, payload)
        if result is not None:
            self._prev_re = dict(re)
            self._prev_le = dict(le)
        return result

    def init_prev_state(
        self,
        re_sph: float, re_cyl: float, re_axis: float,
        le_sph: float, le_cyl: float, le_axis: float,
    ):
        """Set prev-state tracker without sending to phoropter."""
        self._prev_re = {"sph": re_sph, "cyl": re_cyl, "axis": re_axis, "add": 0.0}
        self._prev_le = {"sph": le_sph, "cyl": le_cyl, "axis": le_axis, "add": 0.0}
