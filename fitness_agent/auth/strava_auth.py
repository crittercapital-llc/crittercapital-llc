"""Strava OAuth2 configuration."""
import os
from fitness_agent.auth.oauth import build_auth_url, exchange_code, get_valid_token

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_SCOPES = "activity:read_all"
PROVIDER = "strava"


def _cfg():
    return {
        "client_id": os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
    }


def get_auth_url(redirect_uri: str) -> str:
    cfg = _cfg()
    return build_auth_url(
        auth_endpoint=STRAVA_AUTH_URL,
        client_id=cfg["client_id"],
        redirect_uri=redirect_uri,
        scope=STRAVA_SCOPES,
        provider=PROVIDER,
    )


def handle_callback(code: str, state: str, redirect_uri: str) -> dict:
    cfg = _cfg()
    return exchange_code(
        token_endpoint=STRAVA_TOKEN_URL,
        code=code,
        state=state,
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri=redirect_uri,
        provider=PROVIDER,
    )


def get_token() -> str:
    cfg = _cfg()
    return get_valid_token(
        token_endpoint=STRAVA_TOKEN_URL,
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        provider=PROVIDER,
    )
