"""
Training intensity recommendation based on Whoop recovery score and recent strain.

This provides a data-driven guardrail. Goggins layers contextual judgment on top.
"""


def score_intensity(recovery_score: float, recent_strain_scores: list[float]) -> str:
    """
    Return a recommended training intensity label.

    Args:
        recovery_score: Whoop recovery score 0–100
        recent_strain_scores: Whoop strain scores from last 1–3 days (0–21 scale)

    Returns:
        'rest' | 'easy' | 'moderate' | 'hard' | 'peak'
    """
    recovery_score = float(recovery_score)
    recent_strain_scores = [float(s) for s in (recent_strain_scores or [])]
    avg_strain = sum(recent_strain_scores) / len(recent_strain_scores) if recent_strain_scores else 0.0

    if recovery_score < 33:
        return "rest"
    elif recovery_score < 50:
        return "easy" if avg_strain > 15 else "moderate"
    elif recovery_score < 67:
        return "moderate" if avg_strain > 18 else "hard"
    elif recovery_score < 84:
        return "hard" if avg_strain < 12 else "moderate"
    else:
        return "peak" if avg_strain < 10 else "hard"


def get_daily_recommendation(recovery_score: float,
                              recent_strain_scores: list[float]) -> dict:
    """
    Tool-facing wrapper that returns the intensity label plus a brief rationale.
    """
    recovery_score = float(recovery_score)
    recent_strain_scores = [float(s) for s in (recent_strain_scores or [])]
    intensity = score_intensity(recovery_score, recent_strain_scores)
    avg_strain = (sum(recent_strain_scores) / len(recent_strain_scores)
                  if recent_strain_scores else 0.0)

    rationale_map = {
        "rest": "Recovery is critically low. The body needs full rest to rebuild.",
        "easy": "Recovery is below baseline. Light movement only — protect the adaptation.",
        "moderate": "Moderate recovery. A solid aerobic session is appropriate.",
        "hard": "Recovery is good. Push into quality work today.",
        "peak": "Full green. Peak performance day — go all out.",
    }

    return {
        "intensity": intensity,
        "recovery_score": recovery_score,
        "avg_recent_strain": round(avg_strain, 1),
        "rationale": rationale_map[intensity],
    }
