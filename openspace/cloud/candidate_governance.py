"""Verify skill-engineering Governance evidence for one exact Candidate payload."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.candidate_contract import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateVerdict,
    ManagedCompletionReceipt,
    PipelineOrchestrator,
    completion_receipt,
    completion_receipt_from_data,
    confirmation_from_data,
    digest_tree,
    managed_status,
    to_data,
    validate_completion_receipt,
    validation_from_data,
)

from openspace.cloud.candidate_lifecycle import (
    CandidateStatus,
    canonical_json_digest,
)


class CandidateGovernanceError(ValueError):
    """Raised when submitted evidence targets a different Candidate path."""


@dataclass(frozen=True, slots=True)
class CandidateGovernanceResult:
    status: CandidateStatus
    install_authorized: bool
    canonical_candidate_path: str
    candidate_digest: str
    inspection_id: str
    validation_id: str
    receipt: ManagedCompletionReceipt | None = None
    receipt_digest: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _required_mapping(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return dict(value)


def _result(
    status: CandidateStatus,
    *,
    current: Path,
    current_digest: str,
    inspection_id: str,
    validation_id: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> CandidateGovernanceResult:
    return CandidateGovernanceResult(
        status=status,
        install_authorized=False,
        canonical_candidate_path=str(current),
        candidate_digest=current_digest,
        inspection_id=inspection_id,
        validation_id=validation_id,
        error_code=error_code,
        error_message=error_message,
    )


def verify_confirmed_candidate(
    candidate_path: str | Path,
    serialized_outcome: Mapping[str, Any],
) -> CandidateGovernanceResult:
    """Recompute Governance and validate its formal receipt against current bytes."""

    current = Path(candidate_path).expanduser().resolve(strict=True)
    if not current.is_dir():
        raise CandidateGovernanceError("canonical Candidate path must be a directory")
    current_digest = digest_tree(current)

    try:
        validation = validation_from_data(
            _required_mapping(serialized_outcome, "validation")
        )
        confirmation = confirmation_from_data(
            _required_mapping(serialized_outcome, "semantic_confirmation")
        )
    except Exception as exc:
        return _result(
            CandidateStatus.GOVERNANCE_ERROR,
            current=current,
            current_digest=current_digest,
            inspection_id="",
            validation_id="",
            error_code="GOVERNANCE_EVIDENCE_INVALID",
            error_message=str(exc),
        )

    try:
        validation_source = validation.source_path.resolve(strict=True)
        validation_artifact = validation.artifact_path.resolve(strict=True)
    except (AttributeError, OSError) as exc:
        raise CandidateGovernanceError(
            "validation source is not the canonical Candidate path"
        ) from exc
    if validation_source != current:
        raise CandidateGovernanceError(
            "validation source is not the canonical Candidate path"
        )
    if validation_artifact != current:
        raise CandidateGovernanceError(
            "validation artifact is not the canonical Candidate path"
        )
    if current_digest != validation.artifact_digest:
        return _result(
            CandidateStatus.INTEGRITY_MISMATCH,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="CANDIDATE_DIGEST_MISMATCH",
            error_message="current Candidate digest differs from validated artifact",
        )

    try:
        recomputed = PipelineOrchestrator().confirm(validation, confirmation)
    except Exception as exc:
        return _result(
            CandidateStatus.GOVERNANCE_ERROR,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="GOVERNANCE_CONFIRMATION_ERROR",
            error_message=str(exc),
        )

    gate = recomputed.gate_result
    if gate.verdict is GateVerdict.ERROR:
        return _result(
            CandidateStatus.GOVERNANCE_ERROR,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="GOVERNANCE_GATE_ERROR",
            error_message="skill-engineering Gate returned ERROR",
        )
    if gate.verdict is GateVerdict.FAIL:
        return _result(
            CandidateStatus.GOVERNANCE_BLOCKED,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="GOVERNANCE_BLOCKED",
            error_message="skill-engineering Gate blocked this Candidate",
        )
    if gate.verdict is GateVerdict.INCOMPLETE:
        return _result(
            CandidateStatus.GOVERNANCE_INCOMPLETE,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="GOVERNANCE_INCOMPLETE",
            error_message="skill-engineering Gate evidence is incomplete",
        )
    if (
        gate.outcome is not GateOutcome.AUDIT_COMPLETE_VALID
        or validation.coverage_status is not CoverageStatus.FULL
        or validation.capability_preservation
        is not CapabilityPreservationStatus.CAPABILITY_PRESERVED
        or confirmation.confirmed_by != "CODEX"
    ):
        return _result(
            CandidateStatus.GOVERNANCE_INCOMPLETE,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="FORMAL_GOVERNANCE_INCOMPLETE",
            error_message="formal AUDIT completion requirements were not met",
        )

    raw_receipt = serialized_outcome.get("completion_receipt")
    if not isinstance(raw_receipt, Mapping):
        return _result(
            CandidateStatus.GOVERNANCE_INCOMPLETE,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="MANAGED_COMPLETION_RECEIPT_REQUIRED",
            error_message="formal ManagedCompletionReceipt is required",
        )
    try:
        submitted_receipt = completion_receipt_from_data(dict(raw_receipt))
        expected_receipt = completion_receipt(recomputed)
        if submitted_receipt != expected_receipt:
            return _result(
                CandidateStatus.INTEGRITY_MISMATCH,
                current=current,
                current_digest=current_digest,
                inspection_id=validation.inspection_id,
                validation_id=validation.validation_id,
                error_code="RECEIPT_OUTCOME_MISMATCH",
                error_message="submitted receipt differs from recomputed Governance receipt",
            )
        validate_completion_receipt(submitted_receipt, recomputed)
        managed = managed_status(current, submitted_receipt)
    except Exception as exc:
        return _result(
            CandidateStatus.GOVERNANCE_INCOMPLETE,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="MANAGED_COMPLETION_INVALID",
            error_message=str(exc),
        )
    if not managed.formal_completion:
        return _result(
            CandidateStatus.INTEGRITY_MISMATCH,
            current=current,
            current_digest=current_digest,
            inspection_id=validation.inspection_id,
            validation_id=validation.validation_id,
            error_code="RECEIPT_CANDIDATE_MISMATCH",
            error_message=managed.reason,
        )

    receipt_digest = canonical_json_digest(to_data(submitted_receipt))
    return CandidateGovernanceResult(
        status=CandidateStatus.GOVERNANCE_PASSED,
        install_authorized=True,
        canonical_candidate_path=str(current),
        candidate_digest=current_digest,
        inspection_id=validation.inspection_id,
        validation_id=validation.validation_id,
        receipt=submitted_receipt,
        receipt_digest=receipt_digest,
    )


__all__ = [
    "CandidateGovernanceError",
    "CandidateGovernanceResult",
    "verify_confirmed_candidate",
]
