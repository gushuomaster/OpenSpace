# Release Closure Reproduction

## Immutable Revisions

| Component | Revision | Evidence |
|---|---|---|
| `skill-engineering` | `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c` | clean detached worktree; GitHub origin push verified |
| OpenSpace | `8a4c402308fbcd2df22d79cd08033837b73c36dd` | clean detached worktree |
| OpenSpace dependency pin | `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c` | `pyproject.toml` and installed `Requires-Dist` |
| Runtime loaded revision | `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c` | PEP 610 `direct_url.json` and `GovernanceEngine().engine_revision` |

The runtime engine loaded from `D:/project/openspace-pin-venv-0c83c8e/Lib/site-packages/engine`; it did not load either repository checkout. The installed wheel contains `schemas/provider-result.schema.json` and contract loading succeeds.

## Verification Matrix

| Check | Expected | Actual | Status |
|---|---|---|---|
| `skill-engineering` immutable SHA | fixed | `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c` | PASS |
| OpenSpace dependency pin | same SHA | same SHA | PASS |
| runtime imported SHA | same SHA | same SHA | PASS |
| clean checkout | yes | all three worktrees clean/detached | PASS |
| `skill-engineering` full suite | pass | `459 passed, 2 skipped` | PASS |
| Skill validation | valid | `Skill is valid!` | PASS |
| B1 pinned live | pass | declared `5`, verified `5`, missing `0`; Governance PASS; authorized | PASS |
| B2 pinned live | pass | KR-02/KR-03/KR-04 recovery PASS; no false pass/apply/stale replay | PASS |
| B3 pinned live | pass | PASS/BLOCKED/INCOMPLETE persisted in shadow; commits remain provisional | PASS |
| B4 pinned live | pass | MCP sessions, DB, dashboard and evolution gate consistent; revision matches pin | PASS |
| OpenSpace focused governance/runtime/cloud | pass | `88 passed` | PASS |
| OpenSpace non-benchmark | no new regression | `110 passed, 1 baseline failure` | PASS_WITH_BASELINE |
| Dashboard build | pass | clean `npm ci` + `npm run build` succeeded | PASS |
| Target Skill regression | no new regression | `263 passed, 1 skipped, 4 baseline failures`; parent has same four failures | PASS_WITH_BASELINE |

## Known Baselines

- `KNOWN_BASELINE_001`: OpenSpace `tests/grounding/core/permissions/test_loader_runtime_modes.py::test_bypass_mode_allows_ordinary_path_outside_workspace`; Windows maps `/etc/...` to `C:\etc\...`. It remains unchanged on the pinned commit.
- `KNOWN_BASELINE_002`: Target `tests/test_code_scope.py::test_scope_keeps_product_code_and_reports_non_product_roles`; fixture lacks `build/generated.c`. It fails identically on target parent `affc52a`.
- `KNOWN_BASELINE_003`: Target `tests/test_docx_assembly_depth.py::test_merged_cover_table_is_not_marked_as_repeating_header`; it fails identically on target parent `affc52a`.
- `KNOWN_BASELINE_004`: Target bootstrap tests expect a CPython license hash that differs from the installed local CPython asset; both fail identically on target parent `affc52a`.

No new regression is attributable to the release closure commits.
