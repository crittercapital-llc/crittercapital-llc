"""Post-workout journal tool functions."""
from datetime import date

from fitness_agent.storage.db import save_workout_log as _save, get_workout_logs


def log_workout(user_recap: str, perceived_effort: int = None,
                pain_notes: str = None, strava_activity_id: str = None,
                claude_feedback: str = None, plan_adjustments: list = None) -> dict:
    """Store a post-workout recap and optional Claude feedback."""
    today = date.today().isoformat()
    perceived_effort = int(perceived_effort) if perceived_effort is not None else None
    log_id = _save(
        date_str=today,
        user_recap=user_recap,
        perceived_effort=perceived_effort,
        pain_notes=pain_notes or "",
        strava_activity_id=strava_activity_id,
        claude_feedback=claude_feedback or "",
        plan_adjustments=plan_adjustments,
    )
    return {"status": "logged", "id": log_id, "date": today}


def get_workout_log(days: int = 7) -> list[dict]:
    """Retrieve recent workout log entries."""
    days = int(days)
    logs = get_workout_logs(days)
    if not logs:
        return [{"message": f"No workout logs in the last {days} days."}]
    return [
        {
            "date": l["date"],
            "recap": l["user_recap"],
            "effort": l["perceived_effort"],
            "pain_notes": l["pain_notes"],
            "feedback": l["claude_feedback"],
        }
        for l in logs
    ]
