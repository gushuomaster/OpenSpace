"""Receipt-gated installation of quarantined Skill Candidates."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from engine.candidate_contract import digest_tree

from openspace.cloud.candidate_governance import (
    CandidateGovernanceError,
    CandidateGovernanceResult,
    verify_confirmed_candidate,
)
from openspace.cloud.candidate_lifecycle import (
    CandidateIntegrityError,
    CandidateManifest,
    CandidateRepository,
    CandidateStatus,
    SourceIntegrityStatus,
    formal_candidate_path,
)
from openspace.cloud.local_mapping import (
    CloudLocalMappingStore,
    CloudSkillBinding,
    utc_now_iso,
)
from openspace.skill_engine.registry import SkillRegistry
from openspace.skill_engine.store import SkillStore


@dataclass(frozen=True, slots=True)
class CandidateInstallResult:
    status: CandidateStatus
    installed: bool
    candidate_id: str
    skill_id: str
    installed_path: str | None = None
    installed_digest: str | None = None
    receipt_digest: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def _result(
    status: CandidateStatus,
    manifest: CandidateManifest,
    *,
    installed: bool = False,
    installed_path: Path | None = None,
    installed_digest: str | None = None,
    receipt_digest: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> CandidateInstallResult:
    return CandidateInstallResult(
        status=status,
        installed=installed,
        candidate_id=manifest.candidate_id,
        skill_id=manifest.final_skill_id,
        installed_path=str(installed_path) if installed_path is not None else None,
        installed_digest=installed_digest,
        receipt_digest=receipt_digest,
        error_code=error_code,
        error_message=error_message,
    )


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first.is_relative_to(second)
        or second.is_relative_to(first)
    )


def _transition_governance_result(
    repository: CandidateRepository,
    manifest: CandidateManifest,
    result: CandidateGovernanceResult,
) -> None:
    state = repository.load_state(manifest.candidate_id)
    if state.status not in {
        CandidateStatus.QUARANTINED,
        CandidateStatus.GOVERNANCE_PENDING,
    }:
        return
    repository.transition(
        manifest.candidate_id,
        expected={state.status},
        next_status=result.status,
        error_code=result.error_code,
        error_message=result.error_message,
    )


def _verify_binding(
    repository: CandidateRepository,
    manifest: CandidateManifest,
    governance: CandidateGovernanceResult,
) -> None:
    binding = repository.load_governance_binding(manifest.candidate_id)
    payload = repository.payload_path(manifest).resolve(strict=True)
    expected = {
        "candidate_id": manifest.candidate_id,
        "candidate_manifest_digest": repository.manifest_digest(manifest.candidate_id),
        "canonical_payload_path": str(payload),
        "candidate_digest": manifest.candidate_digest,
        "inspection_id": governance.inspection_id,
        "validation_id": governance.validation_id,
        "managed_completion_receipt_digest": governance.receipt_digest,
    }
    actual = {
        "candidate_id": binding.candidate_id,
        "candidate_manifest_digest": binding.candidate_manifest_digest,
        "canonical_payload_path": binding.canonical_payload_path,
        "candidate_digest": binding.candidate_digest,
        "inspection_id": binding.inspection_id,
        "validation_id": binding.validation_id,
        "managed_completion_receipt_digest": (
            binding.managed_completion_receipt_digest
        ),
    }
    if actual != expected:
        raise CandidateIntegrityError("Candidate Governance binding changed")


async def install_candidate(
    candidate_id: str,
    serialized_outcome: Mapping[str, Any],
    *,
    repository: CandidateRepository,
    registry: SkillRegistry,
    skill_store: SkillStore,
    mapping_store: CloudLocalMappingStore,
    after_formal_placement: Callable[[Path], None] | None = None,
) -> CandidateInstallResult:
    """Install one Candidate only after recomputing formal Governance PASS."""

    manifest = repository.load_manifest(candidate_id)
    if manifest.candidate_id != candidate_id:
        raise CandidateIntegrityError("Candidate manifest identity changed")
    payload = repository.payload_path(manifest).resolve(strict=True)
    state = repository.load_state(candidate_id)
    if state.status not in {
        CandidateStatus.QUARANTINED,
        CandidateStatus.GOVERNANCE_PENDING,
        CandidateStatus.GOVERNANCE_PASSED,
    }:
        return _result(
            state.status,
            manifest,
            error_code="CANDIDATE_NOT_INSTALLABLE",
            error_message=f"Candidate state is {state.status.value}",
        )

    if manifest.source_integrity_status is not SourceIntegrityStatus.PROVEN:
        source_status = (
            CandidateStatus.INTEGRITY_MISMATCH
            if manifest.source_integrity_status is SourceIntegrityStatus.MISMATCH
            else CandidateStatus.GOVERNANCE_INCOMPLETE
        )
        source_result = CandidateGovernanceResult(
            status=source_status,
            install_authorized=False,
            canonical_candidate_path=str(payload),
            candidate_digest=digest_tree(payload),
            inspection_id="",
            validation_id="",
            error_code="SOURCE_INTEGRITY_NOT_PROVEN",
            error_message=(
                f"Candidate source integrity is {manifest.source_integrity_status.value}"
            ),
        )
        _transition_governance_result(repository, manifest, source_result)
        return _result(
            source_status,
            manifest,
            error_code=source_result.error_code,
            error_message=source_result.error_message,
        )

    try:
        governance = verify_confirmed_candidate(payload, serialized_outcome)
    except CandidateGovernanceError as exc:
        error_result = CandidateGovernanceResult(
            status=CandidateStatus.GOVERNANCE_ERROR,
            install_authorized=False,
            canonical_candidate_path=str(payload),
            candidate_digest=digest_tree(payload),
            inspection_id="",
            validation_id="",
            error_code="GOVERNANCE_CANDIDATE_MISMATCH",
            error_message=str(exc),
        )
        _transition_governance_result(repository, manifest, error_result)
        return _result(
            error_result.status,
            manifest,
            error_code=error_result.error_code,
            error_message=error_result.error_message,
        )
    if not governance.install_authorized:
        _transition_governance_result(repository, manifest, governance)
        return _result(
            governance.status,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code=governance.error_code,
            error_message=governance.error_message,
        )

    final_path = formal_candidate_path(manifest)
    install_parent = Path(manifest.intended_install_parent).expanduser().resolve()
    quarantine_root = repository.state_root.resolve()
    if _paths_overlap(install_parent, quarantine_root):
        return _result(
            CandidateStatus.INSTALL_FAILED,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code="INSTALL_ROOT_OVERLAPS_QUARANTINE",
            error_message="formal install root overlaps Candidate quarantine state",
        )
    if final_path.exists():
        return _result(
            CandidateStatus.INSTALL_FAILED,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code="INSTALL_TARGET_EXISTS",
            error_message=f"formal target already exists: {final_path}",
        )
    if registry.get_skill(manifest.final_skill_id) is not None:
        return _result(
            CandidateStatus.INSTALL_FAILED,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code="SKILL_ID_CONFLICT",
            error_message="Skill ID is already registered",
        )
    if skill_store.load_record(manifest.final_skill_id) is not None:
        return _result(
            CandidateStatus.INSTALL_FAILED,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code="SKILL_STORE_CONFLICT",
            error_message="Skill ID already exists in SkillStore",
        )
    if (
        mapping_store.get_binding_by_local(manifest.final_skill_id) is not None
        or mapping_store.get_binding_by_cloud(manifest.cloud_skill_id) is not None
    ):
        return _result(
            CandidateStatus.INSTALL_FAILED,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code="CLOUD_BINDING_CONFLICT",
            error_message="Cloud/local Skill binding already exists",
        )

    if state.status is CandidateStatus.GOVERNANCE_PASSED:
        _verify_binding(repository, manifest, governance)
    else:
        repository.bind_governance(candidate_id, governance)
    _verify_binding(repository, manifest, governance)
    repository.transition(
        candidate_id,
        expected={CandidateStatus.GOVERNANCE_PASSED},
        next_status=CandidateStatus.INSTALLING,
        receipt_digest=governance.receipt_digest,
    )

    temporary: Path | None = None
    final_created = False
    try:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = final_path.with_name(
            f".{final_path.name}.installing-{uuid.uuid4().hex}"
        )
        shutil.copytree(payload, temporary)
        temporary_digest = digest_tree(temporary)
        if temporary_digest != governance.receipt.candidate_digest:
            raise CandidateIntegrityError("temporary install copy digest changed")
        os.replace(temporary, final_path)
        temporary = None
        final_created = True
        if after_formal_placement is not None:
            after_formal_placement(final_path)
        installed_digest = digest_tree(final_path)
        if installed_digest != governance.receipt.candidate_digest:
            raise CandidateIntegrityError("installed Candidate digest changed")

        meta = registry.load_skill_from_dir(final_path)
        if meta is None:
            raise RuntimeError("Registry parser rejected installed Candidate")
        if meta.skill_id != manifest.final_skill_id:
            raise CandidateIntegrityError("installed Skill ID differs from Candidate manifest")
        if meta.path.parent.resolve() != final_path:
            raise CandidateIntegrityError("Registry parser resolved another Skill path")

        await skill_store.sync_from_registry([meta])
        if skill_store.load_record(manifest.final_skill_id) is None:
            raise RuntimeError("SkillStore did not persist installed Candidate")

        mapping_store.upsert_binding(
            CloudSkillBinding(
                local_skill_id=manifest.final_skill_id,
                cloud_skill_id=manifest.cloud_skill_id,
                local_path=str(final_path),
                package_id_at_pull=manifest.package_id,
                package_path_at_pull=manifest.package_path,
                package_snapshot_version_at_pull=manifest.package_snapshot_version,
                current_package_id=manifest.package_id,
                current_package_path=manifest.package_path,
                manifest_hash=manifest.source_manifest_hash,
                local_content_hash=manifest.local_content_hash,
                sync_state="clean",
                last_pulled_at=manifest.acquired_at,
            )
        )
        mapping_store.upsert_skill_local_classification(
            local_skill_id=manifest.final_skill_id,
            category=manifest.local_category,
            local_category_path=manifest.local_category_path,
            updated_at=utc_now_iso(),
            review_state="reviewed",
            evidence={"candidate_id": manifest.candidate_id},
        )

        registered = registry.register_skill_dir(final_path)
        if registered is None:
            raise RuntimeError("Registry rejected installed Candidate")
        if (
            registered.skill_id != manifest.final_skill_id
            or registered.path.parent.resolve() != final_path
        ):
            raise CandidateIntegrityError("Registry registered another Skill identity")

        repository.transition(
            candidate_id,
            expected={CandidateStatus.INSTALLING},
            next_status=CandidateStatus.INSTALLED,
            installed_path=str(final_path),
            receipt_digest=governance.receipt_digest,
            installed_digest=installed_digest,
        )
        return _result(
            CandidateStatus.INSTALLED,
            manifest,
            installed=True,
            installed_path=final_path,
            installed_digest=installed_digest,
            receipt_digest=governance.receipt_digest,
        )
    except Exception as exc:
        registry.unregister_skill(
            manifest.final_skill_id,
            expected_path=final_path,
        )
        mapping_store.delete_import_state(
            manifest.final_skill_id,
            expected_cloud_skill_id=manifest.cloud_skill_id,
            expected_local_path=final_path,
        )
        store_record = skill_store.load_record(manifest.final_skill_id)
        if (
            store_record is not None
            and Path(store_record.path).expanduser().resolve().parent == final_path
        ):
            await skill_store.delete_record(manifest.final_skill_id)
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        if final_created:
            shutil.rmtree(final_path, ignore_errors=True)
        try:
            repository.transition(
                candidate_id,
                expected={CandidateStatus.INSTALLING},
                next_status=CandidateStatus.INSTALL_FAILED,
                error_code="INSTALL_FAILED",
                error_message=str(exc),
                receipt_digest=governance.receipt_digest,
            )
        except Exception:
            pass
        return _result(
            CandidateStatus.INSTALL_FAILED,
            manifest,
            receipt_digest=governance.receipt_digest,
            error_code="INSTALL_FAILED",
            error_message=str(exc),
        )


__all__ = ["CandidateInstallResult", "install_candidate"]
