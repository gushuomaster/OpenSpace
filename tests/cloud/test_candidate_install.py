from __future__ import annotations

import asyncio
import json
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
from engine.serialization import completion_receipt_from_data, outcome_to_data

from openspace.cloud.candidate_install import install_candidate
from openspace.cloud.candidate_lifecycle import (
    CandidateRepository,
    CandidateStatus,
    SourceIntegrityStatus,
)
from openspace.cloud.local_mapping import CloudLocalMappingStore
from openspace.cloud.local_mapping import CloudSkillBinding, utc_now_iso
from openspace.skill_engine.registry import SkillRegistry
from openspace.skill_engine.store import SkillStore


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
        "behavioral.candidate-install",
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


def _audit(candidate_path: Path):
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway((CapabilityProvider(),))
    )
    inspection = orchestrator.inspect(
        Intent.AUDIT,
        candidate_path,
        deliverable_contract_applicability=DeliverableContractApplicability.NOT_REQUIRED,
    )
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


class InstallerFixture:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.install_root = tmp_path / "formal-skills"
        self.repository = CandidateRepository(tmp_path / "state" / "candidates")
        self.mapping_store = CloudLocalMappingStore(tmp_path / "state" / "mapping.db")
        self.skill_store = SkillStore(tmp_path / "state" / "skills.db")
        self.registry = SkillRegistry([])
        self.registry.discover()

        self.manifest = self._candidate(
            directory_name="demo",
            cloud_skill_id="cloud-1",
            local_skill_id="demo__imp_12345678",
            skill_text=(
                "---\nname: demo\ndescription: Install the governed Candidate.\n---\n\n"
                "# Demo\n\nUse the installed workflow.\n"
            ),
        )
        self.payload_path = self.repository.payload_path(self.manifest)
        self.skill_id = self.manifest.final_skill_id
        self.final_path = (
            self.install_root
            / "technology"
            / "computing"
            / self.manifest.final_directory_name
        )
        self.pass_payload = outcome_to_data(_audit(self.payload_path))
        self.receipt = completion_receipt_from_data(
            self.pass_payload["completion_receipt"]
        )

        self.blocked_manifest = self._candidate(
            directory_name="blocked-demo",
            cloud_skill_id="cloud-blocked",
            local_skill_id="blocked-demo__imp_12345678",
            skill_text=(
                "---\nname: Bad Name\ndescription: Structurally blocked Candidate.\n"
                "---\n\nTODO\n"
            ),
        )
        blocked_path = self.repository.payload_path(self.blocked_manifest)
        blocked_outcome = _audit(blocked_path)
        assert blocked_outcome.gate_result.verdict is GateVerdict.FAIL
        self.blocked_payload = outcome_to_data(blocked_outcome)
        self.unrelated_dir: Path | None = None
        self.unrelated_skill_id = "unrelated__existing"

    def _candidate(
        self,
        *,
        directory_name: str,
        cloud_skill_id: str,
        local_skill_id: str,
        skill_text: str,
    ):
        prepared = self.tmp_path / "prepared" / directory_name
        prepared.mkdir(parents=True)
        (prepared / "SKILL.md").write_text(skill_text, encoding="utf-8")
        (prepared / ".skill_id").write_text(local_skill_id + "\n", encoding="utf-8")
        (prepared / ".cloud_skill.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "api_version": "v2",
                    "local_skill_id": local_skill_id,
                    "cloud_skill_id": cloud_skill_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return self.repository.quarantine(
            prepared,
            cloud_skill_id=cloud_skill_id,
            source_bundle_sha256="1" * 64,
            source_manifest_hash="sha256:" + "1" * 64,
            source_integrity_status=SourceIntegrityStatus.PROVEN,
            local_content_hash="sha256:" + "2" * 64,
            final_skill_id=local_skill_id,
            intended_install_parent=self.install_root,
            local_category="workflow",
            local_category_path="technology/computing",
            package_id="package-1",
            package_path="technology/computing",
            package_snapshot_version="snapshot-1",
            acquired_at="2026-09-30T00:00:00Z",
        )

    async def install_passed(self):
        return await install_candidate(
            self.manifest.candidate_id,
            self.pass_payload,
            repository=self.repository,
            registry=self.registry,
            skill_store=self.skill_store,
            mapping_store=self.mapping_store,
        )

    async def install(self, outcome_name: str):
        manifest = self.manifest
        payload = json.loads(json.dumps(self.pass_payload))
        if outcome_name == "blocked":
            manifest = self.blocked_manifest
            payload = self.blocked_payload
        elif outcome_name == "incomplete":
            payload["semantic_confirmation"]["confirmed_by"] = "PROVIDER"
        elif outcome_name == "error":
            payload["validation"] = "malformed"
        elif outcome_name == "integrity_mismatch":
            (self.payload_path / "tampered.txt").write_text(
                "changed after confirmation\n",
                encoding="utf-8",
            )
        else:
            raise AssertionError(f"unknown outcome: {outcome_name}")
        return await install_candidate(
            manifest.candidate_id,
            payload,
            repository=self.repository,
            registry=self.registry,
            skill_store=self.skill_store,
            mapping_store=self.mapping_store,
        )

    def formal_snapshot(self) -> dict[str, object]:
        files = ()
        if self.install_root.exists():
            files = tuple(
                sorted(
                    path.relative_to(self.install_root).as_posix()
                    for path in self.install_root.rglob("*")
                )
            )
        return {
            "files": files,
            "registry": tuple(sorted(item.skill_id for item in self.registry.list_skills())),
            "skill_store": tuple(sorted(self.skill_store.load_all())),
            "bindings": tuple(
                binding.local_skill_id
                for cloud_id in ("cloud-1", "cloud-blocked")
                if (binding := self.mapping_store.get_binding_by_cloud(cloud_id))
                is not None
            ),
        }

    def fail_at(self, failure_point: str) -> None:
        self._create_unrelated_skill()
        if failure_point == "skill_store":
            async def fail_sync(_skills):
                raise RuntimeError("injected SkillStore failure")

            self.skill_store.sync_from_registry = fail_sync
            return
        if failure_point == "mapping":
            original = self.mapping_store.upsert_binding

            def fail_mapping(binding):
                original(binding)
                raise RuntimeError("injected mapping failure after write")

            self.mapping_store.upsert_binding = fail_mapping
            return
        if failure_point == "registry":
            original = self.registry.register_skill_dir

            def fail_registry(skill_dir):
                registered = original(skill_dir)
                assert registered is not None
                raise RuntimeError("injected Registry failure after visibility")

            self.registry.register_skill_dir = fail_registry
            return
        if failure_point == "state_write":
            original = self.repository.transition

            def fail_state(candidate_id, **kwargs):
                if kwargs.get("next_status") is CandidateStatus.INSTALLED:
                    raise RuntimeError("injected final Candidate state failure")
                return original(candidate_id, **kwargs)

            self.repository.transition = fail_state
            return
        raise AssertionError(f"unknown failure point: {failure_point}")

    def _create_unrelated_skill(self) -> None:
        unrelated = self.tmp_path / "unrelated-skills" / "unrelated"
        unrelated.mkdir(parents=True)
        (unrelated / "SKILL.md").write_text(
            "---\nname: unrelated\ndescription: Existing unrelated Skill.\n---\n",
            encoding="utf-8",
        )
        (unrelated / ".skill_id").write_text(
            self.unrelated_skill_id + "\n",
            encoding="utf-8",
        )
        meta = self.registry.register_skill_dir(unrelated)
        assert meta is not None
        asyncio.run(self.skill_store.sync_from_registry([meta]))
        self.mapping_store.upsert_skill_local_classification(
            local_skill_id=self.unrelated_skill_id,
            category="workflow",
            local_category_path="existing/unrelated",
            updated_at=utc_now_iso(),
        )
        self.mapping_store.upsert_binding(
            CloudSkillBinding(
                local_skill_id=self.unrelated_skill_id,
                cloud_skill_id="cloud-unrelated",
                local_path=str(unrelated),
            )
        )
        self.unrelated_dir = unrelated

    def unrelated_skill_still_exists(self) -> bool:
        return bool(
            self.unrelated_dir is not None
            and self.unrelated_dir.exists()
            and self.registry.get_skill(self.unrelated_skill_id) is not None
            and self.skill_store.load_record(self.unrelated_skill_id) is not None
            and self.mapping_store.get_binding_by_local(self.unrelated_skill_id)
            is not None
        )

    def close(self) -> None:
        self.skill_store.close()
        self.mapping_store.close()


@pytest.fixture
def installer_fixture(tmp_path: Path):
    fixture = InstallerFixture(tmp_path)
    try:
        yield fixture
    finally:
        fixture.close()


def test_pass_candidate_installs_then_becomes_registry_visible(
    installer_fixture: InstallerFixture,
) -> None:
    result = asyncio.run(installer_fixture.install_passed())

    assert result.status is CandidateStatus.INSTALLED
    assert result.installed_digest == installer_fixture.receipt.candidate_digest
    assert installer_fixture.registry.get_skill(result.skill_id) is not None
    assert installer_fixture.skill_store.load_record(result.skill_id) is not None


@pytest.mark.parametrize(
    "outcome_name",
    ["blocked", "incomplete", "error", "integrity_mismatch"],
)
def test_non_pass_candidate_never_touches_formal_state(
    outcome_name: str,
    installer_fixture: InstallerFixture,
) -> None:
    before = installer_fixture.formal_snapshot()

    result = asyncio.run(installer_fixture.install(outcome_name))

    assert result.installed is False
    assert installer_fixture.formal_snapshot() == before


@pytest.mark.parametrize(
    "failure_point",
    ["skill_store", "mapping", "registry", "state_write"],
)
def test_install_failure_compensates_only_current_candidate(
    failure_point: str,
    installer_fixture: InstallerFixture,
) -> None:
    installer_fixture.fail_at(failure_point)

    result = asyncio.run(installer_fixture.install_passed())

    assert result.status is CandidateStatus.INSTALL_FAILED
    assert installer_fixture.registry.get_skill(installer_fixture.skill_id) is None
    assert installer_fixture.skill_store.load_record(installer_fixture.skill_id) is None
    assert (
        installer_fixture.mapping_store.get_binding_by_local(
            installer_fixture.skill_id
        )
        is None
    )
    assert (
        installer_fixture.mapping_store.get_skill_local_classification(
            installer_fixture.skill_id
        )
        is None
    )
    assert not installer_fixture.final_path.exists()
    assert installer_fixture.unrelated_skill_still_exists()
    assert installer_fixture.repository.governance_binding_path(
        installer_fixture.manifest.candidate_id
    ).is_file()
    assert installer_fixture.payload_path.is_dir()


def test_mapping_compensation_refuses_mismatched_owner(
    installer_fixture: InstallerFixture,
) -> None:
    installer_fixture._create_unrelated_skill()

    deleted = installer_fixture.mapping_store.delete_import_state(
        installer_fixture.unrelated_skill_id,
        expected_cloud_skill_id="wrong-cloud-id",
        expected_local_path=installer_fixture.tmp_path / "wrong-path",
    )

    assert deleted is False
    assert installer_fixture.mapping_store.get_binding_by_local(
        installer_fixture.unrelated_skill_id
    ) is not None
    assert installer_fixture.mapping_store.get_skill_local_classification(
        installer_fixture.unrelated_skill_id
    ) is not None


def test_registry_compensation_refuses_mismatched_path(
    installer_fixture: InstallerFixture,
) -> None:
    installer_fixture._create_unrelated_skill()

    deleted = installer_fixture.registry.unregister_skill(
        installer_fixture.unrelated_skill_id,
        expected_path=installer_fixture.tmp_path / "wrong-path",
    )

    assert deleted is False
    assert installer_fixture.registry.get_skill(
        installer_fixture.unrelated_skill_id
    ) is not None
