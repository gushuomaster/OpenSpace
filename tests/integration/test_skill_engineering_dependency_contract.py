from __future__ import annotations

import ast
import importlib.metadata
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_REVISION = "c0d455054f8525d0a881d4e689e36ecfe287bde4"
EXPECTED_CANDIDATE_EXPORTS = (
    "digest_tree",
    "completion_receipt",
    "managed_status",
    "validate_completion_receipt",
    "CapabilityPreservationStatus",
    "CoverageStatus",
    "GateOutcome",
    "GateVerdict",
    "ManagedCompletionReceipt",
    "PipelineOrchestrator",
    "completion_receipt_from_data",
    "confirmation_from_data",
    "to_data",
    "validation_from_data",
)
CANDIDATE_MODULES = (
    "candidate_governance.py",
    "candidate_install.py",
    "candidate_lifecycle.py",
    "candidate_recovery.py",
    "candidate_visibility.py",
)


def _declared_revision(path: Path) -> str | None:
    match = re.search(
        r"skill-engineering(?:\s*@)?\s*git\+https://github\.com/gushuomaster/skill-engineering\.git@([0-9a-f]{40})",
        path.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def test_dependency_declarations_use_same_immutable_revision():
    assert _declared_revision(ROOT / "pyproject.toml") == EXPECTED_REVISION
    assert _declared_revision(ROOT / "requirements.txt") == EXPECTED_REVISION


def test_candidate_governance_import_contract_is_available():
    import engine.candidate_contract as candidate_contract
    from engine.inventory import digest_tree
    from engine.managed_completion import (
        completion_receipt,
        managed_status,
        validate_completion_receipt,
    )
    from engine.models import (
        CapabilityPreservationStatus,
        CoverageStatus,
        GateOutcome,
        GateVerdict,
        ManagedCompletionReceipt,
    )
    from engine.orchestrator import PipelineOrchestrator
    from engine.serialization import (
        completion_receipt_from_data,
        confirmation_from_data,
        to_data,
        validation_from_data,
    )

    expected = {
        "digest_tree": digest_tree,
        "completion_receipt": completion_receipt,
        "managed_status": managed_status,
        "validate_completion_receipt": validate_completion_receipt,
        "CapabilityPreservationStatus": CapabilityPreservationStatus,
        "CoverageStatus": CoverageStatus,
        "GateOutcome": GateOutcome,
        "GateVerdict": GateVerdict,
        "ManagedCompletionReceipt": ManagedCompletionReceipt,
        "PipelineOrchestrator": PipelineOrchestrator,
        "completion_receipt_from_data": completion_receipt_from_data,
        "confirmation_from_data": confirmation_from_data,
        "to_data": to_data,
        "validation_from_data": validation_from_data,
    }

    assert candidate_contract.__all__ == EXPECTED_CANDIDATE_EXPORTS
    assert {
        name: getattr(candidate_contract, name)
        for name in candidate_contract.__all__
    } == expected


def test_candidate_production_imports_only_the_stable_contract():
    imported_engine_modules: set[str] = set()
    for filename in CANDIDATE_MODULES:
        path = ROOT / "openspace" / "cloud" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_engine_modules.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("engine")
        )

    assert imported_engine_modules == {"engine.candidate_contract"}


def test_installed_distribution_loads_default_gate_policy():
    from engine.quality_gate import load_gate_policy

    policy = load_gate_policy()
    assert policy["policy_version"]


def test_installed_distribution_matches_declared_revision_when_direct_url():
    distribution = importlib.metadata.distribution("skill-engineering")
    direct_url = distribution.read_text("direct_url.json")
    assert direct_url, "skill-engineering must retain PEP 610 direct URL metadata"
    payload = json.loads(direct_url)
    vcs = payload.get("vcs_info") or {}
    assert vcs.get("commit_id") == EXPECTED_REVISION
