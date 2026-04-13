"""
Goggins — Fitness Personal Training Agent.

Claude claude-sonnet-4-6 with tool use. Agentic loop runs until end_turn.
No external API integrations — all data is manually provided by the user.
"""
import json
import os
from typing import AsyncIterator

import anthropic

from fitness_agent.tools.profile import get_fitness_profile, save_fitness_profile
from fitness_agent.tools.training_plan import (
    get_training_plan, get_todays_workout, store_generated_plan,
    update_plan_days, complete_todays_workout
)
from fitness_agent.tools.workout_log import log_workout, get_workout_log

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """Your name is Goggins. You are a former military special operations veteran turned elite personal trainer and coach. You have seen what the human body is capable of when the mind refuses to quit.

Your coaching style:
- Direct and no-nonsense. Cut to the point. No fluff.
- You push hard, but always with purpose — every hard session has a reason, every rest day is earned and intentional.
- You have deep empathy. You've been in pain. You know what it costs. You acknowledge struggle before you challenge it.
- You never mock, belittle, or shame. You hold people to a high standard because you believe they're capable of meeting it.
- When recovery is low, you scale back without hesitation — overtraining destroys the mission.
- You celebrate wins briefly, then immediately ask what's next.
- You speak in plain, direct language. No corporate wellness speak. No coddling.
- Keep responses concise and formatted for mobile reading. Use short paragraphs. Use bullet points only for listing exercises or key items.

Recovery score guidance (user provides this manually from their Whoop):
- 0–33: Rest or very light movement only. Non-negotiable.
- 34–50: Easy session. Nothing that pushes heart rate high.
- 51–66: Moderate work. Solid aerobic session.
- 67–83: Good day. Quality work is appropriate.
- 84–100: Peak day. Go after it.

Example responses:
- Low recovery check-in: "Score of 38 with knee pain — that's your body talking. Today we pull back. 20 min easy walk, mobility work. That's it. Fighting through this would cost you next week."
- High recovery check-in: "Score of 91. No excuses today. Here's exactly what you're doing: [adapted workout]. Get after it."
- After tough workout log: "That hurt. Good. That's exactly where you needed to go. Rest well tonight — we build on this tomorrow."
- After easy workout log: "Solid. Recovery work done right. Your body is banking that adaptation. Tomorrow we go harder."

When generating a training plan, output the plan as a JSON array inside <plan>...</plan> tags, then follow with your coaching message. Each day must have: week_number (int), day_of_week (1=Mon, 7=Sun), workout_type (string), description (string), target_distance_km (float or null), target_duration_min (int or null), intensity (rest/easy/moderate/hard/peak), notes (string).

Always check the user's profile and recent workout logs before giving advice. Use the data — don't guess.
"""

TOOLS = [
    {
        "name": "get_fitness_profile",
        "description": "Read the user's stored fitness goals, current fitness level, restrictions, and training preferences.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "save_fitness_profile",
        "description": "Store the user's fitness goals and preferences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goals": {"type": "string", "description": "Primary fitness goal"},
                "current_fitness": {"type": "string", "description": "Description of current fitness level, e.g. 'Run 3x/week, 5km avg, no strength training'"},
                "timeline_weeks": {"type": "integer", "description": "Training timeline in weeks", "default": 12},
                "restrictions": {"type": "string", "description": "Injuries or physical limitations", "default": ""},
                "preferred_sports": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of preferred activities",
                },
                "days_per_week": {"type": "integer", "description": "Available training days per week", "default": 5},
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
        "description": "Store a newly generated training plan. Call this after generating the plan JSON.",
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
        "description": "Modify specific future training plan days (e.g. after a workout log reveals fatigue or breakthrough).",
        "input_schema": {
            "type": "object",
            "properties": {
                "adjustments": {
                    "type": "array",
                    "description": "List of day modifications. Each must have 'date' (ISO string) plus fields to update.",
                    "items": {"type": "object"},
                }
            },
            "required": ["adjustments"],
        },
    },
    {
        "name": "get_workout_log",
        "description": "Retrieve recent post-workout journal entries including exercises, effort scores, and recovery notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of past days to retrieve. Default 7.",
                    "default": 7,
                }
            },
            "required": [],
        },
    },
    {
        "name": "log_workout",
        "description": "Store a post-workout entry: what the athlete did, exercises/weights, effort, and how they felt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_recap": {"type": "string", "description": "Free-text description of the workout"},
                "exercises": {
                    "type": "array",
                    "description": "List of exercises with sets/reps/weight",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "sets": {"type": "integer"},
                            "reps": {"type": "integer"},
                            "weight_lbs": {"type": "number"},
                            "notes": {"type": "string"},
                        },
                    },
                },
                "perceived_effort": {
                    "type": "integer",
                    "description": "Perceived effort 1–10",
                    "minimum": 1,
                    "maximum": 10,
                },
                "recovery_score": {
                    "type": "integer",
                    "description": "Whoop recovery score used before this workout (0–100)",
                },
                "pre_workout_notes": {"type": "string", "description": "How the athlete felt going in, any pain"},
                "post_notes": {"type": "string", "description": "How they felt after the workout"},
            },
            "required": ["user_recap"],
        },
    },
]


def _dispatch_tool(name: str, inputs: dict) -> str:
    try:
        if name == "get_fitness_profile":
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
        else:
            result = {"error": "unknown_tool", "message": f"No tool named {name}"}
    except Exception as e:
        result = {"error": "tool_error", "message": str(e)}

    return json.dumps(result)


def run_agent(messages: list[dict], max_iterations: int = 10) -> str:
    """Run the agentic loop synchronously. Returns the final text response."""
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
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

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

    return "Something went wrong. Try again."


async def stream_agent(messages: list[dict], max_iterations: int = 10) -> AsyncIterator[str]:
    """Run the agentic loop, yielding text chunks on the final response."""
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
            for block in response.content:
                if hasattr(block, "text"):
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
