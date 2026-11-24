# Critic Review — Round 1

Reviewed commit `c91ffad` on `task-c-scaling`.

## Verdict: REVISE

## Findings

1. **Correctness & Edge Cases — Factor bounds.** Scaling `"200 g flour"` by `1e308` returns HTTP 500. Scaling `"1 egg"` by `1001` or `1e-5` returns HTTP 200. All three should return 400 or 422 under the rubric’s suggested bounds. Enforce finite lower and upper bounds at query validation.
2. **Correctness & Edge Cases — Ranges.** At factor `2`, `"2-3 eggs"` becomes `"4-3 eggs"` (expected `"4-6 eggs"`), and `"1–2 cloves"` becomes `"2–2 cloves"` (expected `"2–4 cloves"`). Parse and scale both endpoints while preserving the delimiter and suffix.
3. **Correctness & Edge Cases — Precision.** At factor `0.001`, `"1/2 cup"` becomes `"0 cup"` (expected `"0.0005 cup"`). At factor `1`, `"12345.67 g"` becomes `"12345.7 g"` (expected `"12345.67 g"`) because the default general format limits significant digits. Preserve enough precision for positive results and trim trailing zeros.
4. **Correctness & Edge Cases — Malformed fractions.** At factor `2`, `"1/0 cup"` returns HTTP 200 with `"0 cup"`. The rubric leaves malformed fractions unspecified. Preserve `"1/0 cup"` verbatim so a stored invalid quantity does not silently become zero.
5. **Correctness & Edge Cases — Response documentation.** A request with `?factor=2` returns a top-level `"factor": 2.0`. The task docs show the query parameter but omit the response field. Document the response field if retained.
6. **Tests — Missing rubric cases.** Add assertions for both range delimiters, HTTP 400 or 422 for extreme factors at both ends, and HTTP 200 with `ingredients: []` for an empty stored list. The current `""` helper case covers an empty string. Add regressions for the precision and malformed-fraction examples above, and assert that the scaled request succeeds in the immutability test so a failed request cannot satisfy it.

## What Passed

- Unknown IDs return HTTP 404 with `"unknown recipe"`, consistent with the ordinary GET. Validation rejects zero, negatives, NaN, and both infinities with clear HTTP 422 messages.
- Scaling leaves the stored SQLite recipe unchanged and preserves `id`, `title`, and `tags`. An empty ingredient list returns HTTP 200 with an empty list.
- Integers, attached units, ordinary decimals, simple fractions, and whole mixed quantities scale correctly on the covered cases. Leading whitespace and non-numeric text survive unchanged. Whole numbers omit `.0`, and `"0.1 cup"` at factor `3` yields `"0.3 cup"`.
- Readable parsing, formatting, and ingredient helpers keep the route short. The dedicated suite covers basic success, 404, immutability, invalid input, and the core single-quantity formats. All 59 tests passed against temporary SQLite storage. The run emitted an anyio assertion-rewrite warning from the test harness and a Starlette TestClient deprecation warning.
