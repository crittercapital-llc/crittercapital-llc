"""Generic OAuth2 Authorization Code + PKCE helpers."""
import base64
import hashlib
import os
import secrets
import time
from urllib.parse import urlencode

import httpx

from fitness_agent.storage.db import (
    get_token, save_token, save_pkce_state, pop_pkce_state
)


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def build_auth_url(auth_endpoint: str, client_id: str, redirect_uri: str,
                   scope: str, provider: str) -> str:
    """Build the OAuth2 authorization URL and persist PKCE state."""
    state = secrets.token_urlsafe(16)
    code_verifier, code_challenge = generate_pkce()
    save_pkce_state(state, code_verifier, provider)

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{auth_endpoint}?{urlencode(params)}"


def exchange_code(token_endpoint: str, code: str, state: str,
                  client_id: str, client_secret: str,
                  redirect_uri: str, provider: str) -> dict:
    """Exchange auth code for tokens. Returns the raw token response dict."""
    pkce = pop_pkce_state(state)
    if not pkce:
        raise ValueError("Invalid or expired OAuth state")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": pkce["code_verifier"],
    }
    resp = httpx.post(token_endpoint, data=data, timeout=15)
    resp.raise_for_status()
    token_data = resp.json()

    save_token(
        provider=provider,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        expires_in=token_data.get("expires_in"),
        scope=token_data.get("scope"),
    )
    return token_data


def refresh_access_token(token_endpoint: str, client_id: str, client_secret: str,
                         provider: str) -> str:
    """Refresh the access token using the stored refresh token."""
    stored = get_token(provider)
    if not stored or not stored.get("refresh_token"):
        raise ValueError(f"No refresh token for {provider}. Re-authenticate.")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": stored["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = httpx.post(token_endpoint, data=data, timeout=15)
    resp.raise_for_status()
    token_data = resp.json()

    save_token(
        provider=provider,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", stored["refresh_token"]),
        expires_in=token_data.get("expires_in"),
        scope=token_data.get("scope", stored.get("scope")),
    )
    return token_data["access_token"]


def get_valid_token(token_endpoint: str, client_id: str, client_secret: str,
                    provider: str) -> str:
    """Return a valid access token, refreshing if within 60s of expiry."""
    stored = get_token(provider)
    if not stored:
        raise ValueError(f"Not authenticated with {provider}. Connect it in Settings.")

    expires_at = stored.get("expires_at", 0)
    if time.time() >= (expires_at - 60):
        return refresh_access_token(token_endpoint, client_id, client_secret, provider)

    return stored["access_token"]
