"""Strava API v3 tool functions."""
import time
from datetime import datetime, timedelta, timezone

import httpx

from fitness_agent.auth.strava_auth import get_token

BASE_URL = "https://www.strava.com/api/v3"


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_token()}"}


def get_strava_activities(days: int = 7) -> list[dict]:
    """Fetch recent Strava activities from the last N days."""
    try:
        days = int(days)
        after_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
        activities = []
        page = 1

        while True:
            resp = httpx.get(
                f"{BASE_URL}/athlete/activities",
                headers=_headers(),
                params={"after": after_ts, "per_page": 50, "page": page},
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < 50:
                break
            page += 1

        result = []
        for a in activities:
            dist_m = a.get("distance", 0)
            elapsed_s = a.get("elapsed_time", 0)
            result.append({
                "id": str(a.get("id", "")),
                "name": a.get("name", ""),
                "type": a.get("type", ""),
                "sport_type": a.get("sport_type", ""),
                "date": (a.get("start_date_local", "") or "")[:10],
                "distance_km": round(dist_m / 1000, 2) if dist_m else 0,
                "duration_min": round(elapsed_s / 60, 1) if elapsed_s else 0,
                "avg_hr": a.get("average_heartrate"),
                "max_hr": a.get("max_heartrate"),
                "avg_speed_kph": round((a.get("average_speed", 0) or 0) * 3.6, 1),
                "elevation_gain_m": a.get("total_elevation_gain"),
                "avg_watts": a.get("average_watts"),
                "suffer_score": a.get("suffer_score"),
            })
        return result

    except httpx.HTTPStatusError as e:
        return [{"error": "api_error", "message": str(e)}]
    except Exception as e:
        return [{"error": "not_connected", "message": f"Strava not connected or error: {e}"}]
