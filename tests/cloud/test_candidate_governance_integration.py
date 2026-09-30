from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from engine.inventory import digest_tree
from engine.managed_completion import completion_receipt
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

from openspace.cloud.candidate_install import install_candidate
from openspace.cloud.candidate_lifecycle import CandidateRepository, CandidateStatus
from openspace.cloud.client import OpenSpaceClient
from openspace.cloud.config import CloudConfig
from openspace.cloud.local_mapping import CloudLocalMappingStore
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
class AuditProvider:
    descriptor: ProviderDescriptor = ProviderDescriptor(
        "test.candidate-integration",
        "test://candidate-integration",
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
        "behavioral.candidate-integration",
        "test.runner",
        path.name,
        True,
        CheckStatus.PASS,
        True,
        True,
        1.0,
        ("candidate integration behavior executed",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        str(path),
    )


class RealLifecycle:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.install_root = tmp_path / "formal-skills"
        self.db_path = tmp_path / "state" / "openspace.db"
        self.skill_store = SkillStore(self.db_path)
        self.mapping_store = CloudLocalMappingStore(self.db_path)
        self.repository = CandidateRepository(self.db_path.parent / "candidates")
        self.registry = SkillRegistry([])
        self.registry.discover()
        self.client = OpenSpaceClient(
            CloudConfig(
                mode="live",
                base_url="https://open-space.cloud",
                api_key="test-key",
                telemetry_mode="off",
            ),
            mapping_store=self.mapping_store,
        )
        self.orchestrator = PipelineOrchestrator(
            provider_gateway=ProviderGateway((AuditProvider(),))
        )
        self.acquired: dict[str, object] | None = None

    def acquire(
        self,
        *,
        cloud_skill_id: str = "cloud-integration",
        skill_name: str = "demo",
        skill_text: str | None = None,
    ) -> dict[str, object]:
        if skill_text is None:
            skill_text = (
                "---\nname: demo\ndescription: Governed integration Skill.\n"
                "---\n\n# Demo\n\nUse the governed workflow.\n"
            )
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                f"{skill_name}/SKILL.md",
                skill_text,
            )
        bundle_bytes = bundle.getvalue()
        self.client.fetch_cloud_skill = lambda _requested_cloud_skill_id: {
            "cloud_skill_id": cloud_skill_id,
            "title": skill_name,
            "summary": "Governed integration Skill.",
            "authored_metadata": {
                "name": skill_name,
                "description": "Governed integration Skill.",
            },
            "package_id": "package-integration",
            "package_path": "technology/computing",
            "snapshot_version": "snapshot-integration",
            "manifest_hash": "sha256:" + hashlib.sha256(bundle_bytes).hexdigest(),
        }
        self.client.download_skill_bundle = lambda *_args, **_kwargs: bundle_bytes
        self.acquired = self.client.import_skill(
            cloud_skill_id,
            self.install_root,
            local_category="workflow",
            local_category_path="technology/computing",
        )
        return self.acquired

    @property
    def candidate_path(self) -> Path:
        assert self.acquired is not None
        return Path(str(self.acquired["candidate_path"]))

    @property
    def candidate_id(self) -> str:
        assert self.acquired is not None
        return str(self.acquired["candidate_id"])

    @property
    def formal_path(self) -> Path:
        manifest = self.repository.load_manifest(self.candidate_id)
        return (
            self.install_root
            / "technology"
            / "computing"
            / manifest.final_directory_name
        )

    def inspect_audit(self):
        return self.orchestrator.inspect(
            Intent.AUDIT,
            self.candidate_path,
            deliverable_contract_applicability=(
                DeliverableContractApplicability.NOT_REQUIRED
            ),
        )

    def validate_audit(self, inspection):
        return self.orchestrator.validate(
            inspection,
            _decision(),
            (),
            candidate=None,
            target_parent=self.candidate_path.parent,
            authorized_to_modify=False,
            behavioral_runner=_behavior,
        )

    def confirm_as_codex(self, validation):
        return self.orchestrator.confirm(
            validation,
            SemanticConfirmation(
                digest_tree(self.candidate_path),
                "Codex confirmed the exact quarantined Candidate.",
                "CODEX",
            ),
        )

    async def install(self, serialized_outcome):
        return await install_candidate(
            self.candidate_id,
            serialized_outcome,
            repository=self.repository,
            registry=self.registry,
            skill_store=self.skill_store,
            mapping_store=self.mapping_store,
        )

    def close(self) -> None:
        self.mapping_store.close()
        self.skill_store.close()


@pytest.fixture
def real_lifecycle(tmp_path: Path):
    lifecycle = RealLifecycle(tmp_path)
    try:
        yield lifecycle
    finally:
        lifecycle.close()


def test_remote_candidate_requires_real_governance_before_install(
    real_lifecycle: RealLifecycle,
) -> None:
    acquired = real_lifecycle.acquire()
    assert acquired["status"] == "governance_required"
    assert not real_lifecycle.formal_path.exists()

    inspection = real_lifecycle.inspect_audit()
    validation = real_lifecycle.validate_audit(inspection)
    outcome = real_lifecycle.confirm_as_codex(validation)
    installed = asyncio.run(real_lifecycle.install(outcome_to_data(outcome)))

    assert installed.status is CandidateStatus.INSTALLED
    assert (
        digest_tree(real_lifecycle.formal_path)
        == completion_receipt(outcome).candidate_digest
    )
    assert real_lifecycle.registry.get_skill(installed.skill_id) is not None
    assert real_lifecycle.skill_store.load_record(installed.skill_id) is not None


@pytest.mark.parametrize(
    ("failure_case", "expected_status"),
    [
        ("gate_fail", CandidateStatus.GOVERNANCE_BLOCKED),
        ("missing_receipt", CandidateStatus.GOVERNANCE_INCOMPLETE),
        ("non_codex_confirmation", CandidateStatus.GOVERNANCE_INCOMPLETE),
        ("malformed_outcome", CandidateStatus.GOVERNANCE_ERROR),
        ("payload_mutation", CandidateStatus.INTEGRITY_MISMATCH),
        ("install_failure", CandidateStatus.INSTALL_FAILED),
    ],
)
def test_governance_and_install_failures_retain_only_quarantine(
    failure_case: str,
    expected_status: CandidateStatus,
    real_lifecycle: RealLifecycle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if failure_case == "gate_fail":
        real_lifecycle.acquire(
            cloud_skill_id="cloud-blocked",
            skill_name="blocked-demo",
            skill_text=(
                "---\nname: Bad Name\ndescription: Structurally blocked Candidate.\n"
                "---\n\nTODO\n"
            ),
        )
    else:
        real_lifecycle.acquire()

    inspection = real_lifecycle.inspect_audit()
    validation = real_lifecycle.validate_audit(inspection)
    outcome = real_lifecycle.confirm_as_codex(validation)
    serialized = outcome_to_data(outcome)

    if failure_case == "missing_receipt":
        serialized.pop("completion_receipt", None)
    elif failure_case == "non_codex_confirmation":
        serialized["semantic_confirmation"]["confirmed_by"] = "PROVIDER"
    elif failure_case == "malformed_outcome":
        serialized["validation"] = "malformed"
    elif failure_case == "payload_mutation":
        (real_lifecycle.candidate_path / "tampered.txt").write_text(
            "changed after confirmation\n",
            encoding="utf-8",
        )
    elif failure_case == "install_failure":
        async def fail_sync(_skills):
            raise RuntimeError("injected integration SkillStore failure")

        monkeypatch.setattr(
            real_lifecycle.skill_store,
            "sync_from_registry",
            fail_sync,
        )

    result = asyncio.run(real_lifecycle.install(serialized))
    manifest = real_lifecycle.repository.load_manifest(real_lifecycle.candidate_id)

    assert result.status is expected_status
    assert result.installed is False
    assert not real_lifecycle.formal_path.exists()
    assert real_lifecycle.registry.get_skill(manifest.final_skill_id) is None
    assert real_lifecycle.skill_store.load_record(manifest.final_skill_id) is None
    assert real_lifecycle.candidate_path.is_dir()
    assert real_lifecycle.repository.manifest_path(
        real_lifecycle.candidate_id
    ).is_file()
    assert real_lifecycle.repository.state_path(
        real_lifecycle.candidate_id
    ).is_file()
    if failure_case == "install_failure":
        assert real_lifecycle.repository.governance_binding_path(
            real_lifecycle.candidate_id
        ).is_file()
