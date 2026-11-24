# Starter — Recipe Box

A tiny FastAPI + SQLite service with a static frontend. Your playground for concurrent
agents and a generator–critic loop.

## Setup
```bash
pip install -r requirements.txt
pytest                      # 3 tests should pass
uvicorn main:app --reload   # http://localhost:8000  (UI at /, docs at /docs)
```

## Endpoints
- `POST /recipes` `{ "title": ..., "ingredients": [...], "tags": [...] }`
- `GET /recipes`, `GET /recipes/{id}`
- `GET /recipes/{id}/scaled?factor=2` — the recipe with leading ingredient quantities
  (integers, decimals, fractions, mixed numbers, ranges like `2-3`) multiplied by `factor`.
  `factor` must be between 0.001 and 1000 (otherwise `422`); unknown id is `404`.
  The response has `id`, `title`, `ingredients` (scaled), `tags`, and `factor` (the multiplier
  applied). Ingredients without a leading quantity, or with a malformed one like `1/0 cup`,
  are returned unchanged. The stored recipe is never modified.

## Parallel work with git worktrees
```bash
git worktree add ../recipe-task-a -b task-a
git worktree add ../recipe-task-b -b task-b
```

## Files
- `main.py` — the app
- `static/index.html` — minimal UI
- `test_main.py` — pytest suite
- `docs/TASKS.md` — independent tasks (safe to run in parallel)
