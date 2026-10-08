"""Durable records for the two-stage Cloud Skill candidate lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from engine.candidate_contract import digest_tree


_SCHEMA_VERSION = "1.0"


class CandidateIntegrityError(ValueError):
    """Raised when persisted Candidate identity no longer matches its bytes."""


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


@dataclass(frozen=True, slots=True)
class CandidateState:
    schema_version: str
    status: CandidateStatus
    updated_at: str
    error_code: str | None = None
    error_message: str | None = None
    installed_path: str | None = None
    receipt_digest: str | None = None
    installed_digest: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateGovernanceBinding:
    schema_version: str
    candidate_id: str
    candidate_manifest_digest: str
    canonical_payload_path: str
    candidate_digest: str
    inspection_id: str
    validation_id: str
    managed_completion_receipt_digest: str
    bound_at: str


_ALLOWED_TRANSITIONS: Mapping[CandidateStatus, frozenset[CandidateStatus]] = {
    CandidateStatus.QUARANTINED: frozenset(
        {
            CandidateStatus.GOVERNANCE_PENDING,
            CandidateStatus.GOVERNANCE_PASSED,
            CandidateStatus.GOVERNANCE_BLOCKED,
            CandidateStatus.GOVERNANCE_INCOMPLETE,
            CandidateStatus.GOVERNANCE_ERROR,
            CandidateStatus.INTEGRITY_MISMATCH,
        }
    ),
    CandidateStatus.GOVERNANCE_PENDING: frozenset(
        {
            CandidateStatus.GOVERNANCE_PASSED,
            CandidateStatus.GOVERNANCE_BLOCKED,
            CandidateStatus.GOVERNANCE_INCOMPLETE,
            CandidateStatus.GOVERNANCE_ERROR,
            CandidateStatus.INTEGRITY_MISMATCH,
        }
    ),
    CandidateStatus.GOVERNANCE_PASSED: frozenset(
        {CandidateStatus.INSTALLING, CandidateStatus.INTEGRITY_MISMATCH}
    ),
    CandidateStatus.INSTALLING: frozenset(
        {
            CandidateStatus.INSTALLED,
            CandidateStatus.INSTALL_FAILED,
            CandidateStatus.INTEGRITY_MISMATCH,
        }
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_json_digest(value: Any) -> str:
    if hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    encoded = json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_identity(
    *,
    cloud_skill_id: str,
    source_bundle_sha256: str,
    source_manifest_hash: str | None,
    source_integrity_status: SourceIntegrityStatus,
    candidate_digest: str,
    final_skill_id: str,
    final_directory_name: str,
    intended_install_parent: str,
    local_category_path: str,
) -> str:
    parent = os.path.normcase(str(Path(intended_install_parent).expanduser().resolve()))
    digest = canonical_json_digest(
        {
            "schema_version": _SCHEMA_VERSION,
            "cloud_skill_id": str(cloud_skill_id),
            "source_bundle_sha256": str(source_bundle_sha256),
            "source_manifest_hash": source_manifest_hash,
            "source_integrity_status": source_integrity_status,
            "candidate_digest": str(candidate_digest),
            "final_skill_id": str(final_skill_id),
            "final_directory_name": str(final_directory_name),
            "intended_install_parent": parent,
            "local_category_path": str(local_category_path),
        }
    )
    return f"candidate_{digest}"


def formal_candidate_path(manifest: CandidateManifest) -> Path:
    """Return the only formal directory owned by a Candidate manifest."""

    install_parent = Path(manifest.intended_install_parent).expanduser().resolve()
    category = PurePosixPath(manifest.local_category_path.replace("\\", "/"))
    if category.is_absolute() or any(
        part in {"", ".", ".."} for part in category.parts
    ):
        raise CandidateIntegrityError("Candidate placement is not a safe relative path")
    target = install_parent.joinpath(
        *category.parts, manifest.final_directory_name
    ).resolve()
    if not target.is_relative_to(install_parent):
        raise CandidateIntegrityError("Candidate placement escapes intended install root")
    return target


def _manifest_to_data(manifest: CandidateManifest) -> dict[str, Any]:
    data = asdict(manifest)
    data["source_integrity_status"] = manifest.source_integrity_status.value
    return data


def _state_to_data(state: CandidateState) -> dict[str, Any]:
    data = asdict(state)
    data["status"] = state.status.value
    return data


def _binding_to_data(binding: CandidateGovernanceBinding) -> dict[str, Any]:
    return asdict(binding)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class CandidateRepository:
    """Own Candidate files outside every formal Skill root."""

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.quarantine_root = self.state_root / "quarantine"

    def candidate_dir(self, candidate_id: str) -> Path:
        if not candidate_id.startswith("candidate_") or any(
            separator in candidate_id for separator in ("/", "\\")
        ):
            raise ValueError("invalid candidate_id")
        return self.quarantine_root / candidate_id

    def payload_path(self, manifest: CandidateManifest) -> Path:
        return self.candidate_dir(manifest.candidate_id) / "payload" / manifest.final_directory_name

    def manifest_path(self, candidate_id: str) -> Path:
        return self.candidate_dir(candidate_id) / "candidate-manifest.json"

    def state_path(self, candidate_id: str) -> Path:
        return self.candidate_dir(candidate_id) / "state.json"

    def governance_binding_path(self, candidate_id: str) -> Path:
        return self.candidate_dir(candidate_id) / "governance" / "candidate-binding.json"

    def candidate_ids(self) -> tuple[str, ...]:
        """Enumerate persisted Candidate record names without loading their contents."""

        if not self.quarantine_root.is_dir():
            return ()
        return tuple(
            sorted(
                entry.name
                for entry in self.quarantine_root.iterdir()
                if entry.name.startswith("candidate_")
            )
        )

    def quarantine(
        self,
        prepared_skill: str | Path,
        *,
        cloud_skill_id: str,
        source_bundle_sha256: str,
        source_manifest_hash: str | None,
        source_integrity_status: SourceIntegrityStatus,
        local_content_hash: str,
        final_skill_id: str,
        intended_install_parent: str | Path,
        local_category: str,
        local_category_path: str,
        package_id: str | None,
        package_path: str | None,
        package_snapshot_version: str | None,
        acquired_at: str,
    ) -> CandidateManifest:
        source = Path(prepared_skill).expanduser().resolve(strict=True)
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            raise ValueError("prepared Candidate must be a Skill directory")
        candidate_digest = digest_tree(source)
        install_parent = Path(intended_install_parent).expanduser().resolve()
        candidate_id = candidate_identity(
            cloud_skill_id=cloud_skill_id,
            source_bundle_sha256=source_bundle_sha256,
            source_manifest_hash=source_manifest_hash,
            source_integrity_status=source_integrity_status,
            candidate_digest=candidate_digest,
            final_skill_id=final_skill_id,
            final_directory_name=source.name,
            intended_install_parent=str(install_parent),
            local_category_path=local_category_path,
        )
        manifest = CandidateManifest(
            _SCHEMA_VERSION,
            candidate_id,
            cloud_skill_id,
            source_bundle_sha256,
            source_manifest_hash,
            source_integrity_status,
            candidate_digest,
            local_content_hash,
            final_skill_id,
            source.name,
            str(install_parent),
            local_category,
            local_category_path,
            package_id,
            package_path,
            package_snapshot_version,
            acquired_at,
        )
        destination = self.candidate_dir(candidate_id)
        if destination.exists():
            existing = self.load_manifest(candidate_id)
            current_digest = digest_tree(self.payload_path(existing))
            if current_digest != existing.candidate_digest:
                raise CandidateIntegrityError("persisted Candidate payload digest changed")
            if existing.candidate_digest != candidate_digest:
                raise CandidateIntegrityError("Candidate payload digest does not match acquisition")
            if candidate_identity(
                cloud_skill_id=existing.cloud_skill_id,
                source_bundle_sha256=existing.source_bundle_sha256,
                source_manifest_hash=existing.source_manifest_hash,
                source_integrity_status=existing.source_integrity_status,
                candidate_digest=existing.candidate_digest,
                final_skill_id=existing.final_skill_id,
                final_directory_name=existing.final_directory_name,
                intended_install_parent=existing.intended_install_parent,
                local_category_path=existing.local_category_path,
            ) != candidate_id:
                raise CandidateIntegrityError("persisted Candidate identity changed")
            return existing

        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        acquiring = self.quarantine_root / f".acquiring-{uuid.uuid4().hex}"
        payload = acquiring / "payload" / source.name
        try:
            payload.parent.mkdir(parents=True)
            shutil.copytree(source, payload)
            _atomic_write_json(acquiring / "candidate-manifest.json", _manifest_to_data(manifest))
            _atomic_write_json(
                acquiring / "state.json",
                _state_to_data(
                    CandidateState(_SCHEMA_VERSION, CandidateStatus.QUARANTINED, acquired_at)
                ),
            )
            os.replace(acquiring, destination)
        except Exception:
            shutil.rmtree(acquiring, ignore_errors=True)
            raise
        return manifest

    def load_manifest(self, candidate_id: str) -> CandidateManifest:
        payload = json.loads(self.manifest_path(candidate_id).read_text(encoding="utf-8"))
        return CandidateManifest(
            schema_version=str(payload["schema_version"]),
            candidate_id=str(payload["candidate_id"]),
            cloud_skill_id=str(payload["cloud_skill_id"]),
            source_bundle_sha256=str(payload["source_bundle_sha256"]),
            source_manifest_hash=payload.get("source_manifest_hash"),
            source_integrity_status=SourceIntegrityStatus(payload["source_integrity_status"]),
            candidate_digest=str(payload["candidate_digest"]),
            local_content_hash=str(payload["local_content_hash"]),
            final_skill_id=str(payload["final_skill_id"]),
            final_directory_name=str(payload["final_directory_name"]),
            intended_install_parent=str(payload["intended_install_parent"]),
            local_category=str(payload["local_category"]),
            local_category_path=str(payload["local_category_path"]),
            package_id=payload.get("package_id"),
            package_path=payload.get("package_path"),
            package_snapshot_version=payload.get("package_snapshot_version"),
            acquired_at=str(payload["acquired_at"]),
        )

    def manifest_digest(self, candidate_id: str) -> str:
        return canonical_json_digest(self.load_manifest(candidate_id))

    def load_state(self, candidate_id: str) -> CandidateState:
        payload = json.loads(self.state_path(candidate_id).read_text(encoding="utf-8"))
        return CandidateState(
            schema_version=str(payload["schema_version"]),
            status=CandidateStatus(payload["status"]),
            updated_at=str(payload["updated_at"]),
            error_code=payload.get("error_code"),
            error_message=payload.get("error_message"),
            installed_path=payload.get("installed_path"),
            receipt_digest=payload.get("receipt_digest"),
            installed_digest=payload.get("installed_digest"),
        )

    def load_governance_binding(
        self,
        candidate_id: str,
    ) -> CandidateGovernanceBinding:
        payload = json.loads(
            self.governance_binding_path(candidate_id).read_text(encoding="utf-8")
        )
        return CandidateGovernanceBinding(
            schema_version=str(payload["schema_version"]),
            candidate_id=str(payload["candidate_id"]),
            candidate_manifest_digest=str(payload["candidate_manifest_digest"]),
            canonical_payload_path=str(payload["canonical_payload_path"]),
            candidate_digest=str(payload["candidate_digest"]),
            inspection_id=str(payload["inspection_id"]),
            validation_id=str(payload["validation_id"]),
            managed_completion_receipt_digest=str(
                payload["managed_completion_receipt_digest"]
            ),
            bound_at=str(payload["bound_at"]),
        )

    def bind_governance(
        self,
        candidate_id: str,
        result: Any,
        *,
        bound_at: str | None = None,
    ) -> CandidateGovernanceBinding:
        if (
            getattr(result, "status", None) is not CandidateStatus.GOVERNANCE_PASSED
            or not getattr(result, "install_authorized", False)
            or getattr(result, "receipt", None) is None
            or not getattr(result, "receipt_digest", None)
        ):
            raise ValueError("only verified formal Governance PASS can be bound")

        manifest = self.load_manifest(candidate_id)
        if manifest.candidate_id != candidate_id:
            raise CandidateIntegrityError("Candidate manifest identity changed")
        recomputed_id = candidate_identity(
            cloud_skill_id=manifest.cloud_skill_id,
            source_bundle_sha256=manifest.source_bundle_sha256,
            source_manifest_hash=manifest.source_manifest_hash,
            source_integrity_status=manifest.source_integrity_status,
            candidate_digest=manifest.candidate_digest,
            final_skill_id=manifest.final_skill_id,
            final_directory_name=manifest.final_directory_name,
            intended_install_parent=manifest.intended_install_parent,
            local_category_path=manifest.local_category_path,
        )
        if recomputed_id != candidate_id:
            raise CandidateIntegrityError("Candidate manifest identity changed")
        if manifest.source_integrity_status is not SourceIntegrityStatus.PROVEN:
            raise ValueError("Candidate source integrity is not PROVEN")

        payload = self.payload_path(manifest).resolve(strict=True)
        current_digest = digest_tree(payload)
        if current_digest != manifest.candidate_digest:
            raise CandidateIntegrityError("Candidate payload digest changed")
        if str(payload) != str(getattr(result, "canonical_candidate_path", "")):
            raise CandidateIntegrityError("Governance result targets another Candidate path")
        if current_digest != getattr(result, "candidate_digest", None):
            raise CandidateIntegrityError("Governance result targets another Candidate digest")
        receipt = result.receipt
        if receipt.candidate_digest != current_digest:
            raise CandidateIntegrityError("Governance receipt targets another Candidate digest")
        if receipt.inspection_id != getattr(result, "inspection_id", None):
            raise CandidateIntegrityError("Governance inspection identity changed")

        state = self.load_state(candidate_id)
        bindable_states = {
            CandidateStatus.QUARANTINED,
            CandidateStatus.GOVERNANCE_PENDING,
        }
        if state.status not in bindable_states:
            raise ValueError(f"Candidate state is not bindable: {state.status.value}")
        path = self.governance_binding_path(candidate_id)
        if path.exists():
            raise CandidateIntegrityError("Candidate already has a Governance binding")

        binding = CandidateGovernanceBinding(
            schema_version=_SCHEMA_VERSION,
            candidate_id=candidate_id,
            candidate_manifest_digest=self.manifest_digest(candidate_id),
            canonical_payload_path=str(payload),
            candidate_digest=current_digest,
            inspection_id=result.inspection_id,
            validation_id=result.validation_id,
            managed_completion_receipt_digest=result.receipt_digest,
            bound_at=bound_at or _utc_now(),
        )
        _atomic_write_json(path, _binding_to_data(binding))
        try:
            self.transition(
                candidate_id,
                expected=bindable_states,
                next_status=CandidateStatus.GOVERNANCE_PASSED,
                receipt_digest=result.receipt_digest,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return binding

    def transition(
        self,
        candidate_id: str,
        *,
        expected: Iterable[CandidateStatus],
        next_status: CandidateStatus,
        error_code: str | None = None,
        error_message: str | None = None,
        installed_path: str | None = None,
        receipt_digest: str | None = None,
        installed_digest: str | None = None,
        updated_at: str | None = None,
    ) -> CandidateState:
        current = self.load_state(candidate_id)
        expected_set = frozenset(expected)
        if current.status not in expected_set:
            expected_text = ", ".join(sorted(item.value for item in expected_set))
            raise ValueError(
                f"Candidate state is {current.status.value}; expected {expected_text}"
            )
        if next_status not in _ALLOWED_TRANSITIONS.get(current.status, frozenset()):
            raise ValueError(
                f"invalid Candidate transition: {current.status.value} -> {next_status.value}"
            )
        state = CandidateState(
            _SCHEMA_VERSION,
            next_status,
            updated_at or _utc_now(),
            error_code,
            error_message,
            installed_path,
            receipt_digest,
            installed_digest,
        )
        _atomic_write_json(self.state_path(candidate_id), _state_to_data(state))
        return state


__all__ = [
    "CandidateGovernanceBinding",
    "CandidateIntegrityError",
    "CandidateManifest",
    "CandidateRepository",
    "CandidateState",
    "CandidateStatus",
    "SourceIntegrityStatus",
    "candidate_identity",
    "canonical_json_digest",
    "formal_candidate_path",
]
