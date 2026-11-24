import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def recipe_catalog(monkeypatch, request):
    db_path = main.BASE / ".pytest_cache" / request.node.name / "recipes.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    monkeypatch.setattr(main, "DB_PATH", db_path)
    main.init_db()

    with TestClient(main.app) as client:
        recipes = []
        for title, tags in [
            ("Pancakes", ["sweet", "breakfast"]),
            ("Omelette", [" Breakfast "]),
            ("Soup", ["lunch"]),
            ("Toast", []),
        ]:
            response = client.post("/recipes", json={"title": title, "tags": tags})
            assert response.status_code == 200
            recipes.append(response.json())
        yield client, recipes
    db_path.unlink()


@pytest.mark.parametrize("tag", ["breakfast", "BREAKFAST", " breakfast\t"])
def test_matching_tag_returns_only_matching_recipes(recipe_catalog, tag):
    client, recipes = recipe_catalog
    response = client.get("/recipes", params={"tag": tag})

    assert response.status_code == 200
    assert response.json() == recipes[:2]


@pytest.mark.parametrize("tag", ["fast", "dinner"])
def test_no_exact_tag_match_returns_empty_list(recipe_catalog, tag):
    client, _ = recipe_catalog
    response = client.get("/recipes", params={"tag": tag})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("params", [{}, {"tag": ""}, {"tag": " \t "}])
def test_omitted_or_blank_tag_returns_all_recipes(recipe_catalog, params):
    client, recipes = recipe_catalog
    response = client.get("/recipes", params=params)

    assert response.status_code == 200
    assert response.json() == recipes
