"""Supabase Auth HTTP helpers (signup / password grant)."""

from __future__ import annotations

import httpx

from .config import Settings


async def supabase_signup(settings: Settings, email: str, password: str) -> str:
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/signup"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers=headers,
            json={"email": email, "password": password},
        )
    data = resp.json()
    if resp.status_code >= 400:
        msg = data.get("msg") or data.get("error_description") or data.get("error") or resp.text
        raise RuntimeError(msg)
    # Email confirm may leave session empty
    access = data.get("access_token") or (data.get("session") or {}).get("access_token")
    if not access:
        raise RuntimeError(
            "Signup succeeded but no session returned. "
            "Disable email confirmations in Supabase Auth settings for API signup, "
            "or confirm the email then log in."
        )
    return access


async def supabase_login(settings: Settings, email: str, password: str) -> str:
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers=headers,
            json={"email": email, "password": password},
        )
    data = resp.json()
    if resp.status_code >= 400:
        msg = data.get("msg") or data.get("error_description") or data.get("error") or resp.text
        raise RuntimeError(msg)
    access = data.get("access_token")
    if not access:
        raise RuntimeError("No access_token in Supabase response")
    return access
