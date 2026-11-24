# Critic Review — Round 3

Reviewed commit `e00cba69` on `task-c-scaling`.

## Verdict: REVISE

The malformed-range handling still changes ingredients that the README says should be preserved verbatim.

## Round 2 Verification

1. **Malformed numeric tokens — partially resolved.** All four original failures now pass, including `1-2/ cup`. The upper-end check still skips malformed tokens that begin with a slash or repeated dots. At factor 2, `1-/2 cup` becomes `2-/2 cup` and `1-..5 cups` becomes `2-..5 cups`. The parser should preserve both strings while continuing to scale `1-inch ginger` to `2-inch ginger`.
2. **Positive quantities underflowing to zero — resolved.** Both Round 2 cases now produce the expected positive decimals, including the fraction with a 310-digit denominator.
3. **Significant digits lost in formatting — resolved.** `12345678901 g` stays exact at factor 1 and yields `24691357802 g` at factor 2. Tests also cover long decimals and a 400-digit integer.
4. **Shared scaling test database — resolved.** The scaling route fixture initializes a fresh SQLite file under `tmp_path` for each test. The isolation test confirms the configured path and empty starting state.
5. **Missing boundary regressions — resolved for the listed cases.** Tests cover the original malformed and precision examples, attached units, hyphenated descriptors, package sizes, leading-dot decimals, fraction ranges, true zeros, and the saffron example. The remaining malformed range cases need their own coverage.

## Final Rubric Check

- **Correctness & Edge Cases.** Unknown IDs return 404. Factor validation returns 422 for missing, invalid, non-finite, and out-of-range values, with inclusive bounds of 0.001 and 1000. Scaling leaves SQLite data unchanged and preserves metadata, the documented factor, whitespace, and nonnumeric ingredients. Integers, decimals, fractions, mixed numbers, and both endpoints of valid ranges scale cleanly. Malformed upper endpoints remain the blocking edge case.
- **Tests.** The dedicated scaling suite covers all listed rubric scenarios, including an empty ingredient list. The requested `pytest -v` run passed all 119 tests with one Starlette TestClient deprecation warning.
- **Clarity & Structure.** Helpers handle parsing, arithmetic, and formatting. The route reuses the existing recipe lookup and its 404 error, and FastAPI provides the factor validation errors.
