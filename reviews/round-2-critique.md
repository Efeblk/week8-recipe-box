# Critic Review — Round 2

Reviewed commit `ea131e2` on `task-c-scaling`.

## Verdict: REVISE

## Round 1 Verification

1. **Factor bounds.** `1e308`, `1001`, and `1e-5` return HTTP 422. The suite also verifies rejection of zero, negatives, NaN, both infinities, and missing factors, and acceptance of both inclusive bounds.
2. **Ranges.** At factor 2, `2-3 eggs` yields `4-6 eggs` and `1–2 cloves garlic` yields `2–4 cloves garlic`. Both endpoints scale and the delimiter survives.
3. **Precision.** The reported regressions pass. `1/2 cup` at factor 0.001 yields `0.0005 cup`, and `12345.67 g` at factor 1 stays exact. Other precision failures remain below.
4. **Zero denominators.** `1/0 cup` stays unchanged at factor 2, as do the covered mixed-number and range variants. The broader malformed-input guarantee still fails for partial matches.
5. **Response documentation.** The README and route docstring describe the top-level `factor`. The metadata test verifies the complete response.
6. **Missing rubric tests.** Added coverage for both reported dash variants, extreme factors, an empty stored list, precision, and zero denominators. The immutability test now checks that scaling succeeds and returns the expected result before reading the original.

## New / Remaining Findings

1. **Malformed numeric tokens are partially scaled and can become valid but incorrect quantities.** At factor 2, `1/2/3 cup` becomes `1/3 cup`, `1.2.3 g` becomes `2.4.3 g`, `1/ cup` becomes `2/ cup`, and `1-2/ cup` becomes `2-4/ cup`. Each should be preserved verbatim under the README contract. The regex accepts a valid numeric prefix and passes its leftover punctuation through as suffix text. The route reproduces the first case with HTTP 200. Directly calling `_parse_quantity("1/2/3")` would raise `ValueError` from unpacking, despite the helper's documented malformed-input return value. Validate the full numeric token including either range endpoint, while continuing to accept attached units and hyphenated descriptors.
2. **Positive finite quantities can become zero.** For `"0." + "0" * 322 + "1 g"` at factor 0.001, the result is `0 g`. The expected decimal result is `"0." + "0" * 325 + "1 g"`. The parsed float is positive, but multiplication underflows before formatting, and zero passes the finite check. For `"1/" + "1" + "0" * 309 + " cup"` at factor 2, the result is `0 cup` because the denominator converts to infinity before division. The exact result is `"0." + "0" * 308 + "2 cup"`. Preserve positive representable results using arithmetic suited to the input, or preserve the original when scaling cannot be represented safely.
3. **Formatting drops significant digits from exact quantities.** `12345678901 g` at factor 1 becomes `12345678900 g`. The float represents the original integer exactly. The ten-significant-digit formatting step introduces the change. Preserve exact integer results and add a regression beyond ten significant digits.
4. **Route tests share the default application database.** A normal test run uses `main.DB_PATH` next to the source unless the runner overrides it. POSTs accumulate, including setup for rejected-factor tests. The fixed missing-ID test can return 200 if row 99999 already exists, as confirmed by seeding that ID in memory. Use a fresh temporary database for the scaling route tests, following the existing tag-filter fixture pattern.
5. **Missing regressions around numeric token boundaries.** Add cases for the defects above and for currently passing examples that constrain the fix. At factor 2, `1-inch ginger` yields `2-inch ginger`, `2 8-oz cans tomatoes` yields `4 8-oz cans tomatoes`, `1 12-oz can beans` yields `2 12-oz can beans`, and `.5 tsp salt` yields `1 tsp salt`. Fraction ranges `1/2-3/4 cup milk` and `1/2 - 1 cup milk` yield `1-1.5 cup milk` and `1 - 2 cup milk`. True zeros remain zero. The already-covered small-quantity behavior also holds for `0.0001 g saffron` at factor 0.001, which yields `0.0000001 g saffron`.

All 89 tests passed with temporary SQLite storage. The run emitted an anyio assertion-rewrite warning and a Starlette TestClient deprecation warning.
