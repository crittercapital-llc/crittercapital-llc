"""
Goggins Fitness Agent — FastAPI app (v2, no external API integrations).
Run with: uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""
import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fitness_agent.storage.db import init_db
from fitness_agent.tools.profile import get_fitness_profile, save_fitness_profile
from fitness_agent.tools.training_plan import (
    get_training_plan, get_todays_workout, store_generated_plan, update_plan_days
)
from fitness_agent.tools.workout_log import log_workout, get_workout_log
from fitness_agent.recommendation import get_daily_recommendation
from fitness_agent.agent import run_agent, stream_agent

init_db()

app = FastAPI(title="Goggins Fitness Agent")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    return (static_dir / "index.html").read_text()


# ── Profile ────────────────────────────────────────────────────────────────────

class ProfileIn(BaseModel):
    goals: str
    current_fitness: str = ""
    timeline_weeks: int = 12
    restrictions: str = ""
    preferred_sports: list[str] = []
    days_per_week: int = 5


@app.get("/profile")
async def get_profile_route():
    return get_fitness_profile()


@app.post("/profile")
async def save_profile_route(body: ProfileIn):
    return save_fitness_profile(
        goals=body.goals,
        current_fitness=body.current_fitness,
        timeline_weeks=body.timeline_weeks,
        restrictions=body.restrictions,
        preferred_sports=body.preferred_sports,
        days_per_week=body.days_per_week,
    )


# ── Training plan ──────────────────────────────────────────────────────────────

@app.get("/plan")
async def get_plan():
    return get_training_plan()


@app.get("/plan/today")
async def plan_today():
    return get_todays_workout()


class PlanAdjustIn(BaseModel):
    adjustments: list[dict]


@app.post("/plan/adjust")
async def adjust_plan(body: PlanAdjustIn):
    return update_plan_days(body.adjustments)


@app.post("/plan/generate")
async def generate_plan():
    """Ask Goggins to build the training plan from the stored profile."""
    profile = get_fitness_profile()
    if "error" in profile:
        raise HTTPException(status_code=400, detail="Set your fitness profile first.")

    prompt = f"""Generate a complete {profile.get('timeline_weeks', 12)}-week training plan for this athlete.

Goal: {profile.get('goals')}
Current fitness: {profile.get('current_fitness') or 'Not specified'}
Available days/week: {profile.get('days_per_week')}
Preferred sports: {', '.join(profile.get('preferred_sports', []) or ['Not specified'])}
Restrictions: {profile.get('restrictions') or 'None'}

Output the plan as a JSON array inside <plan>...</plan> tags, then follow with your coaching message.
Each day object: week_number, day_of_week (1=Mon), workout_type, description, target_distance_km, target_duration_min, intensity, notes.
Include rest days (workout_type: "rest", intensity: "rest"). Cover all 7 days each week.
"""
    messages = [{"role": "user", "content": prompt}]
    full_response = run_agent(messages)

    # Extract and store the plan JSON
    plan_match = re.search(r"<plan>(.*?)</plan>", full_response, re.DOTALL)
    store_result = None
    if plan_match:
        try:
            plan_data = json.loads(plan_match.group(1).strip())
            store_result = store_generated_plan(plan_data)
        except json.JSONDecodeError:
            store_result = {"error": "Could not parse plan JSON"}

    coaching_message = re.sub(r"<plan>.*?</plan>", "", full_response, flags=re.DOTALL).strip()
    return {"message": coaching_message, "plan_stored": store_result}


# ── Today dashboard ────────────────────────────────────────────────────────────

@app.get("/today")
async def today_dashboard():
    """Return today's scheduled workout from the plan (no live data)."""
    scheduled = get_todays_workout()
    return {
        "date": date.today().isoformat(),
        "scheduled_workout": scheduled,
    }


# ── Pre-workout check-in ───────────────────────────────────────────────────────

class CheckInIn(BaseModel):
    recovery_score: int
    notes: str = ""


@app.post("/checkin")
async def checkin(body: CheckInIn):
    """
    Accept a manual recovery score + pain notes.
    Goggins reads today's plan and adapts the workout. Streams the response.
    """
    # Get quick intensity label server-side as context for the agent
    rec = get_daily_recommendation(body.recovery_score, [])
    scheduled = get_todays_workout()

    scheduled_desc = "No workout scheduled in the plan for today."
    if "description" in scheduled:
        scheduled_desc = (
            f"{scheduled['description']} "
            f"({scheduled.get('intensity', '').upper()}, "
            f"{scheduled.get('target_distance_km') or ''}km / "
            f"{scheduled.get('target_duration_min') or ''}min)"
        ).strip(" (km / min)")

    prompt = (
        f"Athlete pre-workout check-in.\n"
        f"Whoop recovery score: {body.recovery_score}/100\n"
        f"Pain / notes: {body.notes or 'None'}\n"
        f"Today's scheduled workout: {scheduled_desc}\n"
        f"Baseline intensity recommendation: {rec['intensity'].upper()} — {rec['rationale']}\n\n"
        f"Based on this, tell the athlete exactly what to do today. "
        f"Be specific: adapt the workout if needed, give sets/reps/pacing if relevant. "
        f"If recovery is very low and the plan says hard, cut it back without apology."
    )

    messages = [{"role": "user", "content": prompt}]

    async def event_stream():
        try:
            async for chunk in stream_agent(messages):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Chat (open-ended) ──────────────────────────────────────────────────────────

class ChatIn(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/chat")
async def chat(body: ChatIn):
    messages = list(body.history)
    messages.append({"role": "user", "content": body.message})

    async def event_stream():
        try:
            async for chunk in stream_agent(messages):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Post-workout log ───────────────────────────────────────────────────────────

class ExerciseIn(BaseModel):
    name: str
    sets: int | None = None
    reps: int | None = None
    weight_lbs: float | None = None
    notes: str = ""


class LogIn(BaseModel):
    user_recap: str
    exercises: list[ExerciseIn] = []
    perceived_effort: int | None = None
    recovery_score: int | None = None
    pre_workout_notes: str = ""
    post_notes: str = ""


@app.post("/log")
async def post_log(body: LogIn):
    """
    Submit a post-workout log. Goggins gives feedback and may adjust the plan.
    Returns streaming SSE.
    """
    exercises_dicts = [e.model_dump(exclude_none=True) for e in body.exercises]

    # Build exercises summary for the prompt
    ex_lines = []
    for e in exercises_dicts:
        line = e["name"]
        if e.get("sets") and e.get("reps"):
            line += f" {e['sets']}x{e['reps']}"
        if e.get("weight_lbs"):
            line += f" @ {e['weight_lbs']}lbs"
        if e.get("notes"):
            line += f" ({e['notes']})"
        ex_lines.append(line)

    prompt = (
        f"Athlete post-workout log.\n"
        f"Date: {date.today().isoformat()}\n"
        f"Recovery going in: {body.recovery_score or 'Not recorded'}\n"
        f"Pre-workout notes: {body.pre_workout_notes or 'None'}\n"
        f"What they did: {body.user_recap}\n"
    )
    if ex_lines:
        prompt += f"Exercises:\n" + "\n".join(f"  - {l}" for l in ex_lines) + "\n"
    prompt += (
        f"Perceived effort: {body.perceived_effort or 'Not recorded'}/10\n"
        f"How they felt after: {body.post_notes or 'Not recorded'}\n\n"
        f"Give brief, direct feedback. Call out what was good, what needs attention. "
        f"If effort was very high or they noted pain, consider adjusting the next few days — "
        f"use update_plan_days if needed. Then log this entry with log_workout."
    )

    messages = [{"role": "user", "content": prompt}]

    # Run agent synchronously to get feedback + trigger tool calls (log + plan adjust)
    feedback = run_agent(messages)

    # Store the log with the feedback
    log_workout(
        user_recap=body.user_recap,
        exercises=exercises_dicts,
        perceived_effort=body.perceived_effort,
        recovery_score=body.recovery_score,
        pre_workout_notes=body.pre_workout_notes,
        post_notes=body.post_notes,
        claude_feedback=feedback,
    )

    return {"feedback": feedback}


@app.get("/log")
async def get_log(days: int = Query(default=7)):
    return get_workout_log(days=days)
