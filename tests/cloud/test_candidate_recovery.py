from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.inventory import digest_tree

from openspace.cloud.candidate_lifecycle import (
    CandidateRepository,
    CandidateStatus,
    formal_candidate_path,
)
from openspace.cloud.candidate_governance import verify_confirmed_candidate
from openspace.cloud.candidate_visibility import CandidateVisibilityDecision, CandidateVisibilityPolicy
from openspace.cloud.local_mapping import CloudSkillBinding
from test_candidate_install import InstallerFixture


PINNED_PYTHON = Path(
    r"D:\project\OpenSpace-e2e-functional-closure\artifacts\recovery-subprocess\venv\Scripts\python.exe"
)


def test_kill_after_formal_placement_leaves_installing_state(tmp_path: Path):
    child_code = r'''
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "tests" / "cloud"))
from test_candidate_install import InstallerFixture
from openspace.cloud.candidate_install import install_candidate

root = Path(sys.argv[1])
fixture = InstallerFixture(root)

def kill_after_placement(_path):
    os._exit(91)

asyncio.run(install_candidate(
    fixture.manifest.candidate_id,
    fixture.pass_payload,
    repository=fixture.repository,
    registry=fixture.registry,
    skill_store=fixture.skill_store,
    mapping_store=fixture.mapping_store,
    after_formal_placement=kill_after_placement,
))
'''
    completed = subprocess.run(
        [str(PINNED_PYTHON), "-c", child_code, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )

    repository = CandidateRepository(tmp_path / "state" / "candidates")
    candidate_ids = repository.candidate_ids()
    assert completed.returncode == 91, completed.stderr
    assert len(candidate_ids) == 2
    candidate_id = next(
        item
        for item in candidate_ids
        if repository.load_manifest(item).cloud_skill_id == "cloud-1"
    )
    manifest = repository.load_manifest(candidate_id)
    assert formal_candidate_path(manifest).is_dir()
    assert repository.load_state(candidate_id).status is CandidateStatus.INSTALLING


@pytest.fixture
def installing_fixture(tmp_path: Path):
    fixture = InstallerFixture(tmp_path)
    governance = verify_confirmed_candidate(fixture.payload_path, fixture.pass_payload)
    assert governance.install_authorized
    fixture.repository.bind_governance(fixture.manifest.candidate_id, governance)
    fixture.repository.transition(
        fixture.manifest.candidate_id,
        expected={CandidateStatus.GOVERNANCE_PASSED},
        next_status=CandidateStatus.INSTALLING,
        receipt_digest=governance.receipt_digest,
    )
    fixture.final_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture.payload_path, fixture.final_path)
    try:
        yield fixture
    finally:
        fixture.close()


def _recover(fixture: InstallerFixture):
    from openspace.cloud.candidate_recovery import reconcile_installing_candidates

    results = asyncio.run(
        reconcile_installing_candidates(
            repository=fixture.repository,
            registry=fixture.registry,
            skill_store=fixture.skill_store,
            mapping_store=fixture.mapping_store,
        )
    )
    assert len(results) == 1
    return results[0]


def test_matching_installing_candidate_becomes_visible(installing_fixture):
    fixture = installing_fixture
    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALLED
    assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALLED
    assert fixture.registry.get_skill(fixture.skill_id).path.parent == fixture.final_path
    assert fixture.skill_store.load_record(fixture.skill_id) is not None
    assert fixture.mapping_store.get_binding_by_local(fixture.skill_id).cloud_skill_id == "cloud-1"
    assert CandidateVisibilityPolicy(fixture.repository).inspect(fixture.final_path).allowed


def test_missing_formal_path_cleans_owned_metadata_and_fails(installing_fixture):
    fixture = installing_fixture
    meta = fixture.registry.register_skill_dir(fixture.final_path)
    asyncio.run(fixture.skill_store.sync_from_registry([meta]))
    fixture.mapping_store.upsert_binding(
        CloudSkillBinding(fixture.skill_id, "cloud-1", str(fixture.final_path))
    )
    fixture.mapping_store.upsert_skill_local_classification(
        local_skill_id=fixture.skill_id,
        category="workflow",
        local_category_path="technology/computing",
        updated_at="2026-10-08T00:00:00Z",
    )
    shutil.rmtree(fixture.final_path)

    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALL_FAILED
    assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALL_FAILED
    assert fixture.registry.get_skill(fixture.skill_id) is None
    assert fixture.skill_store.load_record(fixture.skill_id) is None
    assert fixture.mapping_store.get_binding_by_local(fixture.skill_id) is None
    assert fixture.mapping_store.get_skill_local_classification(fixture.skill_id) is None


def test_missing_formal_path_cleans_only_owned_install_temporary(
    installing_fixture,
):
    fixture = installing_fixture
    shutil.rmtree(fixture.final_path)
    owned_temporary = fixture.final_path.with_name(
        f".{fixture.final_path.name}.installing-"
        f"{fixture.manifest.candidate_id}-{'a' * 32}"
    )
    other_candidate_temporary = fixture.final_path.with_name(
        f".{fixture.final_path.name}.installing-"
        f"candidate_{'9' * 64}-{'b' * 32}"
    )
    shutil.copytree(fixture.payload_path, owned_temporary)
    other_candidate_temporary.mkdir()
    (other_candidate_temporary / "SKILL.md").write_text(
        "unrelated asset\n", encoding="utf-8"
    )

    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALL_FAILED
    assert result.error_code == "FORMAL_PATH_MISSING"
    assert not owned_temporary.exists()
    assert other_candidate_temporary.is_dir()


def test_payload_tamper_fails_closed_without_deleting_formal_bytes(installing_fixture):
    fixture = installing_fixture
    (fixture.payload_path / "tampered.txt").write_text("tampered", encoding="utf-8")
    original_digest = digest_tree(fixture.final_path)

    result = _recover(fixture)

    assert result.status is CandidateStatus.INTEGRITY_MISMATCH
    assert digest_tree(fixture.final_path) == original_digest
    assert fixture.registry.get_skill(fixture.skill_id) is None
    assert not CandidateVisibilityPolicy(fixture.repository).inspect(fixture.final_path).allowed


def test_foreign_formal_path_owner_is_preserved(installing_fixture):
    fixture = installing_fixture
    (fixture.final_path / ".skill_id").write_text("foreign__imp_12345678\n", encoding="utf-8")
    foreign_digest = digest_tree(fixture.final_path)

    result = _recover(fixture)

    assert result.status is CandidateStatus.INTEGRITY_MISMATCH
    assert digest_tree(fixture.final_path) == foreign_digest
    assert fixture.registry.get_skill(fixture.skill_id) is None


def test_another_local_skill_occupying_formal_path_is_preserved(installing_fixture):
    fixture = installing_fixture
    sidecar = fixture.final_path / ".skill_id"
    sidecar.write_text("foreign__imp_12345678\n", encoding="utf-8")
    foreign = fixture.registry.register_skill_dir(fixture.final_path)
    assert foreign.skill_id == "foreign__imp_12345678"
    sidecar.write_text(fixture.skill_id + "\n", encoding="utf-8")

    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALL_FAILED
    assert fixture.registry.get_skill(foreign.skill_id) is foreign
    assert fixture.final_path.is_dir()
    assert fixture.registry.get_skill(fixture.skill_id) is None


@pytest.mark.parametrize(
    "corruption",
    ["manifest", "binding", "receipt", "installed_bytes"],
)
def test_corrupt_recovery_evidence_fails_closed(installing_fixture, corruption):
    fixture = installing_fixture
    candidate_id = fixture.manifest.candidate_id
    if corruption == "manifest":
        path = fixture.repository.manifest_path(candidate_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["local_content_hash"] = "sha256:" + "f" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    elif corruption == "binding":
        path = fixture.repository.governance_binding_path(candidate_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["candidate_digest"] = "f" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    elif corruption == "receipt":
        path = fixture.repository.state_path(candidate_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["receipt_digest"] = "f" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        (fixture.final_path / "tampered.txt").write_text("tampered", encoding="utf-8")
    original_digest = digest_tree(fixture.final_path)

    result = _recover(fixture)

    assert result.status is CandidateStatus.INTEGRITY_MISMATCH
    assert digest_tree(fixture.final_path) == original_digest
    assert fixture.registry.get_skill(fixture.skill_id) is None
    assert not CandidateVisibilityPolicy(fixture.repository).inspect(fixture.final_path).allowed


def test_corrupt_state_does_not_publish_candidate(installing_fixture):
    fixture = installing_fixture
    path = fixture.repository.state_path(fixture.manifest.candidate_id)
    path.write_text("{invalid", encoding="utf-8")

    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALL_FAILED
    assert path.read_text(encoding="utf-8") == "{invalid"
    assert fixture.registry.get_skill(fixture.skill_id) is None


def test_repeated_recovery_has_no_duplicate_visibility(installing_fixture):
    fixture = installing_fixture
    first = _recover(fixture)
    second = asyncio.run(
        __import__("openspace.cloud.candidate_recovery", fromlist=["reconcile_installing_candidates"])
        .reconcile_installing_candidates(
            repository=fixture.repository,
            registry=fixture.registry,
            skill_store=fixture.skill_store,
            mapping_store=fixture.mapping_store,
        )
    )

    assert first.status is CandidateStatus.INSTALLED
    assert second == ()
    assert [meta.skill_id for meta in fixture.registry.list_skills()].count(fixture.skill_id) == 1


@pytest.mark.parametrize("point", ["mapping", "classification", "registry", "terminal"])
def test_visibility_interruption_leaves_installing_then_reruns(installing_fixture, monkeypatch, point):
    fixture = installing_fixture
    if point == "mapping":
        owner, method = fixture.mapping_store, "upsert_binding"
    elif point == "classification":
        owner, method = fixture.mapping_store, "upsert_skill_local_classification"
    elif point == "registry":
        owner, method = fixture.registry, "register_skill_dir"
    else:
        owner, method = fixture.repository, "transition"
    original = getattr(owner, method)

    def interrupted(*args, **kwargs):
        if point != "terminal" or kwargs.get("next_status") is CandidateStatus.INSTALLED:
            if point != "terminal":
                original(*args, **kwargs)
            raise RuntimeError("injected interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, method, interrupted)
    first = _recover(fixture)
    assert first.status is CandidateStatus.INSTALLING
    assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALLING
    monkeypatch.setattr(owner, method, original)

    second = _recover(fixture)
    assert second.status is CandidateStatus.INSTALLED
    assert fixture.registry.get_skill(fixture.skill_id) is not None


def test_second_terminal_interruption_never_marks_installed(installing_fixture, monkeypatch):
    fixture = installing_fixture
    original = fixture.repository.transition

    def interrupted(candidate_id, **kwargs):
        if kwargs.get("next_status") is CandidateStatus.INSTALLED:
            raise RuntimeError("still interrupted")
        return original(candidate_id, **kwargs)

    monkeypatch.setattr(fixture.repository, "transition", interrupted)

    for _ in range(2):
        result = _recover(fixture)
        assert result.status is CandidateStatus.INSTALLING
        assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALLING
        assert not CandidateVisibilityPolicy(fixture.repository).inspect(fixture.final_path).allowed


def test_terminal_write_then_exception_preserves_completed_visibility(installing_fixture, monkeypatch):
    fixture = installing_fixture
    original = fixture.repository.transition

    def interrupted(candidate_id, **kwargs):
        state = original(candidate_id, **kwargs)
        if kwargs.get("next_status") is CandidateStatus.INSTALLED:
            raise RuntimeError("exception after atomic state write")
        return state

    monkeypatch.setattr(fixture.repository, "transition", interrupted)

    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALLED
    assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALLED
    assert CandidateVisibilityPolicy(fixture.repository).inspect(fixture.final_path).allowed
    assert fixture.registry.get_skill(fixture.skill_id) is not None


def test_post_write_visibility_denial_aborts_startup_without_cleanup(
    installing_fixture, monkeypatch
):
    fixture = installing_fixture
    original_inspect = CandidateVisibilityPolicy.inspect
    original_transition = fixture.repository.transition
    calls = 0

    def deny_after_terminal_write(policy, path):
        nonlocal calls
        calls += 1
        if calls >= 2:
            return CandidateVisibilityDecision(False, "INJECTED_ADMISSION_DENIAL")
        return original_inspect(policy, path)

    def interrupted_transition(candidate_id, **kwargs):
        state = original_transition(candidate_id, **kwargs)
        if kwargs.get("next_status") is CandidateStatus.INSTALLED:
            raise RuntimeError("exception after atomic state write")
        return state

    monkeypatch.setattr(CandidateVisibilityPolicy, "inspect", deny_after_terminal_write)
    monkeypatch.setattr(fixture.repository, "transition", interrupted_transition)

    with pytest.raises(RuntimeError, match="INJECTED_ADMISSION_DENIAL"):
        _recover(fixture)

    assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALLED
    assert fixture.registry.get_skill(fixture.skill_id) is not None
    assert fixture.skill_store.load_record(fixture.skill_id) is not None


def test_inactive_store_record_at_formal_path_is_preserved(installing_fixture):
    fixture = installing_fixture
    meta = fixture.registry.register_skill_dir(fixture.final_path)
    asyncio.run(fixture.skill_store.sync_from_registry([meta]))
    asyncio.run(fixture.skill_store.deactivate_record(fixture.skill_id))
    assert fixture.skill_store.load_record(fixture.skill_id).is_active is False

    result = _recover(fixture)

    assert result.status is CandidateStatus.INSTALL_FAILED
    assert result.error_code == "STORE_INACTIVE_CONFLICT"
    assert fixture.repository.load_state(fixture.manifest.candidate_id).status is CandidateStatus.INSTALL_FAILED
    assert fixture.skill_store.load_record(fixture.skill_id).is_active is False
    assert fixture.final_path.is_dir()
