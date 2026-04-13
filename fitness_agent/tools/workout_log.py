"""Post-workout journal tool functions."""
from datetime import date

from fitness_agent.storage.db import save_workout_log as _save, get_workout_logs


def log_workout(user_recap: str, exercises: list = None,
                perceived_effort: int = None, recovery_score: int = None,
                pre_workout_notes: str = None, post_notes: str = None,
                claude_feedback: str = None, plan_adjustments: list = None) -> dict:
    """Store a post-workout recap with exercises, effort, and optional Claude feedback."""
    today = date.today().isoformat()
    perceived_effort = int(perceived_effort) if perceived_effort is not None else None
    recovery_score = int(recovery_score) if recovery_score is not None else None

    log_id = _save(
        date_str=today,
        recovery_score=recovery_score,
        pre_workout_notes=pre_workout_notes or "",
        user_recap=user_recap,
        exercises=exercises or [],
        perceived_effort=perceived_effort,
        post_notes=post_notes or "",
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
            "recovery_score": l["recovery_score"],
            "pre_notes": l["pre_workout_notes"],
            "recap": l["user_recap"],
            "exercises": l["exercises"],
            "effort": l["perceived_effort"],
            "post_notes": l["post_notes"],
            "feedback": l["claude_feedback"],
        }
        for l in logs
    ]
