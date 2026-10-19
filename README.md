# Maathru Care Nutrition API

Small FastAPI service for authenticated maternal-food search and the nutrition component's My Foods operations. It forwards each caller's Supabase access token and uses only the project's anon key, so Supabase Auth and table RLS remain in force. It does not contain a service-role key.

## Local run

1. Copy `.env.example` to `.env` and set `SUPABASE_URL` and `SUPABASE_ANON_KEY` from the same Supabase project used by the Expo app.
2. Create a virtual environment and install `requirements.txt`.
3. Run `uvicorn app.main:app --host 0.0.0.0 --port 5001 --reload`.
4. Set the Expo app's `EXPO_PUBLIC_NUTRITION_API_URL` to `http://localhost:5001/api/v1` for web/iOS. Android emulators use `http://10.0.2.2:5001/api/v1` by default. For a physical phone, set the variable to the computer's LAN address.

`GET /health` is unauthenticated. All food routes require the user's Supabase access token as a Bearer token. `GET /api/v1/foods/search?q=...` searches display name, English name, scientific name, and food ID. `GET /api/v1/foods/custom` and `/search`, and POST/PATCH/DELETE on `/api/v1/foods/custom`, use the caller's database permissions.

My Foods requires the reviewed `user_custom_foods` migration to be applied to the Supabase project. Until then the API returns an explicit `503 CUSTOM_FOODS_NOT_CONFIGURED`; it never pretends the account has an empty list. No migration is run by this project. Risk-history is intentionally not provided because the inspected project has no risk-history table/schema. The unrelated AI model API remains separate.

## Render

Create a Python web service from this directory, install with `pip install -r requirements.txt`, and start with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and a comma-separated `ALLOWED_ORIGINS` environment variable. Do not add a service-role key.

## Tests

Install `requirements-dev.txt` and run `pytest` from this directory. The tests cover the health endpoint, auth requirement, field filter construction, and relevance ranking without connecting to Supabase.

