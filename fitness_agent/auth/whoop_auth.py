"""Whoop OAuth2 configuration."""
import os
from fitness_agent.auth.oauth import build_auth_url, exchange_code, get_valid_token

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_SCOPES = "read:recovery read:sleep read:cycles offline"
PROVIDER = "whoop"


def _cfg():
    return {
        "client_id": os.environ["WHOOP_CLIENT_ID"],
        "client_secret": os.environ["WHOOP_CLIENT_SECRET"],
        "redirect_uri": os.environ.get("WHOOP_REDIRECT_URI", ""),
    }


def get_auth_url(redirect_uri: str) -> str:
    cfg = _cfg()
    return build_auth_url(
        auth_endpoint=WHOOP_AUTH_URL,
        client_id=cfg["client_id"],
        redirect_uri=redirect_uri,
        scope=WHOOP_SCOPES,
        provider=PROVIDER,
    )


def handle_callback(code: str, state: str, redirect_uri: str) -> dict:
    cfg = _cfg()
    return exchange_code(
        token_endpoint=WHOOP_TOKEN_URL,
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
        token_endpoint=WHOOP_TOKEN_URL,
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        provider=PROVIDER,
    )
