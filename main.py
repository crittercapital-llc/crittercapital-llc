"""
Goggins Fitness Agent — FastAPI app.
Run with: uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""
import json
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from fitness_agent.storage.db import init_db, is_authenticated, get_profile
from fitness_agent.auth import whoop_auth, strava_auth
from fitness_agent.tools.whoop import get_whoop_recovery, get_whoop_sleep, get_whoop_strain
from fitness_agent.tools.strava import get_strava_activities
from fitness_agent.tools.profile import get_fitness_profile, save_fitness_profile
from fitness_agent.tools.training_plan import (
    get_training_plan, get_todays_workout, store_generated_plan, update_plan_days
)
from fitness_agent.tools.workout_log import log_workout, get_workout_log
from fitness_agent.recommendation import get_daily_recommendation
from fitness_agent.agent import run_agent, stream_agent

# Initialise DB on startup
init_db()

app = FastAPI(title="Goggins Fitness Agent")

# ── Static files ───────────────────────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _base_url(request: Request) -> str:
    """Return the base URL of this request (scheme + host)."""
    return str(request.base_url).rstrip("/")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return (static_dir / "index.html").read_text()


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.get("/auth/whoop/start")
async def whoop_start(request: Request):
    redirect_uri = f"{_base_url(request)}/auth/whoop/callback"
    url = whoop_auth.get_auth_url(redirect_uri)
    return RedirectResponse(url)


@app.get("/auth/whoop/callback")
async def whoop_callback(request: Request, code: str = Query(...), state: str = Query(...)):
    redirect_uri = f"{_base_url(request)}/auth/whoop/callback"
    try:
        whoop_auth.handle_callback(code, state, redirect_uri)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/?connected=whoop")


@app.get("/auth/strava/start")
async def strava_start(request: Request):
    redirect_uri = f"{_base_url(request)}/auth/strava/callback"
    url = strava_auth.get_auth_url(redirect_uri)
    return RedirectResponse(url)


@app.get("/auth/strava/callback")
async def strava_callback(request: Request, code: str = Query(...), state: str = Query(...)):
    redirect_uri = f"{_base_url(request)}/auth/strava/callback"
    try:
        strava_auth.handle_callback(code, state, redirect_uri)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/?connected=strava")


@app.get("/auth/status")
async def auth_status():
    return {
        "whoop": is_authenticated("whoop"),
        "strava": is_authenticated("strava"),
    }


# ── Profile routes ─────────────────────────────────────────────────────────────

class ProfileIn(BaseModel):
    goals: str
    timeline_weeks: int = 12
    restrictions: str = ""
    preferred_sports: list[str] = []
    days_per_week: int = 5
    fitness_level: str = "intermediate"


@app.get("/profile")
async def get_profile_route():
    return get_fitness_profile()


@app.post("/profile")
async def save_profile_route(body: ProfileIn):
    result = save_fitness_profile(
        goals=body.goals,
        timeline_weeks=body.timeline_weeks,
        restrictions=body.restrictions,
        preferred_sports=body.preferred_sports,
        days_per_week=body.days_per_week,
        fitness_level=body.fitness_level,
    )
    return result


# ── Training plan routes ───────────────────────────────────────────────────────

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


# ── Today dashboard route ──────────────────────────────────────────────────────

@app.get("/today")
async def today_dashboard():
    """
    Returns recovery data + today's adapted workout recommendation.
    Goggins runs a quick one-shot agent call to adapt based on recovery.
    """
    recovery = get_whoop_recovery()
    sleep = get_whoop_sleep()
    strain = get_whoop_strain()
    scheduled = get_todays_workout()

    # Build quick recommendation without full agent chat
    intensity = None
    rationale = None
    if "score" in recovery and recovery["score"] is not None:
        strain_score = strain.get("strain_score") if "strain_score" in strain else None
        recent = [strain_score] if strain_score else []
        rec = get_daily_recommendation(recovery["score"], recent)
        intensity = rec["intensity"]
        rationale = rec["rationale"]

    return {
        "date": date.today().isoformat(),
        "recovery": recovery,
        "sleep": sleep,
        "strain": strain,
        "scheduled_workout": scheduled,
        "recommended_intensity": intensity,
        "intensity_rationale": rationale,
    }


# ── Chat route (SSE streaming) ─────────────────────────────────────────────────

class ChatIn(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/chat")
async def chat(body: ChatIn):
    """
    Accept a user message + conversation history, stream Goggins's response.
    Frontend should use EventSource or fetch with ReadableStream.
    """
    messages = list(body.history)
    messages.append({"role": "user", "content": body.message})

    async def event_stream():
        try:
            async for chunk in stream_agent(messages):
                # SSE format
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Workout log routes ─────────────────────────────────────────────────────────

class LogIn(BaseModel):
    user_recap: str
    perceived_effort: int | None = None
    pain_notes: str = ""
    strava_activity_id: str = ""


@app.post("/log")
async def post_log(body: LogIn):
    """
    Submit a post-workout recap. Goggins provides feedback via agent call.
    """
    # Get Strava data to enrich the recap context
    strava = get_strava_activities(days=1)
    strava_id = None
    if strava and "error" not in strava[0]:
        strava_id = strava[0].get("id") or body.strava_activity_id

    # Ask Goggins for feedback
    prompt = f"""The athlete just completed a workout and wants to log it.

Athlete recap: "{body.user_recap}"
Perceived effort: {body.perceived_effort}/10
Pain/issues: {body.pain_notes or 'None'}
"""
    if strava and "error" not in strava[0]:
        a = strava[0]
        prompt += f"""
Most recent Strava activity: {a.get('name')} — {a.get('type')}, {a.get('distance_km')}km, {a.get('duration_min')}min, avg HR {a.get('avg_hr')} bpm
"""

    messages = [{"role": "user", "content": prompt}]
    feedback = run_agent(messages)

    # Save to log
    result = log_workout(
        user_recap=body.user_recap,
        perceived_effort=body.perceived_effort,
        pain_notes=body.pain_notes,
        strava_activity_id=strava_id,
        claude_feedback=feedback,
    )
    result["feedback"] = feedback

    # Check if plan needs adjusting based on feedback
    if body.perceived_effort and body.perceived_effort >= 9:
        # High effort day — suggest tomorrow be easy
        tomorrow_msg = [{"role": "user", "content":
            f"Athlete reported effort {body.perceived_effort}/10 today. "
            "Should we adjust tomorrow's plan? If yes, call update_plan_days."}]
        run_agent(tomorrow_msg)

    return result


@app.get("/log")
async def get_log(days: int = Query(default=7)):
    return get_workout_log(days=days)


# ── Plan generation route ──────────────────────────────────────────────────────

@app.post("/plan/generate")
async def generate_plan():
    """
    Ask Goggins to generate a full training plan based on the stored profile.
    Streams the response.
    """
    profile = get_fitness_profile()
    if "error" in profile:
        raise HTTPException(status_code=400, detail="Set your fitness profile first.")

    prompt = f"""Generate a complete {profile.get('timeline_weeks', 12)}-week training plan for this athlete.

Goal: {profile.get('goals')}
Fitness level: {profile.get('fitness_level')}
Available days/week: {profile.get('days_per_week')}
Preferred sports: {', '.join(profile.get('preferred_sports', []))}
Restrictions: {profile.get('restrictions') or 'None'}

Output the plan as a JSON array inside <plan>...</plan> tags, then follow it with your coaching message.
Each day: week_number, day_of_week (1=Mon), workout_type, description, target_distance_km, target_duration_min, intensity, notes.
Rest days must be included (workout_type: "rest", intensity: "rest").
"""

    messages = [{"role": "user", "content": prompt}]
    full_response = run_agent(messages)

    # Parse and store the plan JSON from the response
    plan_match = re.search(r"<plan>(.*?)</plan>", full_response, re.DOTALL)
    store_result = None
    if plan_match:
        try:
            plan_data = json.loads(plan_match.group(1).strip())
            store_result = store_generated_plan(plan_data)
        except json.JSONDecodeError:
            store_result = {"error": "Could not parse plan JSON from response"}

    # Return the coaching message without the raw JSON
    coaching_message = re.sub(r"<plan>.*?</plan>", "", full_response, flags=re.DOTALL).strip()

    return {
        "message": coaching_message,
        "plan_stored": store_result,
    }
