"""Training plan tool functions."""
import json
from datetime import date, timedelta

from fitness_agent.storage.db import (
    get_plan, get_todays_plan_entry, insert_plan_days,
    clear_plan, update_plan_entries, mark_plan_entry_complete
)


def get_training_plan(week_number: int = None) -> dict:
    """Retrieve the full training plan or a specific week."""
    if week_number is not None:
        week_number = int(week_number)
    days = get_plan(week_number)
    if not days:
        return {
            "error": "no_plan",
            "message": "No training plan exists yet. Generate one by telling Goggins your goals.",
        }
    # Group by week for readability
    weeks = {}
    for d in days:
        w = d["week_number"]
        if w not in weeks:
            weeks[w] = []
        weeks[w].append({
            "day": d["day_of_week"],
            "date": d["date"],
            "type": d["workout_type"],
            "description": d["description"],
            "distance_km": d["target_distance_km"],
            "duration_min": d["target_duration_min"],
            "intensity": d["intensity"],
            "completed": bool(d["completed"]),
        })
    return {"weeks": weeks, "total_weeks": max(weeks.keys()) if weeks else 0}


def get_todays_workout() -> dict:
    """Get today's scheduled workout from the training plan."""
    entry = get_todays_plan_entry()
    if not entry:
        return {
            "error": "no_entry",
            "message": f"No workout scheduled for today ({date.today().isoformat()}) in the plan.",
        }
    return {
        "date": entry["date"],
        "week": entry["week_number"],
        "day": entry["day_of_week"],
        "type": entry["workout_type"],
        "description": entry["description"],
        "distance_km": entry["target_distance_km"],
        "duration_min": entry["target_duration_min"],
        "intensity": entry["intensity"],
        "completed": bool(entry["completed"]),
    }


def store_generated_plan(plan_json: list) -> dict:
    """
    Store a Claude-generated training plan.
    Each item in plan_json must have:
      week_number, day_of_week (1-7), workout_type, description,
      target_distance_km, target_duration_min, intensity
    Dates are auto-assigned starting from next Monday.
    """
    if not plan_json:
        return {"error": "empty_plan", "message": "No plan data provided."}

    # Assign real calendar dates starting from next Monday
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    start_monday = today + timedelta(days=days_until_monday)

    enriched = []
    for entry in plan_json:
        week = int(entry.get("week_number", 1))
        dow = int(entry.get("day_of_week", 1))  # 1=Mon
        day_offset = (week - 1) * 7 + (dow - 1)
        cal_date = (start_monday + timedelta(days=day_offset)).isoformat()

        enriched.append({
            "week_number": week,
            "day_of_week": dow,
            "date": cal_date,
            "workout_type": entry.get("workout_type", "rest"),
            "description": entry.get("description", ""),
            "target_distance_km": entry.get("target_distance_km"),
            "target_duration_min": entry.get("target_duration_min"),
            "intensity": entry.get("intensity", "moderate"),
            "notes": entry.get("notes", ""),
        })

    clear_plan()
    insert_plan_days(enriched)
    return {
        "status": "saved",
        "total_days": len(enriched),
        "start_date": enriched[0]["date"] if enriched else None,
        "end_date": enriched[-1]["date"] if enriched else None,
    }


def update_plan_days(adjustments: list) -> dict:
    """
    Modify specific future plan days.
    Each adjustment: { date: str, description: str, intensity: str, ... }
    """
    if not adjustments:
        return {"status": "no_changes"}
    update_plan_entries(adjustments)
    return {"status": "updated", "days_modified": len(adjustments)}


def complete_todays_workout() -> dict:
    """Mark today's workout as completed."""
    today = date.today().isoformat()
    mark_plan_entry_complete(today)
    return {"status": "completed", "date": today}
