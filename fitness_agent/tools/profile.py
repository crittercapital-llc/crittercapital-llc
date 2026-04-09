"""Fitness profile tool functions."""
from fitness_agent.storage.db import get_profile, save_profile as _save_profile


def get_fitness_profile() -> dict:
    """Read the user's stored fitness goals and preferences."""
    profile = get_profile()
    if not profile:
        return {
            "error": "no_profile",
            "message": "No fitness profile set yet. Ask the user to fill in their goals in Settings.",
        }
    return {
        "goals": profile.get("goals"),
        "timeline_weeks": profile.get("timeline_weeks"),
        "restrictions": profile.get("restrictions"),
        "preferred_sports": profile.get("preferred_sports", []),
        "days_per_week": profile.get("days_per_week"),
        "fitness_level": profile.get("fitness_level"),
    }


def save_fitness_profile(goals: str, timeline_weeks: int = 12,
                         restrictions: str = "", preferred_sports: list = None,
                         days_per_week: int = 5, fitness_level: str = "intermediate") -> dict:
    """Store the user's fitness goals and preferences."""
    _save_profile(
        goals=goals,
        timeline_weeks=int(timeline_weeks),
        restrictions=restrictions or "",
        preferred_sports=preferred_sports or [],
        days_per_week=int(days_per_week),
        fitness_level=fitness_level or "intermediate",
    )
    return {"status": "saved", "message": "Profile updated successfully."}
