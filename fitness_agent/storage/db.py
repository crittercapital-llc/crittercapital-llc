import sqlite3
import json
import time
import os
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "./fitness_agent.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tokens (
                provider TEXT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at INTEGER,
                scope TEXT,
                updated_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY DEFAULT 1,
                goals TEXT,
                timeline_weeks INTEGER,
                restrictions TEXT,
                preferred_sports TEXT,
                days_per_week INTEGER,
                fitness_level TEXT,
                created_at INTEGER,
                updated_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS training_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_number INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                date TEXT,
                workout_type TEXT,
                description TEXT,
                target_distance_km REAL,
                target_duration_min INTEGER,
                intensity TEXT,
                completed INTEGER DEFAULT 0,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS workout_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                user_recap TEXT,
                strava_activity_id TEXT,
                perceived_effort INTEGER,
                pain_notes TEXT,
                claude_feedback TEXT,
                plan_adjustments TEXT,
                created_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS pkce_state (
                state TEXT PRIMARY KEY,
                code_verifier TEXT NOT NULL,
                provider TEXT NOT NULL,
                created_at INTEGER
            );
        """)


# ── Token helpers ──────────────────────────────────────────────────────────────

def save_token(provider: str, access_token: str, refresh_token: str | None,
               expires_in: int | None, scope: str | None):
    expires_at = int(time.time()) + (expires_in or 3600)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO tokens (provider, access_token, refresh_token, expires_at, scope, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                access_token=excluded.access_token,
                refresh_token=excluded.refresh_token,
                expires_at=excluded.expires_at,
                scope=excluded.scope,
                updated_at=excluded.updated_at
        """, (provider, access_token, refresh_token, expires_at, scope, int(time.time())))


def get_token(provider: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tokens WHERE provider = ?", (provider,)).fetchone()
        return dict(row) if row else None


def is_authenticated(provider: str) -> bool:
    token = get_token(provider)
    return token is not None and token.get("access_token") is not None


# ── PKCE state helpers ─────────────────────────────────────────────────────────

def save_pkce_state(state: str, code_verifier: str, provider: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO pkce_state (state, code_verifier, provider, created_at)
            VALUES (?, ?, ?, ?)
        """, (state, code_verifier, provider, int(time.time())))


def pop_pkce_state(state: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pkce_state WHERE state = ?", (state,)).fetchone()
        if row:
            conn.execute("DELETE FROM pkce_state WHERE state = ?", (state,))
            return dict(row)
        return None


# ── Profile helpers ────────────────────────────────────────────────────────────

def get_profile() -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("preferred_sports"):
            try:
                d["preferred_sports"] = json.loads(d["preferred_sports"])
            except Exception:
                d["preferred_sports"] = []
        return d


def save_profile(goals: str, timeline_weeks: int, restrictions: str,
                 preferred_sports: list, days_per_week: int, fitness_level: str):
    now = int(time.time())
    sports_json = json.dumps(preferred_sports)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO user_profile (id, goals, timeline_weeks, restrictions, preferred_sports,
                                      days_per_week, fitness_level, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                goals=excluded.goals,
                timeline_weeks=excluded.timeline_weeks,
                restrictions=excluded.restrictions,
                preferred_sports=excluded.preferred_sports,
                days_per_week=excluded.days_per_week,
                fitness_level=excluded.fitness_level,
                updated_at=excluded.updated_at
        """, (goals, timeline_weeks, restrictions, sports_json,
              days_per_week, fitness_level, now, now))


# ── Training plan helpers ──────────────────────────────────────────────────────

def clear_plan():
    with get_conn() as conn:
        conn.execute("DELETE FROM training_plan")


def insert_plan_days(days: list[dict]):
    with get_conn() as conn:
        conn.executemany("""
            INSERT INTO training_plan
                (week_number, day_of_week, date, workout_type, description,
                 target_distance_km, target_duration_min, intensity, completed, notes)
            VALUES
                (:week_number, :day_of_week, :date, :workout_type, :description,
                 :target_distance_km, :target_duration_min, :intensity, 0, :notes)
        """, days)


def get_plan(week_number: int | None = None) -> list[dict]:
    with get_conn() as conn:
        if week_number is not None:
            rows = conn.execute(
                "SELECT * FROM training_plan WHERE week_number = ? ORDER BY week_number, day_of_week",
                (week_number,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM training_plan ORDER BY week_number, day_of_week"
            ).fetchall()
        return [dict(r) for r in rows]


def get_todays_plan_entry() -> dict | None:
    from datetime import date
    today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM training_plan WHERE date = ?", (today,)
        ).fetchone()
        return dict(row) if row else None


def update_plan_entries(adjustments: list[dict]):
    """Each adjustment: { date: str, description: str, intensity: str, ... }"""
    with get_conn() as conn:
        for adj in adjustments:
            sets = []
            params = []
            for field in ("description", "workout_type", "intensity",
                          "target_distance_km", "target_duration_min", "notes"):
                if field in adj:
                    sets.append(f"{field} = ?")
                    params.append(adj[field])
            if sets and "date" in adj:
                params.append(adj["date"])
                conn.execute(
                    f"UPDATE training_plan SET {', '.join(sets)} WHERE date = ?",
                    params
                )


def mark_plan_entry_complete(date_str: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE training_plan SET completed = 1 WHERE date = ?", (date_str,)
        )


# ── Workout log helpers ────────────────────────────────────────────────────────

def save_workout_log(date_str: str, user_recap: str, perceived_effort: int | None,
                     pain_notes: str | None, strava_activity_id: str | None,
                     claude_feedback: str | None, plan_adjustments: list | None) -> int:
    now = int(time.time())
    adj_json = json.dumps(plan_adjustments) if plan_adjustments else None
    with get_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO workout_log
                (date, user_recap, strava_activity_id, perceived_effort,
                 pain_notes, claude_feedback, plan_adjustments, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_str, user_recap, strava_activity_id, perceived_effort,
              pain_notes, claude_feedback, adj_json, now))
        return cursor.lastrowid


def get_workout_logs(days: int = 7) -> list[dict]:
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM workout_log WHERE date >= ? ORDER BY date DESC",
            (cutoff,)
        ).fetchall()
        return [dict(r) for r in rows]
