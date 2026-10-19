import re
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.config import get_settings
from app.supabase_rest import SupabaseRest

settings = get_settings()
supabase = SupabaseRest(settings)
app = FastAPI(title="Maathru Care Nutrition API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

CUSTOM_FOOD_COLUMNS = "id,food_id,display_name,english_name,sinhala_name,category,serving_unit,verification_status,created_at,updated_at"
MATERNAL_FOOD_COLUMNS = "id,food_id,display_name,english_name,scientific_name,category,serving_unit,ref_mask_area,carbs_g,sugar_g,fiber_g,fat_g,iron_mg,calcium_mg,gi_index,is_contraindicated"
SEARCH_FIELDS = ("display_name", "english_name", "scientific_name", "food_id")


class CustomFoodInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    english_name: str | None = Field(default=None, max_length=100)
    sinhala_name: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=80)
    serving_unit: str | None = Field(default=None, max_length=40)


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="A valid Supabase Bearer token is required.")
    return token.strip()


def clean_food_input(food: CustomFoodInput) -> dict[str, str | None]:
    def clean(value: str | None) -> str | None:
        result = re.sub(r"\s+", " ", value.strip()) if value else ""
        return result or None

    display_name = clean(food.display_name)
    if not display_name:
        raise HTTPException(status_code=422, detail="Enter a food name.")
    return {
        "display_name": display_name,
        "english_name": clean(food.english_name),
        "sinhala_name": clean(food.sinhala_name),
        "category": clean(food.category),
        "serving_unit": clean(food.serving_unit),
    }


def search_filter(query: str) -> str:
    # Restrict PostgREST filter grammar metacharacters; search each useful token.
    normalized = re.sub(r"\s+", " ", query.strip())[:80]
    tokens = list(dict.fromkeys([normalized, *normalized.split()]))[:5]
    clauses = []
    for token in tokens:
        safe = re.sub(r"[^\w -]", " ", token, flags=re.UNICODE).strip()
        if not safe:
            continue
        safe = safe.replace("%", " ").replace("_", r"\_")
        clauses.extend(f'{field}.ilike."%{safe}%"' for field in SEARCH_FIELDS)
        food_id = safe.replace(" ", "_")
        if food_id != safe:
            clauses.append(f'food_id.ilike."%{food_id}%"')
    return ",".join(clauses)


def rank_foods(rows: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    needle = re.sub(r"[_-]+", " ", query).strip().casefold()
    def rank(row: dict[str, Any]) -> tuple[int, str]:
        fields = [str(row.get(field) or "").replace("_", " ").replace("-", " ").casefold() for field in SEARCH_FIELDS]
        for index, value in enumerate(fields):
            if value == needle:
                return index, str(row.get("display_name") or "").casefold()
        for index, value in enumerate(fields):
            if value.startswith(needle):
                return 10 + index, str(row.get("display_name") or "").casefold()
        for index, value in enumerate(fields):
            if needle in value:
                return 20 + index, str(row.get("display_name") or "").casefold()
        tokens = needle.split()
        matched = sum(any(token in value for value in fields) for token in tokens)
        return 40 + len(tokens) - matched, str(row.get("display_name") or "").casefold()
    unique = {row.get("food_id"): row for row in rows if row.get("food_id")}
    return sorted(unique.values(), key=rank)[:limit]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "maathru-care-nutrition-api"}


@app.get("/api/v1/foods/search")
async def search_maternal_foods(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    token: str = Depends(bearer_token),
) -> list[dict[str, Any]]:
    await supabase.authenticate(token)
    filt = search_filter(q)
    if not filt:
        return []
    rows = await supabase.request(
        "GET", "/rest/v1/maternal_foods", token,
        params={"select": MATERNAL_FOOD_COLUMNS, "or": f"({filt})", "limit": "100"},
    )
    return rank_foods(rows if isinstance(rows, list) else [], q, limit)


@app.get("/api/v1/foods/custom")
async def list_custom_foods(token: str = Depends(bearer_token)) -> Any:
    await supabase.authenticate(token)
    return await supabase.request(
        "GET", "/rest/v1/user_custom_foods", token,
        params={"select": CUSTOM_FOOD_COLUMNS, "order": "display_name.asc"},
    )


@app.get("/api/v1/foods/custom/search")
async def search_custom_foods(
    q: str = Query(min_length=2, max_length=80),
    token: str = Depends(bearer_token),
) -> Any:
    await supabase.authenticate(token)
    term = re.sub(r"[^\w -]", " ", q.strip(), flags=re.UNICODE).replace("%", " ").replace("_", r"\_")
    filt = ",".join(f'{field}.ilike."%{term}%"' for field in ("display_name", "english_name", "sinhala_name", "category"))
    return await supabase.request(
        "GET", "/rest/v1/user_custom_foods", token,
        params={"select": CUSTOM_FOOD_COLUMNS, "or": f"({filt})", "order": "display_name.asc", "limit": "20"},
    )


@app.post("/api/v1/foods/custom", status_code=201)
async def create_custom_food(food: CustomFoodInput, token: str = Depends(bearer_token)) -> Any:
    await supabase.authenticate(token)
    rows = await supabase.request(
        "POST", "/rest/v1/user_custom_foods", token,
        params={"select": CUSTOM_FOOD_COLUMNS}, body=clean_food_input(food), prefer="return=representation",
    )
    if not rows:
        raise HTTPException(status_code=502, detail="Supabase did not return the saved food.")
    return rows[0]


@app.patch("/api/v1/foods/custom/{food_id}")
async def update_custom_food(food_id: UUID, food: CustomFoodInput, token: str = Depends(bearer_token)) -> Any:
    await supabase.authenticate(token)
    rows = await supabase.request(
        "PATCH", "/rest/v1/user_custom_foods", token,
        params={"id": f"eq.{food_id}", "select": CUSTOM_FOOD_COLUMNS},
        body=clean_food_input(food), prefer="return=representation",
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Saved food not found.")
    return rows[0]


@app.delete("/api/v1/foods/custom/{food_id}", status_code=204)
async def delete_custom_food(food_id: UUID, token: str = Depends(bearer_token)) -> Response:
    await supabase.authenticate(token)
    rows = await supabase.request(
        "DELETE", "/rest/v1/user_custom_foods", token,
        params={"id": f"eq.{food_id}", "select": "id"}, prefer="return=representation",
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Saved food not found.")
    return Response(status_code=204)

