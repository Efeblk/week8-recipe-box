# Generator–Critic Review Rubric — Task 3: Ingredient Scaling

Endpoint: `GET /recipes/{recipe_id}/scaled?factor=<float>`

## 1. Correctness & Edge Cases
- Returns HTTP `404` for an unknown `recipe_id`.
- Does **not** mutate the stored recipe in SQLite (original `GET /recipes/{id}` stays unchanged).
- Validates `factor`: rejects non-positive (`<= 0`), `NaN`, `inf`, `-inf`, and extreme/absurd values (e.g., enforce sensible bounds such as `0.001 <= factor <= 1000`, returning HTTP `400` or `422`).
- Scales leading quantities accurately across common real-world ingredient formats:
  - Integers and decimals with space or attached units (e.g., `"200 g flour"`, `"200g flour"`, `"1.5 tbsp oil"`).
  - Simple fractions and mixed numbers (e.g., `"1/2 cup milk"`, `"1 1/2 cups sugar"` — must scale the *whole* mixed quantity, NOT just `"1"`!).
  - Numeric ranges (e.g., `"2-3 eggs"`, `"1–2 cloves garlic"` — must scale *both* ends of the range).
  - Preserves leading whitespace or normalizes cleanly without corrupting non-numeric ingredients (e.g., `"salt to taste"`, `"a pinch of pepper"` stay unchanged).
  - Formats scaled numbers cleanly (no noisy `2.0` for whole numbers or floating-point artifacts like `0.30000000000000004`, and never rounds small positive quantities down to `0`).
- Preserves recipe metadata (`id`, `title`, `tags`) and includes the scaled `ingredients` (plus `factor` if helpful and documented).

## 2. Tests
- Dedicated `test_scaling.py` covering happy paths, unknown recipe 404, DB immutability, invalid/out-of-bounds factors, decimals, fractions, mixed numbers, ranges, attached units, non-numeric ingredients, and empty ingredient lists.
- All existing and new `pytest` tests pass cleanly.

## 3. Clarity & Structure
- Scaling logic is factored into clean, readable helper function(s) rather than crammed into the route handler.
- Error messages are clear and consistent with the rest of `main.py`.