import pytest
from fastapi.testclient import TestClient

import main
from main import _scale_ingredient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient backed by a fresh SQLite file so tests never touch the default database."""
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "recipes.db")
    main.init_db()
    with TestClient(main.app) as test_client:
        yield test_client


def _create(client, ingredients):
    r = client.post("/recipes", json={"title": "Scale me", "ingredients": ingredients})
    return r.json()["id"]


def test_scale_doubles_quantities(client):
    rid = _create(client, ["200 g flour", "2 eggs", "salt"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["ingredients"] == ["400 g flour", "4 eggs", "salt"]
    assert body["title"] == "Scale me"
    assert body["factor"] == 2


def test_scale_fractional_factor(client):
    rid = _create(client, ["200 g flour", "1 egg"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 0.5})
    assert r.json()["ingredients"] == ["100 g flour", "0.5 egg"]


def test_scale_does_not_modify_stored_recipe(client):
    rid = _create(client, ["200 g flour"])
    scaled = client.get(f"/recipes/{rid}/scaled", params={"factor": 3})
    assert scaled.status_code == 200
    assert scaled.json()["ingredients"] == ["600 g flour"]
    assert client.get(f"/recipes/{rid}").json()["ingredients"] == ["200 g flour"]


def test_scale_preserves_metadata_and_documented_factor_field(client):
    r = client.post(
        "/recipes", json={"title": "Meta", "ingredients": ["1 egg"], "tags": ["breakfast", "quick"]}
    )
    rid = r.json()["id"]
    body = client.get(f"/recipes/{rid}/scaled", params={"factor": 2}).json()
    assert body == {
        "id": rid,
        "title": "Meta",
        "ingredients": ["2 egg"],
        "tags": ["breakfast", "quick"],
        "factor": 2,
    }


def test_scale_empty_ingredient_list(client):
    rid = _create(client, [])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.status_code == 200
    assert r.json()["ingredients"] == []


def test_scaled_unknown_recipe_404(client):
    assert client.get("/recipes/99999").status_code == 404
    r = client.get("/recipes/99999/scaled", params={"factor": 2})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "factor",
    ["0", "-1", "abc", "nan", "inf", "-inf", "0.0009", "1e-5", "1000.5", "1001", "1e308"],
)
def test_invalid_factor_rejected(client, factor):
    rid = _create(client, ["200 g flour"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": factor})
    assert r.status_code == 422


@pytest.mark.parametrize("factor, expected", [("0.001", "0.2 g flour"), ("1000", "200000 g flour")])
def test_factor_bounds_are_inclusive(client, factor, expected):
    rid = _create(client, ["200 g flour"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": factor})
    assert r.status_code == 200
    assert r.json()["ingredients"] == [expected]


def test_missing_factor_rejected(client):
    rid = _create(client, ["200 g flour"])
    assert client.get(f"/recipes/{rid}/scaled").status_code == 422


@pytest.mark.parametrize(
    "ingredient, factor, expected",
    [
        ("200 g flour", 2, "400 g flour"),
        ("1/2 cup sugar", 2, "1 cup sugar"),
        ("1 1/2 cups milk", 2, "3 cups milk"),
        ("2.5 tbsp oil", 2, "5 tbsp oil"),
        ("salt to taste", 2, "salt to taste"),
        ("", 2, ""),
        ("200g flour", 2, "400g flour"),
        ("1.5 tbsp oil", 2, "3 tbsp oil"),
        ("  200 g flour", 2, "  400 g flour"),
        ("a pinch of pepper", 2, "a pinch of pepper"),
        # ranges: both endpoints scale, delimiter and suffix preserved
        ("2-3 eggs", 2, "4-6 eggs"),
        ("1–2 cloves garlic", 2, "2–4 cloves garlic"),
        ("1—2 cloves", 3, "3—6 cloves"),
        ("2 - 3 eggs", 2, "4 - 6 eggs"),
        ("1/2-1 cup milk", 2, "1-2 cup milk"),
        ("1 1/2-2 cups milk", 2, "3-4 cups milk"),
        # float noise and precision
        ("0.1 cup", 3, "0.3 cup"),
        ("1/2 cup", 0.001, "0.0005 cup"),
        ("12345.67 g", 1, "12345.67 g"),
        ("1/3 cup", 3, "1 cup"),
        ("1/3 cup", 1, "0.3333333333 cup"),
        ("0.0001 g salt", 0.001, "0.0000001 g salt"),
        ("0.0001 g saffron", 0.001, "0.0000001 g saffron"),
        ("1 egg", 0.001, "0.001 egg"),
        ("999999999 g", 1000, "999999999000 g"),
        # exact integers and decimals stay exact, beyond float/10-significant-digit limits
        ("12345678901 g", 1, "12345678901 g"),
        ("12345678901 g", 2, "24691357802 g"),
        ("123456789012345678901234567890 g", 1, "123456789012345678901234567890 g"),
        ("1234567.891234567 g", 1, "1234567.891234567 g"),
        # tiny positive quantities never underflow to zero
        ("0." + "0" * 322 + "1 g", 0.001, "0." + "0" * 325 + "1 g"),
        ("1/1" + "0" * 309 + " cup", 2, "0." + "0" * 308 + "2 cup"),
        # true zeros stay zero
        ("0 g", 2, "0 g"),
        ("0.0 g", 2, "0 g"),
        ("0/5 cup", 2, "0 cup"),
        # numeric token boundaries: hyphenated descriptors, attached units, leading dot
        ("1-inch ginger", 2, "2-inch ginger"),
        ("2 8-oz cans tomatoes", 2, "4 8-oz cans tomatoes"),
        ("1 12-oz can beans", 2, "2 12-oz can beans"),
        (".5 tsp salt", 2, "1 tsp salt"),
        ("1/2-3/4 cup milk", 2, "1-1.5 cup milk"),
        ("1/2 - 1 cup milk", 2, "1 - 2 cup milk"),
        ("1 1/2 - 2 1/2 cups", 2, "3 - 5 cups"),
        # malformed or unscalable quantities are preserved verbatim
        ("1/0 cup", 2, "1/0 cup"),
        ("1 1/0 cup", 2, "1 1/0 cup"),
        ("1-1/0 cup", 2, "1-1/0 cup"),
        ("1/2/3 cup", 2, "1/2/3 cup"),
        ("1.2.3 g", 2, "1.2.3 g"),
        ("1/ cup", 2, "1/ cup"),
        ("1-2/ cup", 2, "1-2/ cup"),
        ("1-1/2/3 cup", 2, "1-1/2/3 cup"),
        ("1 1/2/3 cup", 2, "1 1/2/3 cup"),
        ("1..5 g", 2, "1..5 g"),
        ("1. mix well", 2, "1. mix well"),
        ("..5 g", 2, "..5 g"),
        ("/2 cup", 2, "/2 cup"),
    ],
)
def test_scale_ingredient(ingredient, factor, expected):
    assert _scale_ingredient(ingredient, factor) == expected


def test_huge_integer_scales_exactly():
    assert _scale_ingredient("9" * 400 + " g", 1000) == "9" * 400 + "000 g"


def test_scale_route_exact_and_malformed(client):
    rid = _create(
        client,
        ["12345678901 g", "1/2/3 cup", "1.2.3 g", "1-/2 cup", "1-..5 cups", "1-inch ginger"],
    )
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 1})
    assert r.json()["ingredients"] == [
        "12345678901 g",
        "1/2/3 cup",
        "1.2.3 g",
        "1-/2 cup",
        "1-..5 cups",
        "1-inch ginger",
    ]
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.json()["ingredients"] == [
        "24691357802 g",
        "1/2/3 cup",
        "1.2.3 g",
        "1-/2 cup",
        "1-..5 cups",
        "2-inch ginger",
    ]


def test_scale_tests_use_isolated_database(client, tmp_path):
    assert main.DB_PATH == tmp_path / "recipes.db"
    assert client.get("/recipes").json() == []
