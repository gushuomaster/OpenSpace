# Skill Candidate Governance Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct Cloud Skill import/register with an explicit Acquisition → Quarantine → Governance → receipt-verified Install/Register lifecycle.

**Architecture:** OpenSpace owns a minimal file-backed Candidate record, acquisition, placement, install, and registration. A narrow OpenSpace adapter recomputes the existing skill-engineering `AUDIT` confirmation and `ManagedCompletionReceipt` from serialized validation/confirmation data; it does not add a second Gate or an LLM decision. Installation reuses the existing Registry parser/registration, SkillStore transaction/delete API, SQLite mapping store, atomic sibling rename, and compensating delete primitives; this plan does not introduce a durable journal, startup recovery subsystem, or new Registry transaction framework.

**Tech Stack:** Python 3.12+, pathlib/json/hashlib/shutil, OpenSpace `SkillRegistry`/`SkillStore`/`CloudLocalMappingStore`, skill-engineering phased workflow and managed completion primitives, pytest/pytest-asyncio.

**Spec:** `reports/skill-engineering-integration/candidate-governance-lifecycle-design.md`

## Global Constraints

- Candidate bytes must be fully prepared in quarantine before Governance; no `.skill_id`, `.cloud_skill.json`, classification, or placement mutation may be added after confirmation.
- Only a real skill-engineering `AUDIT_COMPLETE_VALID` + `PASS` + `FULL` + `CAPABILITY_PRESERVED` outcome with `confirmed_by=CODEX` and a matching formal `ManagedCompletionReceipt` may authorize installation.
- Candidate identity, manifest digest, canonical payload path, current payload digest, validation/inspection identity, and receipt digest must all match at install time.
- Gate `FAIL`, `INCOMPLETE`, `ERROR`, unproven source identity, and any integrity mismatch fail closed before formal filesystem placement, Registry, or SkillStore visibility.
- `import_skill` remains a discoverable compatibility action but becomes acquisition-only. It must not return a formal `local_path` or perform binding/Registry/SkillStore mutation.
- `import_package_bundle` must not create `.skill_id`, Cloud/local binding, Registry, or SkillStore records for bundled Skills.
- Do not call skill-engineering `apply`; OpenSpace remains the install owner.
- Do not change Evolution Governance responsibilities or merge repositories.
- Use `reuse existing primitive > minimal extension > new abstraction`. No journal/startup recovery/Registry prepare-commit framework is in scope unless a failing invariant test proves the selected existing primitives cannot fail closed.
- Candidate manifest, state, and binding contain only fields consumed by acquisition, verification, installation, diagnostics, or rollback.
- All text and JSON writes are UTF-8 without BOM; JSON replacement uses a sibling temporary file and `os.replace()`.
- Existing user modifications in readiness reports and `tests/live/provider_workload.py` are out of scope and must not enter task commits.

## File Structure

### New production files

- `openspace/cloud/candidate_lifecycle.py` — Candidate records, canonical identity/digests, state transitions, quarantine path ownership, and atomic JSON persistence.
- `openspace/cloud/candidate_governance.py` — narrow reconstruction/verification of serialized skill-engineering `AUDIT` outcomes and candidate-bound binding creation.
- `openspace/cloud/candidate_install.py` — receipt-gated filesystem placement, mapping/SkillStore/Registry ordering, and synchronous compensation.

### Modified production files

- `openspace/cloud/client.py` — convert Skill import to acquisition-only; download package bundles only into non-scanned state storage.
- `openspace/cloud/local_mapping.py` — add one ownership-checked delete transaction for import compensation.
- `openspace/skill_engine/registry.py` — add one ownership-checked unregister primitive for compensation.
- `openspace/entrypoints/mcp/server.py` — stop direct registration, add a second-stage install action, and remove package auto-discovery.
- `openspace/cloud/cli/download_skill.py` — report quarantined Candidate status instead of a formally installed Skill.
- `openspace/host_skills/skill-discovery/SKILL.md` and `openspace/host_skills/delegate-task/SKILL.md` — describe the explicit governance handoff and install continuation.

### Tests

- `tests/cloud/test_candidate_lifecycle.py`
- `tests/cloud/test_candidate_acquisition.py`
- `tests/cloud/test_candidate_governance.py`
- `tests/cloud/test_candidate_install.py`
- `tests/cloud/test_candidate_entrypoints.py`
- `tests/cloud/test_candidate_governance_integration.py`

---

### Task 1: Add minimal Candidate persistence and quarantine ownership

**Files:**
- Create: `openspace/cloud/candidate_lifecycle.py`
- Create: `tests/cloud/test_candidate_lifecycle.py`

**Interfaces:**
- Produces `CandidateStatus`, `SourceIntegrityStatus`, `CandidateManifest`, `CandidateState`, `CandidateGovernanceBinding`, `CandidateRepository`, `canonical_json_digest()`, and `candidate_identity()`.
- `CandidateRepository.quarantine()` accepts a fully prepared staging Skill and atomically creates `<state-root>/candidates/quarantine/<candidate-id>/`.
- `CandidateRepository.transition()` uses compare-before-write state transitions; callers cannot skip from `QUARANTINED` to `INSTALLED`.

- [ ] **Step 1: Write failing identity, quarantine, and transition tests**

```python
def test_candidate_identity_binds_source_bytes_and_placement_but_not_timestamp(tmp_path):
    first = candidate_identity(
        cloud_skill_id="cloud-1",
        source_bundle_sha256="1" * 64,
        source_manifest_hash="sha256:" + "1" * 64,
        source_integrity_status=SourceIntegrityStatus.PROVEN,
        candidate_digest="2" * 64,
        final_skill_id="demo__imp_12345678",
        final_directory_name="demo",
        intended_install_parent=str(tmp_path / "skills"),
        local_category_path="technology/computing",
    )
    second = candidate_identity(
        cloud_skill_id="cloud-1",
        source_bundle_sha256="1" * 64,
        source_manifest_hash="sha256:" + "1" * 64,
        source_integrity_status=SourceIntegrityStatus.PROVEN,
        candidate_digest="2" * 64,
        final_skill_id="demo__imp_12345678",
        final_directory_name="demo",
        intended_install_parent=str(tmp_path / "skills"),
        local_category_path="technology/computing",
    )
    assert first == second


def test_quarantine_never_writes_intended_install_root(tmp_path, prepared_skill):
    install_root = tmp_path / "formal-skills"
    repository = CandidateRepository(tmp_path / "state")
    manifest = repository.quarantine(
        prepared_skill,
        cloud_skill_id="cloud-1",
        source_bundle_sha256="1" * 64,
        source_manifest_hash="sha256:" + "1" * 64,
        source_integrity_status=SourceIntegrityStatus.PROVEN,
        final_skill_id="demo__imp_12345678",
        intended_install_parent=install_root,
        local_category="tool",
        local_category_path="technology/computing",
        package_id="package-1",
        package_path="technology/computing",
        package_snapshot_version="snapshot-1",
        acquired_at="2026-09-30T00:00:00Z",
    )
    assert repository.payload_path(manifest).is_dir()
    assert not install_root.exists()
    assert repository.load_state(manifest.candidate_id).status is CandidateStatus.QUARANTINED


def test_state_machine_rejects_install_without_governance_pass(tmp_path, candidate):
    with pytest.raises(ValueError, match="invalid Candidate transition"):
        candidate.repository.transition(
            candidate.manifest.candidate_id,
            expected={CandidateStatus.QUARANTINED},
            next_status=CandidateStatus.INSTALLED,
        )
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/cloud/test_candidate_lifecycle.py -v -p no:cacheprovider`

Expected: import failure because `openspace.cloud.candidate_lifecycle` does not exist.

- [ ] **Step 3: Implement immutable records and canonical identity**

```python
class CandidateStatus(StrEnum):
    QUARANTINED = "QUARANTINED"
    GOVERNANCE_PENDING = "GOVERNANCE_PENDING"
    GOVERNANCE_PASSED = "GOVERNANCE_PASSED"
    GOVERNANCE_BLOCKED = "GOVERNANCE_BLOCKED"
    GOVERNANCE_INCOMPLETE = "GOVERNANCE_INCOMPLETE"
    GOVERNANCE_ERROR = "GOVERNANCE_ERROR"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    INSTALLING = "INSTALLING"
    INSTALLED = "INSTALLED"
    INSTALL_FAILED = "INSTALL_FAILED"


class SourceIntegrityStatus(StrEnum):
    PROVEN = "PROVEN"
    UNPROVEN = "UNPROVEN"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True, slots=True)
class CandidateManifest:
    schema_version: str
    candidate_id: str
    cloud_skill_id: str
    source_bundle_sha256: str
    source_manifest_hash: str | None
    source_integrity_status: SourceIntegrityStatus
    candidate_digest: str
    local_content_hash: str
    final_skill_id: str
    final_directory_name: str
    intended_install_parent: str
    local_category: str
    local_category_path: str
    package_id: str | None
    package_path: str | None
    package_snapshot_version: str | None
    acquired_at: str
```

`candidate_identity()` hashes canonical JSON over every identity field except timestamps, filesystem quarantine location, and mutable state. `CandidateRepository.quarantine()` copies the prepared Skill into an acquiring sibling, computes `engine.inventory.digest_tree()`, computes the ID, writes manifest/state, then uses `os.replace()` to publish the quarantine directory. Existing equal identity is idempotent only when its manifest and payload digest still match; otherwise raise `CandidateIntegrityError`.

- [ ] **Step 4: Implement state transitions and Governance binding storage**

The allowed transition table is exact: `QUARANTINED → GOVERNANCE_PENDING`; pending may become passed/blocked/incomplete/error/mismatch; passed may become installing/mismatch; installing may become installed/install_failed/mismatch. `save_governance_binding()` requires a manifest digest and payload digest that still match before atomic write.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest tests/cloud/test_candidate_lifecycle.py -v -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add openspace/cloud/candidate_lifecycle.py tests/cloud/test_candidate_lifecycle.py
git commit -m "feat: persist quarantined skill candidates"
```

---

### Task 2: Convert Cloud Skill import into acquisition-only behavior

**Files:**
- Modify: `openspace/cloud/client.py:958-1142`
- Create: `tests/cloud/test_candidate_acquisition.py`

**Interfaces:**
- Consumes `CandidateRepository.quarantine()` from Task 1.
- Keeps `OpenSpaceClient.import_skill(cloud_skill_id, target_dir, ...)` callable; `target_dir` becomes intended formal placement, not extraction control.
- Produces a response with `status="governance_required"`, `candidate_id`, `candidate_path`, `candidate_digest`, `source_integrity_status`, `registered=False`, and no formal `local_path`.

- [ ] **Step 1: Write a failing acquisition isolation test**

```python
def test_import_skill_acquires_to_quarantine_without_binding_or_formal_files(
    tmp_path, cloud_client, mapping_store, valid_bundle,
):
    install_root = tmp_path / "formal-skills"
    cloud_client.fetch_cloud_skill = lambda _: cloud_metadata(
        manifest_hash="sha256:" + sha256(valid_bundle).hexdigest()
    )
    cloud_client.download_skill_bundle = lambda *_args, **_kwargs: valid_bundle

    result = cloud_client.import_skill(
        "cloud-1",
        install_root,
        local_category="tool",
        local_category_path="technology/computing",
    )

    assert result["status"] == "governance_required"
    assert result["registered"] is False
    assert "local_path" not in result
    assert Path(result["candidate_path"]).is_dir()
    assert not install_root.exists()
    assert mapping_store.get_binding_by_cloud("cloud-1") is None
```

The test replaces only Cloud network methods. ZIP extraction, sidecar preparation, digesting, quarantine persistence, and mapping-store reads remain real.

- [ ] **Step 2: Run the test and verify RED against direct import**

Run: `python -m pytest tests/cloud/test_candidate_acquisition.py::test_import_skill_acquires_to_quarantine_without_binding_or_formal_files -v -p no:cacheprovider`

Expected: FAIL because current import writes the formal directory and binding.

- [ ] **Step 3: Implement acquisition preparation**

Add `OpenSpaceClient._candidate_repository()` using `<mapping-store-db-parent>/candidates`. Download into an Engine-owned temporary directory, perform existing secure ZIP extraction/root discovery, write `.skill_id`, compute the pure classification without persisting it, write the stable `.cloud_skill.json`, and call `CandidateRepository.quarantine()`.

Source proof is exact and fail-closed:

```python
bundle_sha256 = hashlib.sha256(zip_data).hexdigest()
declared = _normalized_sha256(skill_data.get("manifest_hash"))
source_status = (
    SourceIntegrityStatus.PROVEN if declared == bundle_sha256
    else SourceIntegrityStatus.MISMATCH if declared is not None
    else SourceIntegrityStatus.UNPROVEN
)
```

Do not accept `snapshot_version` alone because the current bundle endpoint is not requested with that revision.

- [ ] **Step 4: Add UNPROVEN and MISMATCH tests**

```python
@pytest.mark.parametrize(
    ("manifest_hash", "expected"),
    [(None, "UNPROVEN"), ("sha256:" + "0" * 64, "MISMATCH")],
)
def test_source_proof_never_upgrades_unknown_or_wrong_hash(
    manifest_hash, expected, cloud_client, valid_bundle, tmp_path,
):
    cloud_client.fetch_cloud_skill = lambda _: cloud_metadata(manifest_hash=manifest_hash)
    cloud_client.download_skill_bundle = lambda *_args, **_kwargs: valid_bundle
    result = cloud_client.import_skill("cloud-1", tmp_path / "formal")
    assert result["source_integrity_status"] == expected
    assert result["registered"] is False
```

- [ ] **Step 5: Run acquisition and lifecycle tests**

Run: `python -m pytest tests/cloud/test_candidate_lifecycle.py tests/cloud/test_candidate_acquisition.py -v -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add openspace/cloud/client.py tests/cloud/test_candidate_acquisition.py
git commit -m "feat: acquire cloud skills into quarantine"
```

---

### Task 3: Recompute skill-engineering confirmation and bind the exact Candidate

**Files:**
- Create: `openspace/cloud/candidate_governance.py`
- Modify: `openspace/cloud/candidate_lifecycle.py`
- Create: `tests/cloud/test_candidate_governance.py`

**Interfaces:**
- Produces `CandidateGovernanceResult`, `CandidateGovernanceError`, and `verify_confirmed_candidate(candidate_path, serialized_outcome)`.
- Uses existing `engine.serialization.validation_from_data()`, `confirmation_from_data()`, `completion_receipt_from_data()`, `PipelineOrchestrator.confirm()`, `completion_receipt()`, `validate_completion_receipt()`, and `managed_status()`.
- Does not trust serialized `gate_result`, `formal_completion`, or a caller-provided PASS string.

- [ ] **Step 1: Write failing real-outcome verification tests**

Use a test Provider to create a real `AUDIT` inspection/validation/confirmation with `FULL` coverage and a real `ManagedCompletionReceipt`. The Provider is the only test double; orchestrator, Gate, digest, confirmation, receipt, serialization, and current filesystem are real.

```python
def test_verified_outcome_requires_real_codex_confirmation(candidate, real_audit_outcome):
    payload = outcome_to_data(real_audit_outcome)
    payload["semantic_confirmation"]["confirmed_by"] = "PROVIDER"
    result = verify_confirmed_candidate(candidate.payload_path, payload)
    assert result.status is CandidateStatus.GOVERNANCE_INCOMPLETE
    assert result.install_authorized is False


def test_verified_outcome_rejects_forged_pass(candidate, blocked_audit_outcome):
    payload = outcome_to_data(blocked_audit_outcome)
    payload["gate_result"]["verdict"] = "PASS"
    result = verify_confirmed_candidate(candidate.payload_path, payload)
    assert result.status is CandidateStatus.GOVERNANCE_BLOCKED
    assert result.install_authorized is False


def test_verified_outcome_rejects_same_bytes_from_another_candidate_path(
    candidate, copied_candidate, real_audit_outcome,
):
    with pytest.raises(CandidateGovernanceError, match="canonical Candidate path"):
        verify_confirmed_candidate(
            copied_candidate.payload_path,
            outcome_to_data(real_audit_outcome),
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_governance.py -v -p no:cacheprovider`

Expected: import failure because the verifier does not exist.

- [ ] **Step 3: Implement reconstruction and classification**

```python
def verify_confirmed_candidate(candidate_path: Path, serialized_outcome: Mapping[str, Any]):
    validation = validation_from_data(_required_mapping(serialized_outcome, "validation"))
    confirmation = confirmation_from_data(
        _required_mapping(serialized_outcome, "semantic_confirmation")
    )
    current = candidate_path.resolve(strict=True)
    if validation.source_path.resolve(strict=True) != current:
        raise CandidateGovernanceError("validation source is not the canonical Candidate path")
    if validation.artifact_path.resolve(strict=True) != current:
        raise CandidateGovernanceError("validation artifact is not the canonical Candidate path")
    if digest_tree(current) != validation.artifact_digest:
        return CandidateGovernanceResult.integrity_mismatch(validation)
    outcome = PipelineOrchestrator().confirm(validation, confirmation)
    # classify the recomputed Gate; parse/compare receipt only for recomputed PASS
```

For recomputed PASS, require a serialized receipt, compare it with `completion_receipt(outcome)`, call `validate_completion_receipt(receipt, outcome)`, and require `managed_status(current, receipt).formal_completion`. Return only the normalized receipt and its canonical digest. Gate `FAIL`, `INCOMPLETE`, and `ERROR` map to the corresponding Candidate state without a binding.

- [ ] **Step 4: Bind verifier PASS to Candidate manifest and path**

`CandidateRepository.bind_governance()` recomputes candidate ID, manifest digest, payload digest, canonical path, inspection ID, validation ID, and receipt digest before writing `governance/candidate-binding.json`. Only after this write does it transition to `GOVERNANCE_PASSED`.

- [ ] **Step 5: Add tamper, missing receipt, and incomplete coverage tests**

Each test asserts both the returned Candidate state and absence of a binding. The tamper test modifies the payload after confirmation and must return `INTEGRITY_MISMATCH`; missing receipt and partial coverage must return `GOVERNANCE_INCOMPLETE`.

- [ ] **Step 6: Run verifier tests and skill-engineering managed completion regression**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_governance.py -v -p no:cacheprovider`

Run: `python -m pytest tests/unit/test_managed_completion.py tests/integration/test_capability_manifest_pipeline.py -v -p no:cacheprovider` from the skill-engineering worktree.

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add openspace/cloud/candidate_lifecycle.py openspace/cloud/candidate_governance.py tests/cloud/test_candidate_governance.py
git commit -m "feat: verify candidate governance receipts"
```

---

### Task 4: Install only verified Candidates and compensate synchronous failures

**Files:**
- Create: `openspace/cloud/candidate_install.py`
- Modify: `openspace/cloud/local_mapping.py:375-424`
- Modify: `openspace/skill_engine/registry.py:905-970`
- Create: `tests/cloud/test_candidate_install.py`

**Interfaces:**
- Produces async `install_candidate(candidate_id, serialized_outcome, *, repository, registry, skill_store, mapping_store) -> CandidateInstallResult`.
- Adds `CloudLocalMappingStore.delete_import_state(local_skill_id, *, expected_cloud_skill_id, expected_local_path) -> bool`.
- Adds `SkillRegistry.unregister_skill(skill_id, *, expected_path) -> bool`.
- Reuses `SkillStore.delete_record()`; no new SkillStore transaction API.

- [ ] **Step 1: Write failing PASS ordering and negative-path tests**

```python
@pytest.mark.asyncio
async def test_pass_candidate_installs_then_becomes_registry_visible(installer_fixture):
    result = await installer_fixture.install_passed()
    assert result.status is CandidateStatus.INSTALLED
    assert result.installed_digest == installer_fixture.receipt.candidate_digest
    assert installer_fixture.registry.get_skill(result.skill_id) is not None
    assert installer_fixture.skill_store.load_record(result.skill_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome_name",
    ["blocked", "incomplete", "error", "integrity_mismatch"],
)
async def test_non_pass_candidate_never_touches_formal_state(
    outcome_name, installer_fixture,
):
    before = installer_fixture.formal_snapshot()
    result = await installer_fixture.install(outcome_name)
    assert result.installed is False
    assert installer_fixture.formal_snapshot() == before
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_install.py -v -p no:cacheprovider`

Expected: import failure because the installer does not exist.

- [ ] **Step 3: Implement the minimal install sequence with existing primitives**

The sequence is exact:

1. Load/recompute manifest, state, binding, payload and verified outcome.
2. Reject source status other than `PROVEN`, target/binding/Skill ID conflicts, and root overlap.
3. Transition `GOVERNANCE_PASSED → INSTALLING`.
4. Copy payload to a sibling temporary directory and verify receipt digest.
5. `os.replace()` the sibling into the final target; verify digest again.
6. Call existing `registry.load_skill_from_dir(final_path)` for the canonical parser result.
7. Call existing `skill_store.sync_from_registry([meta])`.
8. Persist classification and Cloud binding with the same fields already present in Candidate manifest/sidecar.
9. Call existing `registry.register_skill_dir(final_path)` as the final runtime-visibility step.
10. Persist `INSTALLED` with installed/receipt digests and return success.

On an exception, compensate only objects whose identity/path matches this Candidate, in reverse order: Registry → mapping/classification → SkillStore → final directory. Keep quarantine and Governance records, then persist `INSTALL_FAILED`. No startup journal is added.

- [ ] **Step 4: Write failure-injection tests before adding compensation methods**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["skill_store", "mapping", "registry", "state_write"])
async def test_install_failure_compensates_only_current_candidate(
    failure_point, installer_fixture,
):
    installer_fixture.fail_at(failure_point)
    result = await installer_fixture.install_passed()
    assert result.status is CandidateStatus.INSTALL_FAILED
    assert installer_fixture.registry.get_skill(installer_fixture.skill_id) is None
    assert installer_fixture.skill_store.load_record(installer_fixture.skill_id) is None
    assert installer_fixture.mapping_store.get_binding_by_local(
        installer_fixture.skill_id
    ) is None
    assert not installer_fixture.final_path.exists()
    assert installer_fixture.unrelated_skill_still_exists()
```

Run this test before production compensation changes and confirm it fails at the first unhandled side effect.

- [ ] **Step 5: Add only the two ownership-checked compensation primitives**

`delete_import_state()` executes binding/classification deletes in one SQLite transaction and returns false without mutation when expected cloud ID or path does not match. `unregister_skill()` removes `_skills` and `_content_cache` only when the registered `SkillMeta.path.parent.resolve()` equals `expected_path.resolve()`.

- [ ] **Step 6: Run install, mapping, Registry, and SkillStore tests**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_install.py tests/skill_engine/test_skill_trust_lifecycle.py -v -p no:cacheprovider`

Expected: PASS with no journal/startup recovery abstraction.

- [ ] **Step 7: Commit Task 4**

```powershell
git add openspace/cloud/candidate_install.py openspace/cloud/local_mapping.py openspace/skill_engine/registry.py tests/cloud/test_candidate_install.py
git commit -m "feat: install governed skill candidates"
```

---

### Task 5: Close MCP, CLI, and package-bundle bypasses

**Files:**
- Modify: `openspace/entrypoints/mcp/server.py:481-532, 876-1014, 1524-1642`
- Modify: `openspace/cloud/client.py:1144-1346`
- Modify: `openspace/cloud/cli/download_skill.py`
- Modify: `openspace/host_skills/skill-discovery/SKILL.md`
- Modify: `openspace/host_skills/delegate-task/SKILL.md`
- Create: `tests/cloud/test_candidate_entrypoints.py`

**Interfaces:**
- `cloud_browse_skills(action="import_skill", ...)` returns acquisition status only.
- Add `cloud_browse_skills(action="install_candidate", candidate_id=..., governance_outcome=...)` as the explicit continuation selected from the current MCP schema; it accepts the complete outcome mapping, never a bare PASS flag or receipt alone.
- `openspace-download-skill` keeps `--skill-id`, `--package-id`, and `--output-dir`; for a Skill, output-dir is intended placement and output is Candidate JSON.

- [ ] **Step 1: Write failing MCP acquisition/no-registration test**

```python
@pytest.mark.asyncio
async def test_mcp_import_action_returns_candidate_without_registration(mcp_fixture):
    response = await mcp_fixture.cloud_import_skill()
    assert response["status"] == "governance_required"
    assert response["registered"] is False
    assert response["candidate_id"]
    assert mcp_fixture.registry.list_skills() == []
    assert mcp_fixture.skill_store.load_all() == {}
```

- [ ] **Step 2: Run the test and verify RED**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_entrypoints.py::test_mcp_import_action_returns_candidate_without_registration -v -p no:cacheprovider`

Expected: FAIL because `_do_import_cloud_skill()` currently registers immediately.

- [ ] **Step 3: Remove direct registration and add the explicit install continuation**

Delete the Registry/SkillStore mutation from `_do_import_cloud_skill()`. Route the new install action to Task 4 using runtime-owned Registry/SkillStore and the Cloud client's mapping-store-backed CandidateRepository. Update every next-action string that currently promises “download/register” or immediate local retrieval.

- [ ] **Step 4: Write and run package-bundle bypass test**

```python
def test_package_bundle_is_inspection_only_and_creates_no_skill_binding(
    cloud_client, mapping_store, package_bundle,
):
    result = cloud_client.import_package_bundle("package-1", Path("ignored"))
    assert result["imported_skills"] == []
    assert result["registered_skill_count"] == 0
    assert mapping_store.get_binding_by_cloud("cloud-in-package") is None
    assert not list(Path(result["artifact_path"]).rglob(".skill_id"))
```

Change client package extraction to `<mapping-store-db-parent>/cloud-packages/<package-id>/` and remove `_bind_imported_package_skills()`. Remove MCP `discover_from_dirs()` and `sync_from_registry()` calls. `target_dir` remains accepted but cannot choose a formal scan root.

- [ ] **Step 5: Update CLI and host Skill behavior**

CLI stderr says “Candidate quarantined at …; Governance required” and prints the structured Candidate result. `--force` may only replace an equal-id quarantine acquisition; it cannot overwrite a formal Skill. Host Skill examples show acquisition, external `inspect → validate → confirm`, then `install_candidate` with complete outcome.

- [ ] **Step 6: Run entrypoint and host-skill validation tests**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_entrypoints.py tests/cloud/test_candidate_acquisition.py -v -p no:cacheprovider`

Run: `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py openspace/host_skills/skill-discovery`

Run: `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py openspace/host_skills/delegate-task`

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add openspace/entrypoints/mcp/server.py openspace/cloud/client.py openspace/cloud/cli/download_skill.py openspace/host_skills/skill-discovery/SKILL.md openspace/host_skills/delegate-task/SKILL.md tests/cloud/test_candidate_entrypoints.py
git commit -m "feat: expose two-stage cloud skill lifecycle"
```

---

### Task 6: Prove the real lifecycle and preserve Evolution Governance

**Files:**
- Create: `tests/cloud/test_candidate_governance_integration.py`
- Modify: `reports/skill-engineering-integration/candidate-governance-lifecycle-design.md`

**Interfaces:**
- Produces executable evidence for PASS install and every fail-closed state.
- Records the final mechanism decision: existing primitives were sufficient, or the exact failing test that justified any additional mechanism.

- [ ] **Step 1: Write the end-to-end PASS test before any final integration adjustment**

```python
@pytest.mark.asyncio
async def test_remote_candidate_requires_real_governance_before_install(real_lifecycle):
    acquired = real_lifecycle.acquire()
    assert acquired.status == "governance_required"
    assert not real_lifecycle.formal_path.exists()

    inspection = real_lifecycle.inspect_audit(acquired.candidate_path)
    validation = real_lifecycle.validate_audit(inspection)
    outcome = real_lifecycle.confirm_as_codex(validation)
    installed = await real_lifecycle.install(outcome_to_data(outcome))

    assert installed.status is CandidateStatus.INSTALLED
    assert digest_tree(real_lifecycle.formal_path) == completion_receipt(outcome).candidate_digest
    assert real_lifecycle.registry.get_skill(installed.skill_id) is not None
    assert real_lifecycle.skill_store.load_record(installed.skill_id) is not None
```

- [ ] **Step 2: Run the PASS test and verify its first missing integration behavior**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_governance_integration.py::test_remote_candidate_requires_real_governance_before_install -v -p no:cacheprovider`

Expected: FAIL at the first unwired lifecycle seam; fix only that seam, then rerun until PASS.

- [ ] **Step 3: Add the negative integration matrix**

Cover real Gate `FAIL`, required evidence `INCOMPLETE`, non-Codex confirmation `INCOMPLETE`, malformed/framework outcome `ERROR`, post-confirmation payload mutation `INTEGRITY_MISMATCH`, and injected install failure `INSTALL_FAILED`. Each case asserts: formal target absent, Registry missing, SkillStore missing, and quarantine/evidence retained.

- [ ] **Step 4: Run all Candidate lifecycle tests**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/cloud/test_candidate_lifecycle.py tests/cloud/test_candidate_acquisition.py tests/cloud/test_candidate_governance.py tests/cloud/test_candidate_install.py tests/cloud/test_candidate_entrypoints.py tests/cloud/test_candidate_governance_integration.py -v -p no:cacheprovider`

Expected: PASS.

- [ ] **Step 5: Run existing OpenSpace regressions**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests/skill_engine/test_governance_adapter.py tests/skill_engine/test_skill_trust_lifecycle.py tests/skill_engine/test_evolution_retry_idempotency.py tests/cloud/test_upload_trust.py -v -p no:cacheprovider`

Expected: PASS; Evolution Governance remains unchanged.

- [ ] **Step 6: Run skill-engineering authority checks**

Run from `C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering` with `PYTHONUTF8=1`:

```powershell
python -m pytest tests/unit -v -p no:cacheprovider
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer
```

Expected: the established Windows symlink skips only; all executable tests pass and the Skill validates.

- [ ] **Step 7: Run the full OpenSpace suite**

Run: `$env:PYTHONPATH='C:\Users\28320\.codex\worktrees\candidate-governance\skill-engineering'; python -m pytest tests -q -p no:cacheprovider`

Expected: PASS. Any unrelated pre-existing/live-environment failure is reported with its exact test ID and is not hidden by narrowing the command.

- [ ] **Step 8: Record the proven mechanism choice in the design**

Update sections 9 and 13 with evidence from the failure-injection tests. If existing primitives pass all invariants, explicitly record that no durable journal/startup recovery/new Registry transaction framework was added. If a new mechanism became necessary, cite the exact RED test and the smallest extension used.

- [ ] **Step 9: Commit integration evidence**

```powershell
git add tests/cloud/test_candidate_governance_integration.py reports/skill-engineering-integration/candidate-governance-lifecycle-design.md
git commit -m "test: prove governed cloud skill installation"
```

---

## Plan Self-Review

- Spec coverage: acquisition/quarantine, final-byte Governance, Codex confirmation, candidate-bound receipt, pre-install revalidation, post-PASS Registry/SkillStore, every fail-closed status, package/CLI bypass closure, Evolution regression, and no repository/product-boundary decision each map to an explicit task.
- Mechanism restraint: manifest/state/binding are implemented; journal, startup recovery, and a new Registry transaction framework are intentionally absent. Existing parser, SQLite transaction, delete, and hot-registration primitives are exercised first.
- Type consistency: Task 1 records are consumed unchanged by Tasks 2-6; Task 3 returns the normalized receipt consumed by Task 4; Task 5 only adapts external entrypoints to those services.
- No placeholders: every new file, interface, failure mode, command, and expected result is named.
