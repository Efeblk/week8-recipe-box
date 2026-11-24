# Week 8 — Agent Orchestration: The Recipe Box Sprint

- **Repository:** https://github.com/Efeblk/week8-recipe-box
- **Orchestrator / Coordinator:** Antigravity (Gemini 4 Neon) in T3 Code
- **Concurrent Worker Agents (Part I):**
  - **Agent A (`task-a`, Shopping List):** Claude Sonnet 5.5 (`claudeAgent`)
  - **Agent B (`task-b`, Tag Filter):** Codex GPT-6.2 Sol (`codex`)
- **Generator–Critic Agents (Part II, Task 3 — Ingredient Scaling):**
  - **Generator:** Claude Sonnet 5.5 (Rounds 1–3) + Coordinator supervisor fix (Round 4)
  - **Critic:** Codex GPT-6.2 Sol (fresh isolated review run per round, Rounds 1–4)
- **Final Test Suite on `main` (`367dd4d`):** **119 passed, 0 failed** (`test_main.py`: 3, `test_shopping_list.py`: 31, `test_tag_filter.py`: 8, `test_scaling.py`: 77)

---

## Part I — Concurrent Agents (Git Worktrees)

### Tasks Selected (from `docs/TASKS.md`)
1. **Task 1 — Shopping list (`task-a`):** `GET /shopping-list?ids=1,2,3` merges ingredients across requested recipes in order with case-insensitive deduplication, strict 400 validation for malformed/empty IDs, and 404 listing missing recipe IDs.
2. **Task 2 — Tag filter (`task-b`):** `GET /recipes?tag=breakfast` filters recipes by exact, case-insensitive tag match (trimming whitespace and rejecting substring false positives like `fast` matching `breakfast`), while keeping omitted/blank `tag` backward-compatible.

### Worktree Setup & Parallel Execution
From `week8-recipe-box` (`3ef27f1`), two isolated worktrees were created before launching both agents simultaneously:

```bash
git worktree add ../recipe-task-a -b task-a
git worktree add ../recipe-task-b -b task-b
```

Both agents were dispatched in parallel at `00:09:42`:
- **Agent A** finished at `00:10:26` — commit [`8d632d2`](https://github.com/Efeblk/week8-recipe-box/commit/8d632d2) on `task-a` (`main.py` + `test_shopping_list.py`; 34/34 tests passing).
- **Agent B** finished at `00:10:34` — commit [`9c4feaf`](https://github.com/Efeblk/week8-recipe-box/commit/9c4feaf) on `task-b` (`main.py` + `test_tag_filter.py`; 11/11 tests passing).

### Collision Prevention, Merge Outcome & Remaining Risks
- **How collisions were avoided:**
  1. **Filesystem & branch isolation:** Each agent worked exclusively in its own git worktree (`../recipe-task-a` vs. `../recipe-task-b`), preventing dirty working-tree clashes and index locks.
  2. **Scoped edit regions & separate test files:** Agent A was scoped to append `_parse_recipe_ids` and `/shopping-list` at the bottom of `main.py` and create `test_shopping_list.py`; Agent B was scoped strictly to `list_recipes` in `main.py` and `test_tag_filter.py`. Neither touched `test_main.py`.
- **Merge outcome:** Merging both branches via `git merge --no-ff task-a` (`5221a7e`) and `git merge --no-ff task-b` (`803d24a`) succeeded via Git's `ort` auto-merge with **zero merge conflicts**, and the combined suite immediately passed **42/42 tests**.
- **Concurrency risks observed / mitigated:**
  - *Shared SQLite file during tests:* Because `main.py` defaults to `recipes.db` next to the script, running two test suites in the same directory would race on SQLite. Separate worktrees gave each agent its own local `recipes.db`, and later in Part II the Critic flagged shared-DB test coupling inside `test_scaling.py`, leading us to isolate scaling route tests with `tmp_path`.
  - *Shared `main.py` surface:* Even with region scoping, both agents edited `main.py`; had both modified top-level imports or added helper functions at the exact same line, manual conflict resolution would have been required.

---

## Part II — Generator–Critic Loop (Task 3: Ingredient Scaling)

Branch `task-c-scaling` was branched from the merged `main` (`803d24a`) in worktree `../recipe-task-c`. Before Round 1, the Coordinator committed [`reviews/RUBRIC.md`](reviews/RUBRIC.md) (`87d235c`) defining correctness, edge-case, test, and clarity criteria. To keep Round 1 realistic, the Round 1 Generator received only the brief from `docs/TASKS.md` (not the rubric), while each Critic pass ran as a fresh, read-only Codex session auditing the diff strictly against `reviews/RUBRIC.md`.

### Transcript Summary (4 Rounds → Sign-Off)

#### Round 1
- **Generator (`c91ffad`, Claude Sonnet 5.5):** Implemented `GET /recipes/{recipe_id}/scaled?factor=<float>` with `_scale_ingredient` handling integers, decimals, fractions, mixed numbers, attached units (`200g`), 404 for unknown IDs, and `Query(gt=0, allow_inf_nan=False)`. Added 22 tests in `test_scaling.py` (**59 passed**).
- **Critic (`d1fa0c5`, Codex GPT-6.2 Sol) — Verdict: `REVISE`** ([`reviews/round-1-critique.md`](reviews/round-1-critique.md)):
  1. **Extreme factor crash:** `?factor=1e308` on `"200 g flour"` overflowed and returned **HTTP 500**; `1001` and `1e-5` returned 200 instead of 422.
  2. **Broken ranges:** `"2-3 eggs"` × `2` produced `"4-3 eggs"` and `"1–2 cloves"` × `2` produced `"2–2 cloves"` (only first endpoint scaled).
  3. **Precision / zero-rounding:** `"1/2 cup"` × `0.001` rounded to `"0 cup"` (expected `"0.0005 cup"`), and `"12345.67 g"` × `1` truncated to `"12345.7 g"`.
  4. **Zero-denominator fractions:** `"1/0 cup"` × `2` silently became `"0 cup"` instead of staying verbatim.
  5. **Undocumented `factor` field** in response.
  6. **Missing tests** for ranges, out-of-bounds factors, empty stored ingredient list, and verifying success in the immutability test.

#### Round 2
- **Generator (`ea131e2`, Claude Sonnet 5.5):** Enforced inclusive bounds `0.001 <= factor <= 1000`, added range parsing (`-`, `–`, `—`, including mixed-number ranges), switched formatting to 10-sig-fig `Decimal` plain notation, rejected zero-denominator fractions, documented the response in docstrings and `README.md`, and expanded `test_scaling.py` (**89 passed**).
- **Critic (`c007fd5`, Codex GPT-6.2 Sol) — Verdict: `REVISE`** ([`reviews/round-2-critique.md`](reviews/round-2-critique.md)):
  - Confirmed all 6 Round 1 items fixed, then uncovered **5 deeper edge-case defects**:
  1. **Malformed tokens partially rewritten:** `"1/2/3 cup"` × `2` became `"1/3 cup"`, `"1.2.3 g"` became `"2.4.3 g"`, `"1/ cup"` became `"2/ cup"`, and `"1-2/ cup"` became `"2-4/ cup"`.
  2. **Tiny positive underflow to zero:** `"0." + "0"*322 + "1 g"` × `0.001` and `"1/1" + "0"*309 + " cup"` × `2` underflowed in float math to `0`.
  3. **Exact integer precision loss:** `"12345678901 g"` × `1` turned into `"12345678900 g"` due to unconditional 10-digit formatting.
  4. **Shared SQLite database in route tests:** `test_scaling.py` used the default `recipes.db`, making fixed-ID 404 tests stateful.
  5. **Missing boundary regressions** for hyphenated descriptors (`1-inch ginger`, `2 8-oz cans tomatoes`), leading-dot decimals (`.5 tsp salt`), fraction ranges (`1/2-3/4 cup milk`), and true zeros.

#### Round 3
- **Generator (`e00cba6`, Claude Sonnet 5.5):** Replaced the prefix regex with full numeric-run token validation (`_read_number`), switched all scaling arithmetic to exact `Decimal` (applying 10-digit display rounding only when `Inexact` is raised, e.g., `1/3`), added a `tmp_path` SQLite fixture in `test_scaling.py`, and added all requested regressions (**119 passed**).
- **Critic (`b3d348c`, Codex GPT-6.2 Sol) — Verdict: `REVISE`** ([`reviews/round-3-signoff.md`](reviews/round-3-signoff.md)):
  - Confirmed 4 of 5 Round 2 findings fully resolved, but caught one remaining malformed-range bug: because the range check looked for `_NUMBER_START_RE` (`[0-9]|\.[0-9]`) instead of `_TOKEN_RE` (`[0-9./]+`), `"1-/2 cup"` × `2` became `"2-/2 cup"` and `"1-..5 cups"` × `2` became `"2-..5 cups"` instead of staying verbatim.

#### Round 4 (Sign-Off)
- **Generator / Supervisor (`176eb99`):** Changed the range upper-endpoint trigger in `_scale_ingredient` from `_NUMBER_START_RE` to `_TOKEN_RE` so any slash- or dot-prefixed malformed upper endpoint is validated and causes the ingredient to stay verbatim while hyphenated text (`1-inch ginger`) still scales to `2-inch ginger`. Added both cases to `test_scale_route_exact_and_malformed` (**119 passed**).
- **Critic (`ae35ab0`, Codex GPT-6.2 Sol) — Verdict: `SIGN-OFF`** ([`reviews/round-4-signoff.md`](reviews/round-4-signoff.md)):
  - Verified `"1-/2 cup"` and `"1-..5 cups"` stay verbatim, `"1-inch ginger"` scales to `"2-inch ginger"`, all **119/119 tests pass**, and every rubric criterion (Correctness & Edge Cases, Tests, Clarity & Structure) passes.

Merged `task-c-scaling` cleanly into `main` (`367dd4d`), verified **119/119 tests pass** on `main`.

---

## Autonomy Levels & Supervision

| Agent Role | Allowed Autonomy | Supervision / Guardrails |
|---|---|---|
| **Part I Workers (`task-a`, `task-b`)** | Autonomous read/edit/test/commit **strictly inside their own git worktree** and branch. | Forbidden from touching files outside their worktree, modifying `test_main.py`, merging, or pushing. Coordinator verified both commits, performed `--no-ff` merges, and ran the combined test suite on `main`. |
| **Part II Generator (Claude)** | Autonomous implementation, refactoring, pytest execution, and local commits on `task-c-scaling`. | Could not edit `reviews/` or push/merge; Round 1 intentionally withheld `RUBRIC.md` so the Critic acted as an independent check; each revision round had to address every Critic finding with regression tests. |
| **Part II Critic (Codex)** | Read-only access to code/tests/git diffs plus read-only Python probe commands; write access **only** to `reviews/round-N-*.md` and committing that review file. | Fresh session per round (no shared memory with the Generator) to prevent rubber-stamping; prohibited from editing application code or tests. |
| **Coordinator (Gemini 4 Neon)** | Owned git worktree lifecycle, rubric authoring, task scoping, small final 1-line fix (`176eb99`), branch merges, GitHub publishing, and PR submission. | Verified test results after every merge and enforced Critic sign-off before landing `task-c-scaling`. |

---

## What I Learned

Orchestrating multiple agents showed me that git worktrees plus strict file-region scoping make parallel work genuinely fast and conflict-free—Agents A and B finished within eight seconds of each other and auto-merged cleanly—yet isolation alone does not guarantee edge-case correctness. Running a cross-model generator–critic loop with a fresh Codex reviewer against Claude's implementation proved far more valuable than self-review: even though the Generator's tests were green at 59, 89, and 119 tests, the adversarial Critic uncovered real bugs in three consecutive rounds (`1e308` HTTP 500s, broken ranges, `"1/2/3 cup"` mutating into `"1/3 cup"`, float underflow, and `"1-/2 cup"` partial rewrites). The biggest practical lesson is that orchestration succeeds when each agent has narrow, non-overlapping authority—workers edit in isolated worktrees, critics stay read-only against a written rubric, and the coordinator gates every merge on verified tests and explicit sign-off.
