import pytest
from fastapi.testclient import TestClient

from main import _scale_ingredient, app

client = TestClient(app)


def _create(ingredients):
    r = client.post("/recipes", json={"title": "Scale me", "ingredients": ingredients})
    return r.json()["id"]


def test_scale_doubles_quantities():
    rid = _create(["200 g flour", "2 eggs", "salt"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["ingredients"] == ["400 g flour", "4 eggs", "salt"]
    assert body["title"] == "Scale me"
    assert body["factor"] == 2


def test_scale_fractional_factor():
    rid = _create(["200 g flour", "1 egg"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": 0.5})
    assert r.json()["ingredients"] == ["100 g flour", "0.5 egg"]


def test_scale_does_not_modify_stored_recipe():
    rid = _create(["200 g flour"])
    client.get(f"/recipes/{rid}/scaled", params={"factor": 3})
    assert client.get(f"/recipes/{rid}").json()["ingredients"] == ["200 g flour"]


def test_scaled_unknown_recipe_404():
    r = client.get("/recipes/99999/scaled", params={"factor": 2})
    assert r.status_code == 404


@pytest.mark.parametrize("factor", ["0", "-1", "abc", "nan", "inf"])
def test_invalid_factor_rejected(factor):
    rid = _create(["200 g flour"])
    r = client.get(f"/recipes/{rid}/scaled", params={"factor": factor})
    assert r.status_code == 422


def test_missing_factor_rejected():
    rid = _create(["200 g flour"])
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
    ],
)
def test_scale_ingredient(ingredient, factor, expected):
    assert _scale_ingredient(ingredient, factor) == expected
