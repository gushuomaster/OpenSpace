from __future__ import annotations

import importlib
import json
import os
import shutil
from pathlib import Path

import pytest

from openspace.cloud.candidate_lifecycle import (
    CandidateRepository,
    CandidateStatus,
    SourceIntegrityStatus,
)


def _write_skill(path: Path, *, skill_id: str = "demo__imp_12345678") -> Path:
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Visibility test Skill.\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    (path / ".skill_id").write_text(skill_id + "\n", encoding="utf-8")
    return path


def _quarantine(
    tmp_path: Path,
    *,
    cloud_skill_id: str = "cloud-1",
    source_bundle_sha256: str = "1" * 64,
) -> tuple[CandidateRepository, object]:
    repository = CandidateRepository(tmp_path / "state" / "candidates")
    prepared = _write_skill(tmp_path / "prepared" / cloud_skill_id / "demo")
    manifest = repository.quarantine(
        prepared,
        cloud_skill_id=cloud_skill_id,
        source_bundle_sha256=source_bundle_sha256,
        source_manifest_hash="sha256:" + "2" * 64,
        source_integrity_status=SourceIntegrityStatus.PROVEN,
        local_content_hash="sha256:" + "3" * 64,
        final_skill_id="demo__imp_12345678",
        intended_install_parent=tmp_path / "formal-skills",
        local_category="tool",
        local_category_path="technology/computing",
        package_id="package-1",
        package_path="technology/computing",
        package_snapshot_version="snapshot-1",
        acquired_at="2026-10-08T00:00:00Z",
    )
    return repository, manifest


def _policy(repository: CandidateRepository):
    module = importlib.import_module("openspace.cloud.candidate_visibility")
    return module.CandidateVisibilityPolicy(repository)


def _formal_path(manifest: object) -> Path:
    return (
        Path(manifest.intended_install_parent)
        / "technology"
        / "computing"
        / manifest.final_directory_name
    )


def _mark_installed(
    repository: CandidateRepository,
    manifest: object,
    *,
    installed_path: Path | None = None,
) -> Path:
    installed = installed_path or _formal_path(manifest)
    installed.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repository.payload_path(manifest), installed)
    receipt_digest = "4" * 64
    binding_path = repository.governance_binding_path(manifest.candidate_id)
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    binding_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "candidate_id": manifest.candidate_id,
                "candidate_manifest_digest": repository.manifest_digest(
                    manifest.candidate_id
                ),
                "canonical_payload_path": str(
                    repository.payload_path(manifest).resolve(strict=True)
                ),
                "candidate_digest": manifest.candidate_digest,
                "inspection_id": "inspection-1",
                "validation_id": "validation-1",
                "managed_completion_receipt_digest": receipt_digest,
                "bound_at": "2026-10-08T00:01:00Z",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    repository.transition(
        manifest.candidate_id,
        expected={CandidateStatus.QUARANTINED},
        next_status=CandidateStatus.GOVERNANCE_PASSED,
        receipt_digest=receipt_digest,
    )
    repository.transition(
        manifest.candidate_id,
        expected={CandidateStatus.GOVERNANCE_PASSED},
        next_status=CandidateStatus.INSTALLING,
        receipt_digest=receipt_digest,
    )
    repository.transition(
        manifest.candidate_id,
        expected={CandidateStatus.INSTALLING},
        next_status=CandidateStatus.INSTALLED,
        installed_path=str(installed.resolve()),
        receipt_digest=receipt_digest,
        installed_digest=manifest.candidate_digest,
    )
    return installed


def test_quarantined_payload_is_rejected(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)

    decision = _policy(repository).inspect(repository.payload_path(manifest))

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_QUARANTINED"
    assert decision.candidate_id == manifest.candidate_id


def test_non_installed_formal_path_is_rejected(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)
    formal_path = _write_skill(_formal_path(manifest))

    decision = _policy(repository).inspect(formal_path)

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_NOT_INSTALLED"
    assert decision.candidate_id == manifest.candidate_id


def test_interrupted_install_temporary_path_is_rejected(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)
    formal_path = _formal_path(manifest)
    temporary = formal_path.with_name(
        f".{formal_path.name}.installing-{manifest.candidate_id}-{'a' * 32}"
    )
    shutil.copytree(repository.payload_path(manifest), temporary)

    decision = _policy(repository).inspect(temporary)

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_INSTALL_TEMPORARY"


def test_nested_skill_under_interrupted_install_temporary_is_rejected(
    tmp_path: Path,
) -> None:
    repository, manifest = _quarantine(tmp_path)
    formal_path = _formal_path(manifest)
    temporary = formal_path.with_name(
        f".{formal_path.name}.installing-{manifest.candidate_id}-{'a' * 32}"
    )
    nested = _write_skill(temporary / "nested" / "skill")

    decision = _policy(repository).inspect(nested)

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_INSTALL_TEMPORARY"


def test_inspection_only_bundle_is_rejected(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "state" / "candidates")
    skill = _write_skill(tmp_path / "cloud-packages" / "pkg" / "skill")
    (skill.parent / ".cloud_package.json").write_text(
        '{"inspection_only": true}\n', encoding="utf-8"
    )

    decision = _policy(repository).inspect(skill)

    assert decision.allowed is False
    assert decision.code == "INSPECTION_ONLY_PACKAGE"


def test_malformed_inspection_marker_fails_closed(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "state" / "candidates")
    skill = _write_skill(tmp_path / "cloud-packages" / "pkg" / "skill")
    (skill.parent / ".cloud_package.json").write_text("{", encoding="utf-8")

    decision = _policy(repository).inspect(skill)

    assert decision.allowed is False
    assert decision.code == "INVALID_INSPECTION_MARKER"


def test_ordinary_local_skill_is_allowed(tmp_path: Path) -> None:
    repository = CandidateRepository(tmp_path / "state" / "candidates")
    skill = _write_skill(tmp_path / "local" / "skill")

    decision = _policy(repository).inspect(skill)

    assert decision.allowed is True
    assert decision.code == "ORDINARY_LOCAL_SKILL"
    assert decision.candidate_id is None


def test_installed_candidate_is_allowed_only_for_owned_path(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)
    installed = _mark_installed(repository, manifest)
    foreign_copy = tmp_path / "foreign" / "demo"
    shutil.copytree(installed, foreign_copy)

    installed_decision = _policy(repository).inspect(installed)
    foreign_decision = _policy(repository).inspect(foreign_copy)

    assert installed_decision.allowed is True
    assert installed_decision.code == "INSTALLED_CANDIDATE"
    assert installed_decision.candidate_id == manifest.candidate_id
    assert foreign_decision.allowed is True
    assert foreign_decision.code == "ORDINARY_LOCAL_SKILL"


def test_corrupt_candidate_manifest_fails_closed_for_quarantine_path(
    tmp_path: Path,
) -> None:
    repository, manifest = _quarantine(tmp_path)
    repository.manifest_path(manifest.candidate_id).write_text("{", encoding="utf-8")

    decision = _policy(repository).inspect(repository.payload_path(manifest))

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_RECORD_INVALID"
    assert decision.candidate_id == manifest.candidate_id


def test_corrupt_candidate_state_fails_closed_for_formal_path(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)
    formal_path = _write_skill(_formal_path(manifest))
    repository.state_path(manifest.candidate_id).write_text("{", encoding="utf-8")

    decision = _policy(repository).inspect(formal_path)

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_RECORD_INVALID"
    assert decision.candidate_id == manifest.candidate_id


def test_ambiguous_formal_path_ownership_fails_closed(tmp_path: Path) -> None:
    repository, first = _quarantine(tmp_path, cloud_skill_id="cloud-1")
    same_repository, second = _quarantine(
        tmp_path,
        cloud_skill_id="cloud-2",
        source_bundle_sha256="5" * 64,
    )
    assert same_repository.state_root == repository.state_root
    formal_path = _write_skill(_formal_path(first))

    decision = _policy(repository).inspect(formal_path)

    assert first.candidate_id != second.candidate_id
    assert decision.allowed is False
    assert decision.code == "CANDIDATE_OWNERSHIP_AMBIGUOUS"
    assert decision.candidate_id is None


def test_alternate_path_to_quarantine_payload_is_rejected(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)
    payload = repository.payload_path(manifest)
    spelled_differently = payload.parent / ".." / "payload" / payload.name

    decision = _policy(repository).inspect(spelled_differently)

    assert os.path.normpath(str(spelled_differently)) != str(spelled_differently)
    assert decision.allowed is False
    assert decision.code == "CANDIDATE_QUARANTINED"


def test_symlink_to_quarantine_payload_is_rejected(tmp_path: Path) -> None:
    repository, manifest = _quarantine(tmp_path)
    link = tmp_path / "local" / "linked-skill"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(repository.payload_path(manifest), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    decision = _policy(repository).inspect(link)

    assert decision.allowed is False
    assert decision.code == "CANDIDATE_QUARANTINED"
