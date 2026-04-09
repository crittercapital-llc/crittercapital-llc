"""Whoop API v2 tool functions."""
import httpx
from fitness_agent.auth.whoop_auth import get_token

BASE_URL = "https://api.prod.whoop.com/developer/v2"


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}"}


def get_whoop_recovery() -> dict:
    """Fetch the latest Whoop recovery score, HRV, and resting heart rate."""
    try:
        resp = httpx.get(f"{BASE_URL}/recovery", headers=_headers(),
                         params={"limit": 1}, timeout=10)
        if resp.status_code == 404:
            return {"error": "no_data", "message": "No recovery data available yet today."}
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        if not records:
            return {"error": "no_data", "message": "No recovery records found."}
        r = records[0]
        score = r.get("score", {})
        return {
            "score": score.get("recovery_score"),
            "hrv_rmssd": score.get("hrv_rmssd_milli"),
            "resting_hr": score.get("resting_heart_rate"),
            "spo2_pct": score.get("spo2_percentage"),
            "skin_temp_c": score.get("skin_temp_celsius"),
            "date": r.get("created_at", "")[:10],
        }
    except httpx.HTTPStatusError as e:
        return {"error": "api_error", "message": str(e)}
    except Exception as e:
        return {"error": "not_connected", "message": f"Whoop not connected or error: {e}"}


def get_whoop_sleep() -> dict:
    """Fetch the latest Whoop sleep data."""
    try:
        resp = httpx.get(f"{BASE_URL}/activity/sleep", headers=_headers(),
                         params={"limit": 1}, timeout=10)
        if resp.status_code == 404:
            return {"error": "no_data", "message": "No sleep data available."}
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        if not records:
            return {"error": "no_data", "message": "No sleep records found."}
        s = records[0]
        score = s.get("score", {})
        stage_summary = score.get("stage_summary", {})
        total_ms = stage_summary.get("total_in_bed_time_milli", 0)
        return {
            "quality_score": score.get("sleep_performance_percentage"),
            "efficiency_pct": score.get("sleep_efficiency_percentage"),
            "hours": round(total_ms / 3_600_000, 1) if total_ms else None,
            "rem_pct": score.get("sleep_cycle_count"),
            "disturbance_count": score.get("disturbance_count"),
            "date": s.get("created_at", "")[:10],
        }
    except httpx.HTTPStatusError as e:
        return {"error": "api_error", "message": str(e)}
    except Exception as e:
        return {"error": "not_connected", "message": f"Whoop not connected or error: {e}"}


def get_whoop_strain() -> dict:
    """Fetch the latest Whoop day strain score."""
    try:
        resp = httpx.get(f"{BASE_URL}/cycle", headers=_headers(),
                         params={"limit": 1}, timeout=10)
        if resp.status_code == 404:
            return {"error": "no_data", "message": "No cycle/strain data available."}
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        if not records:
            return {"error": "no_data", "message": "No strain records found."}
        c = records[0]
        score = c.get("score", {})
        return {
            "strain_score": score.get("strain"),
            "avg_hr": score.get("average_heart_rate"),
            "max_hr": score.get("max_heart_rate"),
            "kilojoules": score.get("kilojoule"),
            "date": c.get("created_at", "")[:10],
        }
    except httpx.HTTPStatusError as e:
        return {"error": "api_error", "message": str(e)}
    except Exception as e:
        return {"error": "not_connected", "message": f"Whoop not connected or error: {e}"}
