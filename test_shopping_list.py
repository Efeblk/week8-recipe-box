import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _make(title: str, ingredients: list[str] | None = None) -> int:
    body: dict = {"title": title}
    if ingredients is not None:
        body["ingredients"] = ingredients
    r = client.post("/recipes", json=body)
    assert r.status_code == 200
    return r.json()["id"]


def _missing_id() -> int:
    return max(r["id"] for r in client.get("/recipes").json()) + 1000


def test_single_recipe():
    rid = _make("Pancakes", ["flour", "milk", "eggs"])
    r = client.get(f"/shopping-list?ids={rid}")
    assert r.status_code == 200
    assert r.json() == {"recipe_ids": [rid], "ingredients": ["flour", "milk", "eggs"]}


def test_merge_and_dedupe_across_recipes_preserves_order():
    a = _make("A", ["flour", "milk", "eggs"])
    b = _make("B", ["sugar", "milk", "butter"])
    c = _make("C", ["eggs", "salt"])
    r = client.get(f"/shopping-list?ids={a},{b},{c}")
    assert r.status_code == 200
    assert r.json() == {
        "recipe_ids": [a, b, c],
        "ingredients": ["flour", "milk", "eggs", "sugar", "butter", "salt"],
    }


def test_requested_order_is_respected():
    a = _make("A", ["flour"])
    b = _make("B", ["sugar"])
    r = client.get(f"/shopping-list?ids={b},{a}")
    assert r.json() == {"recipe_ids": [b, a], "ingredients": ["sugar", "flour"]}


def test_case_insensitive_dedupe_keeps_first_seen_casing():
    a = _make("A", ["Flour", "MILK"])
    b = _make("B", ["flour", "milk", "Eggs"])
    r = client.get(f"/shopping-list?ids={a},{b}")
    assert r.json()["ingredients"] == ["Flour", "MILK", "Eggs"]


def test_whitespace_is_trimmed_and_deduped():
    a = _make("A", ["  flour ", "milk"])
    b = _make("B", ["flour", "  Milk  ", "\tsugar\n"])
    r = client.get(f"/shopping-list?ids={a},{b}")
    assert r.json()["ingredients"] == ["flour", "milk", "sugar"]


def test_duplicates_within_a_single_recipe():
    a = _make("A", ["salt", "Salt", " salt "])
    r = client.get(f"/shopping-list?ids={a}")
    assert r.json()["ingredients"] == ["salt"]


def test_blank_ingredients_are_ignored():
    a = _make("A", ["", "   ", "flour"])
    r = client.get(f"/shopping-list?ids={a}")
    assert r.json()["ingredients"] == ["flour"]


def test_duplicate_ids_in_query_are_collapsed():
    a = _make("A", ["flour", "milk"])
    b = _make("B", ["sugar"])
    r = client.get(f"/shopping-list?ids={a},{b},{a}")
    assert r.status_code == 200
    assert r.json() == {"recipe_ids": [a, b], "ingredients": ["flour", "milk", "sugar"]}


def test_whitespace_around_ids_is_tolerated():
    a = _make("A", ["flour"])
    b = _make("B", ["sugar"])
    r = client.get("/shopping-list", params={"ids": f" {a} , {b} "})
    assert r.status_code == 200
    assert r.json()["recipe_ids"] == [a, b]


def test_recipe_with_empty_ingredients():
    a = _make("Empty", [])
    r = client.get(f"/shopping-list?ids={a}")
    assert r.status_code == 200
    assert r.json() == {"recipe_ids": [a], "ingredients": []}


def test_recipe_with_default_ingredients():
    a = _make("NoIngredientsField")
    r = client.get(f"/shopping-list?ids={a}")
    assert r.status_code == 200
    assert r.json()["ingredients"] == []


def test_empty_recipe_merged_with_nonempty():
    a = _make("Empty", [])
    b = _make("Full", ["rice"])
    r = client.get(f"/shopping-list?ids={a},{b}")
    assert r.json() == {"recipe_ids": [a, b], "ingredients": ["rice"]}


@pytest.mark.parametrize(
    "ids",
    [
        None,  # param omitted
        "",
        "   ",
        "abc",
        "1,abc",
        "1,,2",
        "1,2,",
        ",1",
        ",",
        "0",
        "-1",
        "1,-2",
        "1.5",
        "+1",
        "1 2",
        "1;2",
    ],
)
def test_malformed_ids_return_400(ids):
    _make("Anchor", ["flour"])  # make sure the DB is not empty
    params = {} if ids is None else {"ids": ids}
    r = client.get("/shopping-list", params=params)
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


def test_unknown_id_returns_404_listing_missing():
    a = _make("A", ["flour"])
    missing = _missing_id()
    r = client.get(f"/shopping-list?ids={a},{missing}")
    assert r.status_code == 404
    assert r.json()["detail"].endswith(str(missing))


def test_all_missing_ids_listed_in_404():
    m1 = _missing_id()
    m2 = m1 + 1
    r = client.get(f"/shopping-list?ids={m1},{m2}")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert str(m1) in detail and str(m2) in detail


def test_only_unknown_id_returns_404():
    r = client.get(f"/shopping-list?ids={_missing_id()}")
    assert r.status_code == 404
