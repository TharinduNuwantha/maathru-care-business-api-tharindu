import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from fastapi.testclient import TestClient

from app.main import app, rank_foods, search_filter


client = TestClient(app)


def test_health_is_available_without_authentication():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_food_search_requires_bearer_token():
    response = client.get("/api/v1/foods/search", params={"q": "rice"})
    assert response.status_code == 401


def test_search_filter_covers_all_food_names_and_id():
    result = search_filter("red rice")
    assert "display_name.ilike" in result
    assert "english_name.ilike" in result
    assert "scientific_name.ilike" in result
    assert "food_id.ilike" in result


def test_food_results_rank_exact_and_prefix_matches_first():
    rows = [
        {"food_id": "brown_rice_2", "display_name": "Brown Rice"},
        {"food_id": "red_rice", "display_name": "Red Rice"},
        {"food_id": "rice", "display_name": "Rice"},
    ]
    result = rank_foods(rows, "red rice", 20)
    assert [row["food_id"] for row in result][0] == "red_rice"

