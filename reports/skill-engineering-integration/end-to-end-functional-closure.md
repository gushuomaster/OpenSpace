# End-to-End Skill Workflow Functional Closure

**Date:** 2026-10-08

**Branch:** `codex/e2e-skill-functional-closure`

**Scope:** OpenSpace managed Candidate visibility, explicit Cloud continuation, interrupted-install recovery, and install-to-runtime reuse.
**Result:** Functional closure and explicit continuation protocol are verified. Task-level automatic replay is not implemented or claimed.

## Outcome

| Milestone | Result | Evidence boundary |
|---|---:|---|
| `LOCAL_MISS_CONTINUATION_AVAILABLE` | YES | A real zero-result local discovery returns the structured continuation. It is not inferred from `skills_used=[]`. |
| `CLOUD_DISCOVERY_EXECUTED` | YES | The MCP Cloud search and `OpenSpaceClient.search_skills` execute against a deterministic transport response. |
| `CODEX_SELECTION_COMPLETED` | YES | The explicitly selected returned `cloud_skill_id` is supplied to acquisition. No first-result auto-selection exists. |
| `CANDIDATE_INSTALLED` | YES | Real Acquisition, quarantine, skill-engineering inspection/validation, Codex semantic confirmation, candidate-bound receipt verification, and install reach persisted `INSTALLED`. |
| `TASK_RESUMED_WITH_SKILL` | YES — explicit continuation only | Fresh Registry/SkillStore objects discover the installed Candidate; ordinary local lookup and `SkillTool` deliver the exact installed marker. |
| Task-level automatic closure | NO | Neither local miss nor `execute_task` automatically chooses, installs, or replays the original task. |

The E2E replaces only external HTTP transport with deterministic Cloud search and bundle fixtures. Candidate acquisition, Governance, Codex confirmation, install, persisted state, fresh runtime primitives, local lookup, and `SkillTool` are real implementation paths. The restart proof recreates Registry and SkillStore objects; it is not a second operating-system process and does not prove autonomous replay.

## Implemented closure

### Managed-artifact visibility

- Quarantine, inspection-only packages, malformed managed markers, corrupt/ambiguous records, and every non-`INSTALLED` Candidate fail closed.
- A formally installed Candidate is admitted only when Candidate identity, manifest, Governance binding, receipt digest, installed path, and installed bytes agree.
- The shared admission is applied to canonical startup discovery, Registry discovery/registration, MCP host-directory auto-registration, and `fix_skill` before Registry/SkillStore mutation.
- Ordinary valid Local Skills retain the prior default behavior.
- No second Governance pipeline or registration-time Governance call was added.

### Explicit continuation semantics

- A proven local miss exposes `next_action=cloud_skill_discovery` and `LOCAL_MISS_CONTINUATION_AVAILABLE`.
- Cloud execution, Codex selection, Candidate install, and subsequent Skill use are separately observed milestones.
- `execute_task` retains its original task result and does not treat `skills_used=[]` as proof that Cloud is needed.

### Interrupted-install recovery

A real subprocess kill immediately after formal placement exited with code 91 and left the formal path present while Candidate state remained `INSTALLING`. This justified the minimum recovery consumer.

Startup reconciliation:

- enumerates only persisted `INSTALLING` Candidates;
- revalidates Candidate identity, manifest, formal ownership, payload digest, Governance binding, receipt digest, and installed bytes;
- replays existing idempotent Store/mapping/Registry operations;
- preserves foreign Candidate and Local Skill assets using exact ID/path ownership checks;
- produces `INSTALL_FAILED` or `INTEGRITY_MISMATCH` on non-recoverable mismatch;
- keeps `INSTALLING` across replay interruptions;
- aborts startup if an exception occurs after terminal state write but visibility cannot be confirmed;
- rejects an inactive same-ID SkillStore record rather than publishing inconsistent Registry/Store state.

No journal, generic transaction/recovery framework, background worker, public Governance platform, or Agent autonomy layer was added.

## Verification evidence

All commands used UTF-8 mode. The unified task environment installed `skill-engineering` from the declared immutable VCS revision `0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c`; PEP 610 recorded that exact commit. The pinned wheel omits `config/gate-policy.yaml`, so the task environment received an exact byte-for-byte copy from the same commit for Governance execution. This is an environment accommodation, not a repository or packaging change.

| Verification | Result |
|---|---:|
| Candidate recovery/install/visibility focused | 41 passed, 1 skipped |
| Explicit Candidate-to-runtime E2E | 2 passed |
| Candidate/Evolution focused integration | 35 passed |
| Complete OpenSpace `tests/cloud` | 84 passed, 1 skipped |
| Complete OpenSpace `tests/skill_engine` | 79 passed |
| Complete OpenSpace `tests` | 191 passed, 2 skipped |
| Fixed-revision skill-engineering `tests/unit` | 300 passed, 2 skipped |
| `skill-discovery` validator | PASS |
| `delegate-task` validator | PASS |
| `skill-engineer` validator | PASS |
| `git diff --check` | PASS |

All skips are Windows symlink tests blocked by `WinError 1314` (the current process lacks symlink privilege). There were no xfails, collection errors, or remaining test failures in the final runs.

## Invariant status

```text
UNMANAGED_REMOTE_CONTENT_VISIBLE = NO
QUARANTINE_VISIBLE = NO
INSPECTION_ONLY_VISIBLE = NO
NON_PASS_CANDIDATE_INSTALLABLE = NO
TAMPERED_CANDIDATE_INSTALLABLE = NO
GOVERNANCE_BYPASS_PATHS = 0 for the audited formal visibility entrypoints
LOCAL_SKILL_REUSE_COMPLETE = YES
INSTALL_TO_RUNTIME_REUSE_VERIFIED = YES
RUNTIME_DEPENDENCY_ALIGNED = YES
EVOLUTION_GOVERNANCE_PRESERVED = YES
USER_CHANGES_PRESERVED = YES
TASK_LEVEL_AUTOMATIC_REPLAY = NO / NOT IMPLEMENTED
```

## Boundaries and remaining work

- The evidence supports functional completion plus an explicit Host/MCP continuation protocol, not autonomous task-level closure.
- The known fixed-revision wheel package-data omission remains a dependency packaging observation. This phase did not expand into a skill-engineering release or packaging migration.
- The original OpenSpace checkout remains on `codex/integrate-skill-engineering` with the same four pre-existing modified files; this work did not modify them.
- No merge, push, PR, release, repository integration, or historical-complexity cleanup was performed.
