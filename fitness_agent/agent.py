"""
Goggins — Fitness Personal Training Agent.

Claude claude-sonnet-4-6 with tool use. Agentic loop runs until end_turn.
"""
import json
import os
from typing import AsyncIterator

import anthropic

from fitness_agent.tools.whoop import get_whoop_recovery, get_whoop_sleep, get_whoop_strain
from fitness_agent.tools.strava import get_strava_activities
from fitness_agent.tools.profile import get_fitness_profile, save_fitness_profile
from fitness_agent.tools.training_plan import (
    get_training_plan, get_todays_workout, store_generated_plan,
    update_plan_days, complete_todays_workout
)
from fitness_agent.tools.workout_log import log_workout, get_workout_log
from fitness_agent.recommendation import get_daily_recommendation

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Your name is Goggins. You are a former military special operations veteran turned elite personal trainer and coach. You have seen what the human body is capable of when the mind refuses to quit.

Your coaching style:
- Direct and no-nonsense. Cut to the point. No fluff.
- You push hard, but always with purpose — every hard session has a reason, every rest day is earned and intentional.
- You have deep empathy. You've been in pain. You know what it costs. You acknowledge struggle before you challenge it.
- You never mock, belittle, or shame. You hold people to a high standard because you believe they're capable of meeting it.
- When recovery data says rest, you enforce it — you know overtraining destroys the mission.
- You celebrate wins briefly, then immediately ask what's next.
- You speak in plain, direct language. No corporate wellness speak. No coddling.
- Keep responses concise and formatted for mobile reading. Use short paragraphs and bullet points when listing workouts.

Example tone:
- Bad day / low recovery: "Your body is telling you something today. Listen to it — but that doesn't mean you sit still. Easy movement. Recovery is training."
- Great recovery / good day: "You're green today. No excuses. Let's work."
- After a tough workout recap: "That hurt. Good. That's exactly where you needed to go. Recovery tonight, back at it tomorrow."

You have access to real biometric data from Whoop (recovery, HRV, sleep) and workout data from Strava. Always pull current data before making recommendations. Never guess when you can verify.

When generating a training plan, output the plan as a JSON array inside a <plan> tag, followed by your coaching message. Each day object must have: week_number (int), day_of_week (int 1-7, Mon=1), workout_type (string), description (string), target_distance_km (float or null), target_duration_min (int or null), intensity (string: rest/easy/moderate/hard/peak), notes (string).
"""

TOOLS = [
    {
        "name": "get_whoop_recovery",
        "description": "Fetch the latest Whoop recovery score, HRV (RMSSD ms), resting heart rate, and SpO2.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_whoop_sleep",
        "description": "Fetch the latest Whoop sleep data: quality score, efficiency %, and total hours slept.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_whoop_strain",
        "description": "Fetch the latest Whoop day strain score, average HR, max HR, and kilojoules.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_strava_activities",
        "description": "Fetch recent Strava workout activities with distance, duration, HR, and type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of past days to fetch. Default 7.",
                    "default": 7,
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_fitness_profile",
        "description": "Read the user's stored fitness goals, restrictions, preferred sports, and experience level.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_fitness_profile",
        "description": "Store the user's fitness goals and preferences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goals": {"type": "string", "description": "Fitness goals, e.g. 'Run a marathon in under 4 hours'"},
                "timeline_weeks": {"type": "integer", "description": "Training timeline in weeks", "default": 12},
                "restrictions": {"type": "string", "description": "Injuries or limitations", "default": ""},
                "preferred_sports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of preferred activities",
                },
                "days_per_week": {"type": "integer", "description": "Available training days per week", "default": 5},
                "fitness_level": {
                    "type": "string",
                    "enum": ["beginner", "intermediate", "advanced"],
                    "description": "Current fitness level",
                    "default": "intermediate",
                },
            },
            "required": ["goals"],
        },
    },
    {
        "name": "get_training_plan",
        "description": "Retrieve the full stored training plan, or a specific week.",
        "input_schema": {
            "type": "object",
            "properties": {
                "week_number": {
                    "type": "integer",
                    "description": "Specific week to retrieve. Omit for full plan.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_todays_workout",
        "description": "Get today's scheduled workout from the training plan.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "store_generated_plan",
        "description": "Store a newly generated training plan (list of day objects). Call this after generating the plan JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_json": {
                    "type": "array",
                    "description": "Array of training plan day objects",
                    "items": {"type": "object"},
                }
            },
            "required": ["plan_json"],
        },
    },
    {
        "name": "update_plan_days",
        "description": "Modify specific future training plan days (e.g. after a workout recap reveals fatigue).",
        "input_schema": {
            "type": "object",
            "properties": {
                "adjustments": {
                    "type": "array",
                    "description": "List of day modifications. Each has 'date' (ISO) plus fields to update.",
                    "items": {"type": "object"},
                }
            },
            "required": ["adjustments"],
        },
    },
    {
        "name": "get_workout_log",
        "description": "Retrieve recent post-workout journal entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of past days. Default 7.",
                    "default": 7,
                }
            },
            "required": [],
        },
    },
    {
        "name": "log_workout",
        "description": "Store a post-workout recap with perceived effort and any pain/notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_recap": {"type": "string", "description": "The user's description of the workout"},
                "perceived_effort": {
                    "type": "integer",
                    "description": "Perceived effort 1-10",
                    "minimum": 1,
                    "maximum": 10,
                },
                "pain_notes": {"type": "string", "description": "Any pain or discomfort noted", "default": ""},
                "strava_activity_id": {"type": "string", "description": "Strava activity ID if linked", "default": ""},
            },
            "required": ["user_recap"],
        },
    },
    {
        "name": "get_daily_recommendation",
        "description": "Calculate recommended training intensity based on Whoop recovery score and recent strain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "recovery_score": {"type": "number", "description": "Whoop recovery score 0-100"},
                "recent_strain_scores": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Whoop strain scores from last 1-3 days",
                },
            },
            "required": ["recovery_score", "recent_strain_scores"],
        },
    },
]


def _dispatch_tool(name: str, inputs: dict) -> str:
    """Call the appropriate tool function and return JSON string result."""
    try:
        if name == "get_whoop_recovery":
            result = get_whoop_recovery()
        elif name == "get_whoop_sleep":
            result = get_whoop_sleep()
        elif name == "get_whoop_strain":
            result = get_whoop_strain()
        elif name == "get_strava_activities":
            result = get_strava_activities(days=inputs.get("days", 7))
        elif name == "get_fitness_profile":
            result = get_fitness_profile()
        elif name == "save_fitness_profile":
            result = save_fitness_profile(**inputs)
        elif name == "get_training_plan":
            result = get_training_plan(week_number=inputs.get("week_number"))
        elif name == "get_todays_workout":
            result = get_todays_workout()
        elif name == "store_generated_plan":
            result = store_generated_plan(inputs.get("plan_json", []))
        elif name == "update_plan_days":
            result = update_plan_days(inputs.get("adjustments", []))
        elif name == "get_workout_log":
            result = get_workout_log(days=inputs.get("days", 7))
        elif name == "log_workout":
            result = log_workout(**inputs)
        elif name == "get_daily_recommendation":
            result = get_daily_recommendation(
                recovery_score=inputs["recovery_score"],
                recent_strain_scores=inputs.get("recent_strain_scores", []),
            )
        else:
            result = {"error": "unknown_tool", "message": f"No tool named {name}"}
    except Exception as e:
        result = {"error": "tool_error", "message": str(e)}

    return json.dumps(result)


def run_agent(messages: list[dict], max_iterations: int = 10) -> str:
    """
    Run the agentic loop synchronously.
    Returns the final text response from Goggins.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = list(messages)

    for _ in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )

        if response.stop_reason == "end_turn":
            # Extract final text
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            # Add assistant message with tool calls
            history.append({"role": "assistant", "content": response.content})

            # Dispatch all tool calls in this turn
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_content = _dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })

            history.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            break

    return "Something went wrong. Try again."


async def stream_agent(messages: list[dict], max_iterations: int = 10) -> AsyncIterator[str]:
    """
    Run the agentic loop with streaming on the final response turn.
    Yields text chunks as they arrive from Claude.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = list(messages)

    for iteration in range(max_iterations):
        # Check if this might be the final turn (no tool calls expected)
        # We stream only the last turn; prior turns run normally
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )

        if response.stop_reason == "end_turn":
            # Stream the final text block
            for block in response.content:
                if hasattr(block, "text"):
                    # Yield in chunks to simulate streaming
                    text = block.text
                    chunk_size = 20
                    for i in range(0, len(text), chunk_size):
                        yield text[i:i + chunk_size]
            return

        if response.stop_reason == "tool_use":
            history.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_content = _dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_content,
                    })
            history.append({"role": "user", "content": tool_results})
        else:
            break

    yield "Something went wrong. Try again."
