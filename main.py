"""Recipe Box — starter app for Week 8.

A tiny FastAPI service for recipes and tags, with a static frontend. Use it as the
playground for concurrent multi-agent work and a generator-critic loop.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload
    # open http://localhost:8000/
Test:
    pytest
"""
import json
import math
import re
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
DB_PATH = BASE / "recipes.db"

app = FastAPI(title="Recipe Box")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                ingredients TEXT NOT NULL,  -- JSON list of strings
                tags        TEXT NOT NULL   -- JSON list of strings
            )"""
        )
        conn.commit()


init_db()


class RecipeIn(BaseModel):
    title: str
    ingredients: list[str] = []
    tags: list[str] = []


def _row_to_recipe(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "ingredients": json.loads(row["ingredients"]),
        "tags": json.loads(row["tags"]),
    }


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.post("/recipes")
def create_recipe(recipe: RecipeIn):
    with closing(get_db()) as conn:
        cur = conn.execute(
            "INSERT INTO recipes (title, ingredients, tags) VALUES (?, ?, ?)",
            (recipe.title, json.dumps(recipe.ingredients), json.dumps(recipe.tags)),
        )
        conn.commit()
        rid = cur.lastrowid
    return {"id": rid, **recipe.model_dump()}


@app.get("/recipes")
def list_recipes(tag: str | None = None):
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY id").fetchall()
    recipes = [_row_to_recipe(row) for row in rows]
    normalized_tag = tag.strip().casefold() if tag is not None else ""
    if not normalized_tag:
        return recipes
    return [
        recipe
        for recipe in recipes
        if any(recipe_tag.strip().casefold() == normalized_tag for recipe_tag in recipe["tags"])
    ]


@app.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return _row_to_recipe(row)


# Scaling bounds, inclusive. Anything outside is rejected with HTTP 422 by query validation.
MIN_SCALE_FACTOR = 0.001
MAX_SCALE_FACTOR = 1000

# A single quantity: mixed number ("1 1/2"), fraction ("1/2") or decimal/integer ("200", "0.5", ".5").
# ASCII digits only, so lookalike Unicode digits are left alone.
_NUMBER = r"[0-9]+\s+[0-9]+/[0-9]+|[0-9]+/[0-9]+|[0-9]+(?:\.[0-9]+)?|\.[0-9]+"
# Leading quantity, optionally a range ("2-3", "1 – 2") with a hyphen, en dash or em dash.
_QUANTITY_RE = re.compile(
    rf"^(?P<lead>\s*)(?P<first>{_NUMBER})(?:(?P<sep>\s*[-–—]\s*)(?P<second>{_NUMBER}))?"
)


def _parse_quantity(text: str) -> float | None:
    """Parse '200', '0.5', '1/2' or '1 1/2' to a float; None if malformed (e.g. '1/0')."""
    total = 0.0
    for part in text.split():
        if "/" in part:
            num, den = part.split("/")
            if float(den) == 0:
                return None
            total += float(num) / float(den)
        else:
            total += float(part)
    return total


def _format_quantity(value: float) -> str:
    """Render without exponent, float noise or trailing zeros: 0.30000000000000004 -> '0.3'."""
    text = format(Decimal(f"{value:.10g}"), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _scale_quantity(text: str, factor: float) -> str | None:
    """Scale one quantity string and format it; None if it cannot be scaled safely."""
    quantity = _parse_quantity(text)
    if quantity is None:
        return None
    scaled = quantity * factor
    return _format_quantity(scaled) if math.isfinite(scaled) else None


def _scale_ingredient(ingredient: str, factor: float) -> str:
    """Scale the leading quantity (or range) of an ingredient, e.g. '2-3 eggs' -> '4-6 eggs'.

    Ingredients without a leading quantity, or with a malformed one such as '1/0 cup',
    are returned unchanged.
    """
    match = _QUANTITY_RE.match(ingredient)
    if match is None:
        return ingredient
    scaled = [_scale_quantity(match["first"], factor)]
    if match["second"] is not None:
        scaled.append(_scale_quantity(match["second"], factor))
    if None in scaled:
        return ingredient
    quantity = (match["sep"] or "").join(scaled)
    return f"{match['lead']}{quantity}{ingredient[match.end():]}"


@app.get("/recipes/{recipe_id}/scaled")
def get_scaled_recipe(
    recipe_id: int,
    factor: float = Query(ge=MIN_SCALE_FACTOR, le=MAX_SCALE_FACTOR, allow_inf_nan=False),
):
    """Return the recipe with leading ingredient quantities multiplied by `factor`.

    The response has the recipe fields (`id`, `title`, `ingredients`, `tags`) plus
    `factor`, the multiplier that was applied. The stored recipe is not modified.
    """
    recipe = get_recipe(recipe_id)
    recipe["ingredients"] = [_scale_ingredient(i, factor) for i in recipe["ingredients"]]
    return {**recipe, "factor": factor}


def _parse_recipe_ids(ids: str) -> list[int]:
    """Parse a comma-separated list of positive integers, de-duplicated in first-seen order."""
    if not ids.strip():
        raise HTTPException(
            status_code=400,
            detail="ids is required: provide comma-separated recipe ids, e.g. ids=1,2,3",
        )
    parsed: list[int] = []
    for token in ids.split(","):
        token = token.strip()
        if not (token.isascii() and token.isdigit()) or int(token) < 1:
            raise HTTPException(
                status_code=400,
                detail=f"invalid recipe id {token!r}: ids must be comma-separated positive integers",
            )
        value = int(token)
        if value not in parsed:
            parsed.append(value)
    return parsed


@app.get("/shopping-list")
def shopping_list(ids: str = ""):
    recipe_ids = _parse_recipe_ids(ids)
    placeholders = ",".join("?" for _ in recipe_ids)
    with closing(get_db()) as conn:
        rows = conn.execute(
            f"SELECT id, ingredients FROM recipes WHERE id IN ({placeholders})",
            recipe_ids,
        ).fetchall()
    by_id = {row["id"]: json.loads(row["ingredients"]) for row in rows}

    missing = [rid for rid in recipe_ids if rid not in by_id]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"unknown recipe id(s): {', '.join(str(m) for m in missing)}",
        )

    seen: set[str] = set()
    ingredients: list[str] = []
    for rid in recipe_ids:
        for item in by_id[rid]:
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                ingredients.append(cleaned)
    return {"recipe_ids": recipe_ids, "ingredients": ingredients}
