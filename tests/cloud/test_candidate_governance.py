from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.inventory import digest_tree
from engine.mechanism_selection import (
    ENVIRONMENT_TOOLING,
    IMPLEMENTATION_FIX,
    MERGE_INVARIANT,
    PROMPT_RULE,
    REFERENCE_OR_INSTRUCTION,
    REGRESSION_TEST,
    SCHEMA_VALIDATOR,
    WORKFLOW_REFACTOR,
)
from engine.models import (
    ArtifactRole,
    CapabilityManifest,
    CheckResult,
    CheckStatus,
    ControlGap,
    DecisionRecord,
    DeliverableContractApplicability,
    GateVerdict,
    Intent,
    LifecycleState,
    PrimaryIssueClass,
    ProviderDescriptor,
    ProviderResult,
    ProviderStatus,
    RegressionDisposition,
    SemanticConfirmation,
)
from engine.orchestrator import PipelineOrchestrator
from engine.providers import CAPABILITY_CONTRACT, ProviderGateway
from engine.serialization import outcome_to_data

from openspace.cloud.candidate_governance import (
    CandidateGovernanceError,
    verify_confirmed_candidate,
)
from openspace.cloud.candidate_lifecycle import (
    CandidateRepository,
    CandidateStatus,
    SourceIntegrityStatus,
)


_ALL_MECHANISMS = (
    IMPLEMENTATION_FIX,
    REGRESSION_TEST,
    SCHEMA_VALIDATOR,
    ENVIRONMENT_TOOLING,
    WORKFLOW_REFACTOR,
    MERGE_INVARIANT,
    REFERENCE_OR_INSTRUCTION,
    PROMPT_RULE,
)


@dataclass
class CapabilityProvider:
    descriptor: ProviderDescriptor = ProviderDescriptor(
        "test.candidate-capability",
        "test://candidate-capability",
        "a" * 64,
        CAPABILITY_CONTRACT,
        ProviderStatus.AVAILABLE,
        "test",
        (),
        None,
    )

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        manifest = CapabilityManifest(
            "1.0",
            str(request["inspection_id"]),
            str(request["inspection_nonce"]),
            ArtifactRole(str(request["artifact_role"])),
            str(request["target_digest"]),
            self.descriptor.provider_id,
            (),
            "present",
            ("file=SKILL.md;line=1",),
        )
        return ProviderResult(
            self.descriptor.provider_id,
            capability,
            ProviderStatus.AVAILABLE,
            (),
            (),
            ("candidate capability contract inspected",),
            (),
            False,
            capability_manifest=manifest,
        )


@pytest.fixture
def candidate(tmp_path: Path) -> SimpleNamespace:
    return _make_candidate(
        tmp_path,
        "---\nname: demo\ndescription: Audit the exact candidate bytes.\n---\n\n"
        "# Demo\n\nInspect the candidate.\n",
    )


@pytest.fixture
def blocked_candidate(tmp_path: Path) -> SimpleNamespace:
    return _make_candidate(
        tmp_path,
        "---\nname: Bad Name\ndescription: Incomplete candidate.\n---\n\nTODO\n",
    )


def _make_candidate(tmp_path: Path, skill_text: str) -> SimpleNamespace:
    prepared = tmp_path / "prepared" / "demo"
    prepared.mkdir(parents=True)
    (prepared / "SKILL.md").write_text(skill_text, encoding="utf-8")
    (prepared / ".skill_id").write_text("demo__imp_12345678\n", encoding="utf-8")
    repository = CandidateRepository(tmp_path / "state" / "candidates")
    manifest = repository.quarantine(
        prepared,
        cloud_skill_id="cloud-1",
        source_bundle_sha256="1" * 64,
        source_manifest_hash="sha256:" + "1" * 64,
        source_integrity_status=SourceIntegrityStatus.PROVEN,
        local_content_hash="sha256:" + "2" * 64,
        final_skill_id="demo__imp_12345678",
        intended_install_parent=tmp_path / "formal-skills",
        local_category="workflow",
        local_category_path="technology/computing",
        package_id="package-1",
        package_path="technology/computing",
        package_snapshot_version="snapshot-1",
        acquired_at="2026-09-30T00:00:00Z",
    )
    return SimpleNamespace(
        repository=repository,
        manifest=manifest,
        payload_path=repository.payload_path(manifest),
    )


def _decision() -> DecisionRecord:
    return DecisionRecord(
        Intent.AUDIT,
        PrimaryIssueClass.NO_DEFECT,
        (ControlGap.NONE,),
        RegressionDisposition.NOT_APPLICABLE,
        None,
        (),
        (),
        _ALL_MECHANISMS,
        None,
        "CODEX",
    )


def _behavior(path: Path) -> CheckResult:
    return CheckResult(
        "behavioral.candidate-audit",
        "test.runner",
        path.name,
        True,
        CheckStatus.PASS,
        True,
        True,
        1.0,
        ("candidate behavior executed",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        str(path),
    )


def _audit(
    candidate_path: Path,
    *,
    applicability: DeliverableContractApplicability = (
        DeliverableContractApplicability.NOT_REQUIRED
    ),
):
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway((CapabilityProvider(),))
    )
    inspection = orchestrator.inspect(
        Intent.AUDIT,
        candidate_path,
        deliverable_contract_applicability=applicability,
    )
    assert inspection.baseline_capability_manifest is not None, inspection.provider_evidence
    validation = orchestrator.validate(
        inspection,
        _decision(),
        (),
        candidate=None,
        target_parent=candidate_path.parent,
        authorized_to_modify=False,
        behavioral_runner=_behavior,
    )
    return orchestrator.confirm(
        validation,
        SemanticConfirmation(
            digest_tree(candidate_path),
            "Codex confirmed the exact quarantined Candidate.",
            "CODEX",
        ),
    )


@pytest.fixture
def real_audit_outcome(candidate: SimpleNamespace):
    outcome = _audit(candidate.payload_path)
    assert outcome.gate_result.verdict is GateVerdict.PASS
    return outcome


@pytest.fixture
def blocked_audit_outcome(blocked_candidate: SimpleNamespace):
    outcome = _audit(blocked_candidate.payload_path)
    assert outcome.gate_result.verdict is GateVerdict.FAIL
    return outcome


@pytest.fixture
def partial_audit_outcome(candidate: SimpleNamespace):
    return _audit(
        candidate.payload_path,
        applicability=DeliverableContractApplicability.OPTIONAL,
    )


def test_verified_outcome_requires_real_codex_confirmation(
    candidate: SimpleNamespace,
    real_audit_outcome,
) -> None:
    payload = outcome_to_data(real_audit_outcome)
    payload["semantic_confirmation"]["confirmed_by"] = "PROVIDER"

    result = verify_confirmed_candidate(candidate.payload_path, payload)

    assert result.status is CandidateStatus.GOVERNANCE_INCOMPLETE
    assert result.install_authorized is False


def test_verified_outcome_rejects_forged_pass(
    blocked_candidate: SimpleNamespace,
    blocked_audit_outcome,
) -> None:
    payload = outcome_to_data(blocked_audit_outcome)
    payload["gate_result"]["verdict"] = "PASS"

    result = verify_confirmed_candidate(blocked_candidate.payload_path, payload)

    assert result.status is CandidateStatus.GOVERNANCE_BLOCKED
    assert result.install_authorized is False


def test_verified_outcome_rejects_same_bytes_from_another_candidate_path(
    tmp_path: Path,
    candidate: SimpleNamespace,
    real_audit_outcome,
) -> None:
    copied_candidate = tmp_path / "copied-candidate"
    shutil.copytree(candidate.payload_path, copied_candidate)

    with pytest.raises(CandidateGovernanceError, match="canonical Candidate path"):
        verify_confirmed_candidate(
            copied_candidate,
            outcome_to_data(real_audit_outcome),
        )


def test_verified_pass_binds_exact_candidate_before_marking_governance_passed(
    candidate: SimpleNamespace,
    real_audit_outcome,
) -> None:
    result = verify_confirmed_candidate(
        candidate.payload_path,
        outcome_to_data(real_audit_outcome),
    )

    binding = candidate.repository.bind_governance(
        candidate.manifest.candidate_id,
        result,
        bound_at="2026-09-30T01:00:00Z",
    )

    saved = json.loads(
        candidate.repository.governance_binding_path(
            candidate.manifest.candidate_id
        ).read_text(encoding="utf-8")
    )
    assert result.status is CandidateStatus.GOVERNANCE_PASSED
    assert result.install_authorized is True
    assert binding.candidate_id == candidate.manifest.candidate_id
    assert saved["managed_completion_receipt_digest"] == result.receipt_digest
    assert saved["canonical_payload_path"] == str(candidate.payload_path.resolve())
    assert (
        candidate.repository.load_state(candidate.manifest.candidate_id).status
        is CandidateStatus.GOVERNANCE_PASSED
    )


def test_verified_outcome_rejects_payload_tampered_after_confirmation(
    candidate: SimpleNamespace,
    real_audit_outcome,
) -> None:
    payload = outcome_to_data(real_audit_outcome)
    (candidate.payload_path / "tampered.txt").write_text("changed\n", encoding="utf-8")

    result = verify_confirmed_candidate(candidate.payload_path, payload)

    assert result.status is CandidateStatus.INTEGRITY_MISMATCH
    assert result.install_authorized is False
    assert not candidate.repository.governance_binding_path(
        candidate.manifest.candidate_id
    ).exists()


def test_verified_outcome_requires_managed_completion_receipt(
    candidate: SimpleNamespace,
    real_audit_outcome,
) -> None:
    payload = outcome_to_data(real_audit_outcome)
    payload["completion_receipt"] = None

    result = verify_confirmed_candidate(candidate.payload_path, payload)

    assert result.status is CandidateStatus.GOVERNANCE_INCOMPLETE
    assert result.install_authorized is False
    assert not candidate.repository.governance_binding_path(
        candidate.manifest.candidate_id
    ).exists()


def test_verified_outcome_requires_full_coverage(
    candidate: SimpleNamespace,
    partial_audit_outcome,
) -> None:
    result = verify_confirmed_candidate(
        candidate.payload_path,
        outcome_to_data(partial_audit_outcome),
    )

    assert result.status is CandidateStatus.GOVERNANCE_INCOMPLETE
    assert result.install_authorized is False
    assert not candidate.repository.governance_binding_path(
        candidate.manifest.candidate_id
    ).exists()
