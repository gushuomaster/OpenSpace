from __future__ import annotations

import json
from pathlib import Path

import pytest

from openspace.cloud.candidate_lifecycle import (
    CandidateIntegrityError,
    CandidateRepository,
    CandidateStatus,
    SourceIntegrityStatus,
    candidate_identity,
)


@pytest.fixture
def prepared_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "prepared" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo candidate\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    (skill / ".skill_id").write_text("demo__imp_12345678\n", encoding="utf-8")
    (skill / ".cloud_skill.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cloud_skill_id": "cloud-1",
                "local_skill_id": "demo__imp_12345678",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return skill


def _quarantine(
    repository: CandidateRepository,
    prepared_skill: Path,
    install_root: Path,
):
    return repository.quarantine(
        prepared_skill,
        cloud_skill_id="cloud-1",
        source_bundle_sha256="1" * 64,
        source_manifest_hash="sha256:" + "1" * 64,
        source_integrity_status=SourceIntegrityStatus.PROVEN,
        local_content_hash="sha256:" + "3" * 64,
        final_skill_id="demo__imp_12345678",
        intended_install_parent=install_root,
        local_category="tool",
        local_category_path="technology/computing",
        package_id="package-1",
        package_path="technology/computing",
        package_snapshot_version="snapshot-1",
        acquired_at="2026-09-30T00:00:00Z",
    )


def test_candidate_identity_binds_source_proof_and_placement_but_not_timestamp(
    tmp_path: Path,
) -> None:
    values = {
        "cloud_skill_id": "cloud-1",
        "source_bundle_sha256": "1" * 64,
        "source_manifest_hash": "sha256:" + "1" * 64,
        "source_integrity_status": SourceIntegrityStatus.PROVEN,
        "candidate_digest": "2" * 64,
        "final_skill_id": "demo__imp_12345678",
        "final_directory_name": "demo",
        "intended_install_parent": str(tmp_path / "skills"),
        "local_category_path": "technology/computing",
    }

    assert candidate_identity(**values) == candidate_identity(**values)
    assert candidate_identity(**values) != candidate_identity(
        **{**values, "source_integrity_status": SourceIntegrityStatus.UNPROVEN}
    )
    assert candidate_identity(**values) != candidate_identity(
        **{**values, "local_category_path": "writing/documentation"}
    )


def test_quarantine_never_writes_intended_install_root(
    tmp_path: Path,
    prepared_skill: Path,
) -> None:
    install_root = tmp_path / "formal-skills"
    repository = CandidateRepository(tmp_path / "state")

    manifest = _quarantine(repository, prepared_skill, install_root)

    assert repository.payload_path(manifest).is_dir()
    assert repository.payload_path(manifest).is_relative_to(repository.quarantine_root)
    assert not install_root.exists()
    assert repository.load_state(manifest.candidate_id).status is CandidateStatus.QUARANTINED
    assert repository.manifest_digest(manifest.candidate_id)


def test_quarantine_is_idempotent_only_for_unchanged_payload(
    tmp_path: Path,
    prepared_skill: Path,
) -> None:
    repository = CandidateRepository(tmp_path / "state")
    install_root = tmp_path / "formal-skills"
    manifest = _quarantine(repository, prepared_skill, install_root)

    repeated = _quarantine(repository, prepared_skill, install_root)

    assert repeated == manifest
    (repository.payload_path(manifest) / "changed.txt").write_text(
        "tampered", encoding="utf-8"
    )
    with pytest.raises(CandidateIntegrityError, match="payload digest"):
        _quarantine(repository, prepared_skill, install_root)


def test_state_machine_rejects_install_without_governance_pass(
    tmp_path: Path,
    prepared_skill: Path,
) -> None:
    repository = CandidateRepository(tmp_path / "state")
    manifest = _quarantine(repository, prepared_skill, tmp_path / "formal-skills")

    with pytest.raises(ValueError, match="invalid Candidate transition"):
        repository.transition(
            manifest.candidate_id,
            expected={CandidateStatus.QUARANTINED},
            next_status=CandidateStatus.INSTALLED,
        )


def test_state_transition_uses_compare_before_write(
    tmp_path: Path,
    prepared_skill: Path,
) -> None:
    repository = CandidateRepository(tmp_path / "state")
    manifest = _quarantine(repository, prepared_skill, tmp_path / "formal-skills")
    repository.transition(
        manifest.candidate_id,
        expected={CandidateStatus.QUARANTINED},
        next_status=CandidateStatus.GOVERNANCE_PENDING,
    )

    with pytest.raises(ValueError, match="expected QUARANTINED"):
        repository.transition(
            manifest.candidate_id,
            expected={CandidateStatus.QUARANTINED},
            next_status=CandidateStatus.GOVERNANCE_PENDING,
        )
