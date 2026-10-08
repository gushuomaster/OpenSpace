# End-to-End Skill Workflow Functional Closure Design

**Status:** Draft for review. The recommended approach was approved on 2026-10-08; implementation has not started.

**Scope:** OpenSpace runtime and its declared `skill-engineering` dependency contract. The existing Candidate lifecycle and Evolution Governance lifecycle remain authoritative and are not redesigned.

## 1. Goal

Close the remaining functional gaps between a user task and safe Skill reuse so the following workflow is executable, observable, and fail closed:

```text
User task
  -> local Skill discovery
  -> local hit: Codex loads and uses the installed Skill
  -> local miss: explicit Cloud discovery continuation
  -> Codex selects one exact Cloud Skill
  -> Acquisition -> Quarantine
  -> existing skill-engineering Governance
  -> real Codex semantic confirmation
  -> candidate-bound ManagedCompletionReceipt
  -> receipt/digest revalidation
  -> Install -> Registry / SkillStore
  -> restart -> local discovery -> SkillTool -> exact SKILL.md context
```

The closure must prove all of the following without creating a second Governance pipeline:

- managed remote content cannot become visible through hot registration or `fix_skill`;
- a local miss produces a durable, explicit Cloud continuation owned semantically by Codex;
- the controlled OpenSpace environment loads the declared `skill-engineering` contract;
- a process death during Candidate installation is reconciled from existing durable state;
- an installed Candidate is reusable through the ordinary runtime path after restart.

## 2. Preserved Architecture and Ownership

The official Candidate lifecycle stays unchanged:

```text
Discovery / explicit Codex selection
  -> Acquisition
  -> Quarantine
  -> skill-engineering Governance
  -> Codex semantic confirmation
  -> ManagedCompletionReceipt
  -> receipt/digest revalidation
  -> Install
  -> Registry / SkillStore
```

The existing Evolution lifecycle also stays unchanged:

```text
TriggerJob
  -> Decision / Admission
  -> staging authoring
  -> validation
  -> GovernanceAdapter
  -> GovernanceEngine
  -> commit-time integrity recheck
  -> apply
  -> Registry / SkillStore
```

Ownership remains:

| Concern | Owner |
|---|---|
| Semantic Cloud Skill selection | Codex |
| Candidate acquisition, state, install, registration, orchestration | OpenSpace |
| Engineering inspection, validation, Gate, managed completion | skill-engineering |
| Existing Skill evolution admission and apply | OpenSpace Evolution pipeline |

Candidate Governance will not be routed through `GovernanceAdapter`, and `import_skill` will remain acquisition-only. No LLM call or caller-authored PASS shortcut will be added to import or registration APIs.

## 3. Design Principles

1. `reuse existing primitive > minimal extension > new abstraction`.
2. Registration APIs perform admission only; they never run Governance.
3. Ordinary local Skills remain outside the Candidate lifecycle.
4. Managed Candidate identity is established from the existing manifest, canonical paths, state, and digests.
5. Local miss is a continuation, not an automatic choice or download.
6. Recovery replays existing idempotent/ownership-checked operations; it does not add a journal.
7. New fields and helpers exist only for a proven current invariant or test.

## 4. P0: Managed Artifact Visibility Admission

### 4.1 Root cause

Two MCP entrypoint paths currently reach Registry and SkillStore without distinguishing managed remote artifacts from arbitrary local Skills:

1. `_auto_register_skill_dirs()` calls `SkillRegistry.discover_from_dirs()` and then `SkillStore.sync_from_registry()`.
2. `fix_skill()` calls `SkillRegistry.register_skill_dir()` and then syncs the returned metadata.

Static Skill safety checks do not prove Candidate Governance or installation. Consequently a Candidate payload or inspection-only package can be parsed as a normal local Skill.

### 4.2 Narrow admission policy

Add a small managed-artifact visibility policy under `openspace.cloud`. It classifies one resolved Skill directory at the point immediately before general hot registration.

The policy returns an admission result containing only:

- `allowed: bool`;
- stable `code` for diagnostics/tests;
- optional `candidate_id`;
- concise `reason`.

It evaluates in this order:

1. Resolve the path without trusting caller spelling or symlinks.
2. If the path is inside `CandidateRepository.quarantine_root`, reject with `CANDIDATE_QUARANTINED`.
3. If the path or any ancestor carries `.cloud_package.json` with `inspection_only=true`, reject with `INSPECTION_ONLY_PACKAGE`.
4. Ask `CandidateRepository` whether the path is an intended or recorded formal path for a managed Candidate.
5. If it is managed, allow only when state is `INSTALLED` and `state.installed_path` resolves to the same directory. All other states reject with `CANDIDATE_NOT_INSTALLED`.
6. If no managed identity or inspection marker applies, allow it as an ordinary local Skill.

A malformed `.cloud_package.json` is rejected fail closed. The marker name is reserved for OpenSpace Cloud inspection artifacts; silently treating a corrupt marker as a local Skill would recreate the bypass.

An `INSTALLED` Candidate is not required to retain its original installation digest forever at this admission point. A later governed Evolution may legitimately change its bytes. Candidate digest and receipt checks remain mandatory at install time; subsequent Evolution integrity remains owned by the existing Evolution pipeline.

### 4.3 Candidate path resolution

Extend `CandidateRepository` minimally with read-only enumeration/path resolution:

- enumerate valid `candidate_*` records under the existing quarantine root;
- compute the intended formal path from the existing manifest in one authoritative helper;
- resolve a supplied Skill directory to zero or one Candidate record;
- surface corrupt or ambiguous managed state as an error, never as unmanaged content.

The installer will reuse the same formal-path helper, eliminating duplicate path construction. No index, database table, or new manifest field is added. Repository scanning is bounded to Candidate records already stored beneath one runtime state root.

### 4.4 Integration points

- `SkillRegistry.discover_from_dirs()` receives an optional per-entry admission callback. The default remains unchanged for existing internal consumers. `_auto_register_skill_dirs()` supplies the managed-artifact policy so a broad scan root can admit ordinary local Skills while rejecting nested managed artifacts individually.
- `fix_skill()` evaluates the exact `skill_dir` before `register_skill_dir()` and returns a stable fail-closed error without creating evidence, TriggerJobs, Registry entries, or SkillStore records.
- `install_candidate()` does not use the general admission callback. It remains the sole formal Candidate visibility transition and retains its receipt/digest checks.

This closes the two audited external sinks without imposing Candidate semantics on all local Registry use or adding Governance to registration.

### 4.5 Required behavior

| Input | Auto registration | `fix_skill` | Runtime visibility |
|---|---:|---:|---:|
| Quarantined Candidate payload | reject | reject | no |
| Candidate in any non-`INSTALLED` state | reject | reject | no |
| Inspection-only package Skill | reject | reject | no |
| Formally `INSTALLED` Candidate | allow | allow | yes |
| Ordinary valid local Skill | allow | allow | yes |

## 5. P1: Local Miss to Explicit Cloud Continuation

### 5.1 Root cause

Turn-0 local discovery returns no attachment when it finds no hit, and `DiscoverSkillsTool` returns only human-readable empty-result text. The Cloud workflow exists through `cloud_browse_skills`, but the local miss does not carry a durable machine-readable continuation. `execute_task` also searches Cloud before execution even when a local Skill will be used, and only appends candidates after execution.

### 5.2 Selected approach

Use the existing Host/MCP tool loop as the orchestration boundary. A local miss becomes an explicit structured continuation; it does not become an internal autonomous import.

#### Turn-0 and `DiscoverSkillsTool`

When local discovery has zero hits, return the existing `skill_discovery` attachment shape with:

```json
{
  "type": "skill_discovery",
  "skills": [],
  "signal": {
    "status": "local_miss",
    "next_action": "cloud_skill_discovery",
    "query": "<original query>"
  },
  "source": "openspace"
}
```

`DiscoverSkillsTool` returns the same semantic status in result metadata. This tells Codex that local retrieval is exhausted without pretending that a Cloud tool is an installed Skill.

#### MCP `search_skills`

On zero local results, the response adds:

```json
{
  "skill_resolution": {
    "status": "local_miss",
    "selection_owner": "codex",
    "next_actions": [
      {
        "tool": "cloud_browse_skills",
        "action": "search_skills",
        "required_fields": ["query"]
      }
    ]
  }
}
```

Local hits retain the existing result payload and add no Cloud requirement.

#### MCP `execute_task`

Cloud search is deferred until after local execution metadata is available. It runs only when all are true:

- `search_scope == "all"`;
- the controlled Cloud client is available;
- `result.skills_used` is empty.

When candidates exist, the response carries `skill_resolution.status=cloud_discovery_required`, candidates, `selection_owner=codex`, and the existing explicit `cloud_browse_skills` continuation. When no candidates exist it reports `cloud_no_match`; when Cloud is unavailable it reports `cloud_unavailable` without failing local execution.

`execute_task` does not acquire a candidate, choose the first result, or synthesize a selected ID. Its existing task execution status and response remain intact, preserving callers that use tool-only fallback. Existing consumers that ignore added JSON fields remain compatible.

### 5.3 Explicit Codex boundary

Only a subsequent, explicit call containing a chosen `cloud_skill_id` can reach acquisition:

```text
local_miss
  -> cloud_browse_skills(action="search_skills")
  -> candidates returned
  -> Codex selects cloud_skill_id
  -> cloud_browse_skills(action="import_skill", cloud_skill_id=..., local_category_path=...)
```

Tests will assert that local miss and Cloud search never call import, never create Candidate state, and never register content. The existing two-stage Candidate tests continue to prove that acquisition alone is not visibility.

### 5.4 Host Skill alignment

Update the existing `skill-discovery` and `delegate-task` Host Skills only to describe the structured continuation and retry/use behavior. These instructions document the durable protocol; they are not the enforcement mechanism.

## 6. P1: Runtime Dependency Alignment

### 6.1 Evidence and source of truth

OpenSpace declares:

```text
skill-engineering @ git+https://github.com/gushuomaster/skill-engineering.git@0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c
```

That pinned revision contains `engine.managed_completion`. Against the clean existing checkout of that exact revision, the current Candidate Governance, Install, and integration tests pass (`25 passed`). Therefore this phase has no evidence that the pin must move to the local `skill-engineering` HEAD.

The actual drift comes from two install paths:

- `pyproject.toml` contains the VCS pin;
- the legacy `requirements.txt` omits `skill-engineering`, allowing a previously installed revision to remain active.

### 6.2 Minimal closure

1. Keep `pyproject.toml` as the authoritative revision.
2. Add the exact same VCS requirement to `requirements.txt` so the supported legacy install path cannot silently omit the engine.
3. Add a dependency contract test that:
   - parses both declarations and requires the same immutable revision;
   - imports `engine.managed_completion` and the formal serialization/Governance symbols used by Candidate installation.
4. Verify the contract in a clean task-specific virtual environment installed from the OpenSpace project metadata, not from the user's stale global interpreter.

No runtime provenance platform, lockfile migration, release, or `skill-engineering` source change is introduced. If a clean install of the pinned revision fails the smoke contract, implementation stops and returns that new dependency decision rather than silently using local `PYTHONPATH`.

## 7. P2: Candidate Crash Reconciliation

### 7.1 Proof-first gate

Before production recovery code, add a subprocess kill-point test that terminates the process after:

```text
os.replace(temporary, final_path)
```

and before Candidate state transitions from `INSTALLING` to `INSTALLED`.

The test must first prove the durable post-crash condition:

```text
formal final_path exists
AND Candidate state == INSTALLING
```

If that condition cannot be reproduced, no recovery code is added. If reproduced as expected from the current ordering, add only the reconciliation below.

### 7.2 Existing durable recovery inputs

No journal is needed because the current lifecycle already persists the required intent and identity:

- immutable Candidate manifest;
- `INSTALLING` state;
- candidate-bound Governance binding and receipt digest;
- canonical quarantine payload and candidate digest;
- deterministic formal target path;
- ownership-checked Registry, SkillStore, and mapping compensation primitives;
- idempotent SQLite upserts and atomic JSON state replacement.

### 7.3 Minimal reconciliation function

Add one bounded startup function that enumerates only Candidates in `INSTALLING` and produces a result per Candidate. It runs after the runtime Registry/SkillStore have initialized but before the MCP server instance is returned to any caller.

For each record:

1. Recompute Candidate identity, manifest digest, binding path/digest, expected formal path, and current bytes.
2. If the formal path is absent:
   - remove only exact-path/exact-ID partial Registry, SkillStore, and mapping state;
   - transition to `INSTALL_FAILED` with a recovery code.
3. If the formal path exists but identity, binding, or digest does not match:
   - remove exact owned visibility side effects;
   - transition to `INTEGRITY_MISMATCH`;
   - retain the directory and quarantine evidence for diagnosis rather than deleting possibly modified bytes.
4. If the formal path exists and all bindings/digests match:
   - parse the installed Skill;
   - idempotently ensure SkillStore, Cloud/local binding, and classification;
   - register the exact Skill path;
   - transition to `INSTALLED` with the verified installed digest and receipt digest.

If reconciliation itself is interrupted, state remains `INSTALLING` and the same bounded operations replay on the next startup. If managed state is corrupt or ambiguous such that fail-closed visibility cannot be established, startup fails instead of serving a potentially unmanaged Skill.

The general hot-registration admission from section 4 independently rejects an `INSTALLING` formal path until reconciliation completes.

### 7.4 Startup placement

The MCP `_get_openspace()` initialization lock is the existing critical section:

```text
OpenSpace.initialize()
  -> Registry discovery / SkillStore startup sync
  -> Candidate INSTALLING reconciliation
  -> host Skill hot registration
  -> publish initialized MCP runtime
```

Although initial Registry discovery may parse a crash-left formal directory, no external request can observe the runtime before reconciliation. Invalid or incomplete records are removed from Registry/SkillStore before `_get_openspace()` returns.

## 8. Install-to-Runtime Reuse Evidence

Add a real integration test with exact content markers:

1. Acquire a Cloud bundle through the existing acquisition path into quarantine.
2. Run real skill-engineering inspection, validation, Gate PASS, and Codex confirmation to obtain a formal managed completion receipt.
3. Install with the current Candidate installer.
4. Close and discard the original Registry and SkillStore objects.
5. Recreate startup Registry discovery and SkillStore sync from the formal Skill root.
6. Search locally with the ordinary `SkillDiscoveryService` and find the installed Skill.
7. Invoke the ordinary `SkillTool` for that Skill.
8. Assert that the exact installed `SKILL.md` marker reaches the tool result/additional context boundary.

No production feature is added solely for this test. Any failure must be fixed at the first existing broken seam rather than by introducing an E2E-only API.

## 9. Failure Semantics

| Failure | Required result |
|---|---|
| Quarantine path offered to registration | reject; no Registry/Store mutation |
| Non-installed managed formal path offered to registration | reject; no Registry/Store mutation |
| Inspection marker malformed or `inspection_only=true` | reject fail closed |
| Cloud unavailable after local miss | local result preserved; explicit `cloud_unavailable` |
| Cloud returns no candidates | explicit `cloud_no_match`; no acquisition |
| Caller omits explicit selected `cloud_skill_id` | no acquisition |
| Governance BLOCKED/INCOMPLETE/ERROR | no install or visibility |
| Candidate/receipt/digest mismatch | `INTEGRITY_MISMATCH`; no visibility |
| Crash before formal placement | reconcile to owned cleanup + `INSTALL_FAILED` |
| Crash after matching formal placement | replay idempotently to `INSTALLED` |
| Crash-left formal bytes do not match binding | remove visibility, retain evidence, `INTEGRITY_MISMATCH` |
| Dependency pin/import mismatch in clean environment | fail smoke check; stop for dependency decision |

## 10. Compatibility

- `import_skill` remains discoverable and acquisition-only.
- `install_candidate` and the serialized Governance outcome contract are unchanged.
- `execute_task` keeps its existing parameters, execution behavior, and top-level status. It only adds structured resolution fields and avoids unnecessary Cloud search after a local hit.
- `search_skills` keeps existing local results and adds fields only on a miss.
- Registry admission is an optional callback used by the audited MCP hot-registration path; unrelated Registry consumers retain current behavior.
- Ordinary local Skill registration and repair remain supported.
- Installed Candidate Skills remain eligible for normal discovery and later Evolution.
- No public API deletion, repository merge, release, push, or PR occurs in this phase.

## 11. Planned Code Surface

Expected OpenSpace production changes:

- `openspace/cloud/candidate_lifecycle.py` — authoritative intended path and bounded read-only Candidate lookup.
- `openspace/cloud/candidate_visibility.py` — narrow managed-artifact admission decision.
- `openspace/cloud/candidate_recovery.py` — added only after the kill-point RED proves the inconsistent state.
- `openspace/cloud/candidate_install.py` — reuse authoritative path helper; no Governance redesign.
- `openspace/skill_engine/registry.py` — optional per-entry admission in hot discovery.
- `openspace/skill_engine/protocol.py` — structured turn-0/tool local-miss signal.
- `openspace/entrypoints/mcp/server.py` — admission at both audited sinks, conditional Cloud continuation, startup reconciliation.
- `openspace/host_skills/skill-discovery/SKILL.md` and `openspace/host_skills/delegate-task/SKILL.md` — protocol documentation only.
- `requirements.txt` — mirror the existing immutable dependency pin.

Expected tests:

- focused visibility-admission tests for execute/hot registration and `fix_skill`;
- local hit/miss and explicit Codex-selection boundary tests;
- dependency declaration/import contract test;
- subprocess crash kill-point and restart reconciliation tests;
- Cloud Candidate to restart/runtime reuse E2E test;
- existing Candidate and Evolution Governance regressions.

No `skill-engineering` production change is currently planned. Its authoritative suite and Skill validator remain required final checks.

## 12. TDD and Verification Strategy

Implementation follows separate RED/GREEN cycles:

1. Visibility bypass tests fail, then add the admission policy and minimal Registry hook.
2. Local miss continuation tests fail, then add structured signals and conditional Cloud search.
3. Dependency contract fails under the stale/legacy path, then align `requirements.txt` and verify a clean install.
4. Subprocess kill-point proves the `INSTALLING` inconsistency, then add minimal reconciliation and replay tests.
5. Restart/runtime reuse E2E fails at the first real seam, then fix only that seam.
6. Run focused Candidate, Evolution, Host Skill validator, full OpenSpace, and full skill-engineering verification from fresh state.

Final reporting records exact PASS, FAIL, SKIP, XFAIL, and collection-error counts. Prior phase results are context only and cannot substitute for fresh execution.

## 13. Completion Invariants

The phase may report functional completion only when fresh evidence supports:

```text
UNMANAGED_REMOTE_CONTENT_VISIBLE = NO
QUARANTINE_VISIBLE = NO
INSPECTION_ONLY_VISIBLE = NO
NON_PASS_CANDIDATE_INSTALLABLE = NO
TAMPERED_CANDIDATE_INSTALLABLE = NO
GOVERNANCE_BYPASS_PATHS = 0
LOCAL_SKILL_REUSE_COMPLETE = YES
LOCAL_MISS_CLOUD_ESCALATION_COMPLETE = YES
INSTALL_TO_RUNTIME_REUSE_VERIFIED = YES
RUNTIME_DEPENDENCY_ALIGNED = YES
EVOLUTION_GOVERNANCE_PRESERVED = YES
USER_CHANGES_PRESERVED = YES
```

If crash reconciliation cannot be made deterministic with the existing manifest/state/binding and ownership-checked primitives, implementation stops and returns the exact failing test plus a persistence design decision. A journal or transaction framework is not authorized by this design.
