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
import re
import sqlite3
from contextlib import closing
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, Inexact
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

# Quantities are parsed as whole tokens and computed with exact Decimal arithmetic, so there is
# no float rounding, overflow or underflow. ASCII digits only; lookalike Unicode digits are left alone.
_LEAD_RE = re.compile(r"\s*")
_SEPARATOR_RE = re.compile(r"\s*[-–—]\s*")  # range delimiter: hyphen, en dash or em dash
_NUMBER_START_RE = re.compile(r"[0-9]|\.[0-9]")
_TOKEN_RE = re.compile(r"[0-9./]+")  # a maximal run of numeric characters
_INTEGER_RE = re.compile(r"[0-9]+")
_DECIMAL_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?|\.[0-9]+")
_FRACTION_RE = re.compile(r"([0-9]+)/([0-9]+)")
_WHITESPACE_RE = re.compile(r"\s+")

# Results that are not exact (e.g. 1/3) are shown with this many significant digits.
_DISPLAY_CONTEXT = Context(prec=10, Emin=MIN_EMIN, Emax=MAX_EMAX, traps=[])


def _read_fraction(token: str, context: Context) -> Decimal:
    """Parse 'n/d'; ValueError if the token is not exactly that or the denominator is zero."""
    match = _FRACTION_RE.fullmatch(token)
    if match is None:
        raise ValueError(f"malformed fraction {token!r}")
    denominator = Decimal(match[2])
    if denominator == 0:
        raise ValueError(f"zero denominator in {token!r}")
    return context.divide(Decimal(match[1]), denominator)


def _read_number(text: str, pos: int, context: Context) -> tuple[Decimal, int]:
    """Read one quantity at `pos`: integer, decimal ('.5'), fraction ('1/2') or mixed ('1 1/2').

    Returns the exact value and the end position. The whole numeric token must be valid:
    anything malformed ('1/2/3', '1.2.3', '1/', '1/0') raises ValueError.
    """
    match = _TOKEN_RE.match(text, pos)
    if match is None:
        raise ValueError("no number")
    token, end = match[0], match.end()
    if "/" in token:
        return _read_fraction(token, context), end
    if _INTEGER_RE.fullmatch(token):
        # Mixed number: whole part, whitespace, then a fraction-looking token.
        space = _WHITESPACE_RE.match(text, end)
        if space is not None:
            tail = _TOKEN_RE.match(text, space.end())
            if tail is not None and "/" in tail[0]:
                fraction = _read_fraction(tail[0], context)
                return context.add(Decimal(token), fraction), tail.end()
        return Decimal(token), end
    if _DECIMAL_RE.fullmatch(token):
        return Decimal(token), end
    raise ValueError(f"malformed number {token!r}")


def _format_quantity(value: Decimal, exact: bool) -> str:
    """Render without exponent or trailing zeros. Inexact values are rounded for display."""
    if not exact:
        value = _DISPLAY_CONTEXT.plus(value)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _scale_number(text: str, pos: int, factor: Decimal, context: Context) -> tuple[str, int]:
    """Read the quantity at `pos`, multiply it by `factor` and format it. Raises ValueError."""
    context.clear_flags()
    value, end = _read_number(text, pos, context)
    scaled = context.multiply(value, factor)
    return _format_quantity(scaled, exact=not context.flags[Inexact]), end


def _scale_ingredient(ingredient: str, factor: float) -> str:
    """Scale the leading quantity (or range) of an ingredient, e.g. '2-3 eggs' -> '4-6 eggs'.

    Ingredients without a leading quantity, or with a malformed one such as '1/0 cup',
    '1/2/3 cup' or '1.2.3 g', are returned unchanged. Attached units ('200g') and hyphenated
    descriptors ('1-inch ginger', '2 8-oz cans') are preserved as suffix text.
    """
    lead = _LEAD_RE.match(ingredient).end()
    if _NUMBER_START_RE.match(ingredient, lead) is None:
        return ingredient
    factor_text = repr(factor)
    factor_decimal = Decimal(factor_text)
    # Enough digits that every product is exact; only divisions (fractions) can round.
    context = Context(
        prec=len(ingredient) + len(factor_text) + 60, Emin=MIN_EMIN, Emax=MAX_EMAX, traps=[]
    )
    try:
        quantity, end = _scale_number(ingredient, lead, factor_decimal, context)
        separator = _SEPARATOR_RE.match(ingredient, end)
        if separator is not None and _NUMBER_START_RE.match(ingredient, separator.end()):
            upper, end = _scale_number(ingredient, separator.end(), factor_decimal, context)
            quantity = f"{quantity}{separator[0]}{upper}"
    except ValueError:
        return ingredient
    return f"{ingredient[:lead]}{quantity}{ingredient[end:]}"


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
