from typing import Any

import httpx
from fastapi import HTTPException

from app.config import Settings


class SupabaseRest:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.supabase_url.rstrip("/")

    def headers(self, access_token: str, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.settings.supabase_anon_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    async def request(
        self,
        method: str,
        path: str,
        access_token: str,
        *,
        params: dict[str, str] | None = None,
        body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=self.headers(access_token, prefer=prefer),
                    params=params,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Supabase request timed out.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not reach Supabase.") from exc

        if response.is_success:
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        if response.status_code in (401, 403):
            raise HTTPException(status_code=response.status_code, detail="Supabase rejected this request.")
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        code = payload.get("code") if isinstance(payload, dict) else None
        if code in ("42P01", "PGRST205"):
            raise HTTPException(
                status_code=503,
                detail={"code": "CUSTOM_FOODS_NOT_CONFIGURED", "message": "My Foods requires its database migration."},
            )
        if code == "23505":
            raise HTTPException(status_code=409, detail="A food with this name already exists in My Foods.")
        message = payload.get("message") if isinstance(payload, dict) else None
        raise HTTPException(status_code=response.status_code, detail=message or "Supabase rejected the request.")

    async def authenticate(self, access_token: str) -> dict[str, Any]:
        user = await self.request("GET", "/auth/v1/user", access_token)
        if not isinstance(user, dict) or not user.get("id"):
            raise HTTPException(status_code=401, detail="Sign in to continue.")
        return user

