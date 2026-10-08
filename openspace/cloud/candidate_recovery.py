"""Bounded startup reconciliation for interrupted Candidate installations."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from engine.candidate_contract import digest_tree

from openspace.cloud.candidate_lifecycle import (
    CandidateManifest,
    CandidateRepository,
    CandidateStatus,
    SourceIntegrityStatus,
    candidate_identity,
    formal_candidate_path,
)
from openspace.cloud.candidate_visibility import CandidateVisibilityPolicy
from openspace.cloud.local_mapping import (
    CloudLocalMappingStore,
    CloudSkillBinding,
    utc_now_iso,
)
from openspace.skill_engine.registry import SkillRegistry
from openspace.skill_engine.store import SkillStore


@dataclass(frozen=True, slots=True)
class CandidateRecoveryResult:
    candidate_id: str
    status: CandidateStatus
    error_code: str | None = None
    error_message: str | None = None


class _RecoveryMismatch(ValueError):
    def __init__(self, code: str, message: str, *, integrity: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.integrity = integrity


def _resolved_parent(path: str | Path) -> Path:
    return Path(path).expanduser().resolve().parent


async def _cleanup_owned(
    manifest: CandidateManifest,
    final_path: Path,
    *,
    registry: SkillRegistry,
    skill_store: SkillStore,
    mapping_store: CloudLocalMappingStore,
) -> None:
    """Remove only metadata still pointing to this Candidate's exact placement."""

    registry.unregister_skill(manifest.final_skill_id, expected_path=final_path)
    mapping_store.delete_import_state(
        manifest.final_skill_id,
        expected_cloud_skill_id=manifest.cloud_skill_id,
        expected_local_path=final_path,
    )
    record = skill_store.load_record(manifest.final_skill_id)
    if record is not None and record.is_active and _resolved_parent(record.path) == final_path:
        await skill_store.delete_record(manifest.final_skill_id)


def _cleanup_install_temporaries(
    final_path: Path,
    candidate_id: str,
) -> None:
    """Remove only the current Candidate's reserved install staging paths."""

    pattern = re.compile(
        rf"\.{re.escape(final_path.name)}\.installing-"
        rf"{re.escape(candidate_id)}-[0-9a-f]{{32}}"
    )
    if not final_path.parent.is_dir():
        return
    for entry in final_path.parent.iterdir():
        if pattern.fullmatch(entry.name) is None:
            continue
        if entry.is_symlink() or not entry.is_dir():
            entry.unlink(missing_ok=True)
        else:
            shutil.rmtree(entry, ignore_errors=True)


def _verify_identity(repository: CandidateRepository, candidate_id: str) -> tuple[CandidateManifest, Path]:
    manifest = repository.load_manifest(candidate_id)
    if (
        manifest.schema_version != "1.0"
        or manifest.candidate_id != candidate_id
        or manifest.source_integrity_status is not SourceIntegrityStatus.PROVEN
        or candidate_identity(
            cloud_skill_id=manifest.cloud_skill_id,
            source_bundle_sha256=manifest.source_bundle_sha256,
            source_manifest_hash=manifest.source_manifest_hash,
            source_integrity_status=manifest.source_integrity_status,
            candidate_digest=manifest.candidate_digest,
            final_skill_id=manifest.final_skill_id,
            final_directory_name=manifest.final_directory_name,
            intended_install_parent=manifest.intended_install_parent,
            local_category_path=manifest.local_category_path,
        ) != candidate_id
    ):
        raise _RecoveryMismatch("CANDIDATE_IDENTITY_MISMATCH", "Candidate manifest identity changed")
    final_path = formal_candidate_path(manifest)
    if final_path.name != manifest.final_directory_name:
        raise _RecoveryMismatch("FORMAL_PATH_INVALID", "Candidate formal path changed")
    decision = CandidateVisibilityPolicy(repository).inspect(final_path)
    if decision.code != "CANDIDATE_NOT_INSTALLED" or decision.candidate_id != candidate_id:
        raise _RecoveryMismatch("FORMAL_PATH_OWNERSHIP_MISMATCH", decision.code)
    return manifest, final_path


def _verify_evidence(repository: CandidateRepository, manifest: CandidateManifest, state_receipt: str) -> None:
    candidate_id = manifest.candidate_id
    payload = repository.payload_path(manifest).resolve(strict=True)
    if not payload.is_dir() or digest_tree(payload) != manifest.candidate_digest:
        raise _RecoveryMismatch("CANDIDATE_DIGEST_MISMATCH", "Candidate payload bytes changed")
    binding = repository.load_governance_binding(candidate_id)
    if (
        binding.schema_version != "1.0"
        or binding.candidate_id != candidate_id
        or binding.candidate_manifest_digest != repository.manifest_digest(candidate_id)
        or Path(binding.canonical_payload_path).expanduser().resolve(strict=True) != payload
        or binding.candidate_digest != manifest.candidate_digest
        or not binding.inspection_id
        or not binding.validation_id
        or not re.fullmatch(r"[0-9a-f]{64}", state_receipt or "")
        or binding.managed_completion_receipt_digest != state_receipt
    ):
        raise _RecoveryMismatch("GOVERNANCE_BINDING_MISMATCH", "Candidate Governance binding or receipt changed")


def _verify_formal_bytes(manifest: CandidateManifest, final_path: Path) -> None:
    if not final_path.is_dir():
        raise _RecoveryMismatch("FORMAL_PATH_MISSING", "Candidate formal path is missing", integrity=False)
    try:
        installed_id = (final_path / ".skill_id").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise _RecoveryMismatch("FORMAL_PATH_OWNERSHIP_MISMATCH", str(exc)) from exc
    if installed_id != manifest.final_skill_id:
        raise _RecoveryMismatch("FORMAL_PATH_OWNERSHIP_MISMATCH", "formal Skill ID belongs to another asset")
    if digest_tree(final_path) != manifest.candidate_digest:
        raise _RecoveryMismatch("INSTALLED_DIGEST_MISMATCH", "installed Candidate bytes changed")


def _verify_visibility_ownership(
    manifest: CandidateManifest,
    final_path: Path,
    *,
    registry: SkillRegistry,
    skill_store: SkillStore,
    mapping_store: CloudLocalMappingStore,
) -> None:
    skill_id = manifest.final_skill_id
    for meta in registry.list_skills():
        if meta.path.parent.resolve() == final_path and meta.skill_id != skill_id:
            raise _RecoveryMismatch("REGISTRY_PATH_CONFLICT", "another Skill occupies formal path", integrity=False)
        if meta.skill_id == skill_id and meta.path.parent.resolve() != final_path:
            raise _RecoveryMismatch("REGISTRY_ID_CONFLICT", "Skill ID belongs to another path", integrity=False)
    for record in skill_store.load_all().values():
        record_parent = _resolved_parent(record.path)
        if record_parent == final_path and record.skill_id != skill_id:
            raise _RecoveryMismatch("STORE_PATH_CONFLICT", "another SkillStore record occupies path", integrity=False)
        if record.skill_id == skill_id and record_parent != final_path:
            raise _RecoveryMismatch("STORE_ID_CONFLICT", "SkillStore ID belongs to another path", integrity=False)
        if record.skill_id == skill_id and not record.is_active:
            raise _RecoveryMismatch("STORE_INACTIVE_CONFLICT", "SkillStore record is inactive", integrity=False)
    local = mapping_store.get_binding_by_local(skill_id)
    cloud = mapping_store.get_binding_by_cloud(manifest.cloud_skill_id)
    for binding in (local, cloud):
        if binding is not None and (
            binding.local_skill_id != skill_id
            or binding.cloud_skill_id != manifest.cloud_skill_id
            or Path(binding.local_path).expanduser().resolve() != final_path
        ):
            raise _RecoveryMismatch("CLOUD_BINDING_CONFLICT", "Cloud/local binding belongs to another asset", integrity=False)
    classification = mapping_store.get_skill_local_classification(skill_id)
    if classification is not None and classification.evidence != {"candidate_id": manifest.candidate_id}:
        raise _RecoveryMismatch("CLASSIFICATION_CONFLICT", "classification belongs to another asset", integrity=False)


async def _reconcile_one(
    candidate_id: str,
    *,
    repository: CandidateRepository,
    registry: SkillRegistry,
    skill_store: SkillStore,
    mapping_store: CloudLocalMappingStore,
) -> CandidateRecoveryResult:
    manifest: CandidateManifest | None = None
    final_path: Path | None = None
    try:
        manifest, final_path = _verify_identity(repository, candidate_id)
        state = repository.load_state(candidate_id)
        _verify_evidence(repository, manifest, state.receipt_digest or "")
        _verify_formal_bytes(manifest, final_path)
        _verify_visibility_ownership(
            manifest, final_path,
            registry=registry, skill_store=skill_store, mapping_store=mapping_store,
        )
    except Exception as exc:
        mismatch = exc if isinstance(exc, _RecoveryMismatch) else _RecoveryMismatch(
            "CANDIDATE_RECORD_INVALID", str(exc)
        )
        status = CandidateStatus.INTEGRITY_MISMATCH if mismatch.integrity else CandidateStatus.INSTALL_FAILED
        if manifest is not None and final_path is not None:
            _cleanup_install_temporaries(final_path, manifest.candidate_id)
            await _cleanup_owned(
                manifest, final_path,
                registry=registry, skill_store=skill_store, mapping_store=mapping_store,
            )
        repository.transition(
            candidate_id,
            expected={CandidateStatus.INSTALLING},
            next_status=status,
            error_code=mismatch.code,
            error_message=str(mismatch),
        )
        return CandidateRecoveryResult(candidate_id, status, mismatch.code, str(mismatch))

    try:
        meta = registry.load_skill_from_dir(final_path)
        if meta is None or meta.skill_id != manifest.final_skill_id or meta.path.parent.resolve() != final_path:
            raise _RecoveryMismatch("REGISTRY_PARSE_MISMATCH", "Registry parsed another Skill identity")
        await skill_store.sync_from_registry([meta])
        record = skill_store.load_record(manifest.final_skill_id)
        if record is None or not record.is_active or _resolved_parent(record.path) != final_path:
            raise RuntimeError("SkillStore did not persist the Candidate")
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
            evidence={"candidate_id": candidate_id},
        )
        registered = registry.register_skill_dir(final_path)
        if registered is None or registered.skill_id != manifest.final_skill_id or registered.path.parent.resolve() != final_path:
            raise RuntimeError("Registry rejected installed Candidate")
        repository.transition(
            candidate_id,
            expected={CandidateStatus.INSTALLING},
            next_status=CandidateStatus.INSTALLED,
            installed_path=str(final_path),
            installed_digest=manifest.candidate_digest,
            receipt_digest=state.receipt_digest,
        )
        return CandidateRecoveryResult(candidate_id, CandidateStatus.INSTALLED)
    except Exception as exc:
        try:
            persisted_status = repository.load_state(candidate_id).status
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as state_exc:
            raise RuntimeError("Candidate terminal state is unreadable after recovery interruption") from state_exc
        if persisted_status is CandidateStatus.INSTALLED:
            decision = CandidateVisibilityPolicy(repository).inspect(final_path)
            if decision.allowed:
                return CandidateRecoveryResult(candidate_id, CandidateStatus.INSTALLED)
            raise RuntimeError(f"Candidate visibility rejected after terminal write: {decision.code}") from exc
        await _cleanup_owned(
            manifest, final_path,
            registry=registry, skill_store=skill_store, mapping_store=mapping_store,
        )
        _cleanup_install_temporaries(final_path, manifest.candidate_id)
        return CandidateRecoveryResult(
            candidate_id, CandidateStatus.INSTALLING, "RECOVERY_INTERRUPTED", str(exc)
        )


async def reconcile_installing_candidates(
    *,
    repository: CandidateRepository,
    registry: SkillRegistry,
    skill_store: SkillStore,
    mapping_store: CloudLocalMappingStore,
) -> Sequence[CandidateRecoveryResult]:
    """Replay only persisted INSTALLING Candidates before runtime publication."""

    results: list[CandidateRecoveryResult] = []
    for candidate_id in repository.candidate_ids():
        try:
            state = repository.load_state(candidate_id)
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            results.append(CandidateRecoveryResult(candidate_id, CandidateStatus.INSTALL_FAILED, "CANDIDATE_RECORD_INVALID", str(exc)))
            continue
        if state.status is CandidateStatus.INSTALLING:
            results.append(
                await _reconcile_one(
                    candidate_id,
                    repository=repository,
                    registry=registry,
                    skill_store=skill_store,
                    mapping_store=mapping_store,
                )
            )
    return tuple(results)


__all__ = ["CandidateRecoveryResult", "reconcile_installing_candidates"]
