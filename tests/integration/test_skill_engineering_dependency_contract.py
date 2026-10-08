from __future__ import annotations

import importlib.metadata
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_REVISION = "0c83c8e87356191a0ef36c5c0f5a3f262eebbe3c"


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
    from engine.managed_completion import validate_completion_receipt
    from engine.models import ArtifactRole, ManagedCompletionReceipt
    from engine.serialization import validation_from_data

    assert ManagedCompletionReceipt is not None
    assert ArtifactRole is not None
    assert callable(validate_completion_receipt)
    assert callable(validation_from_data)


def test_installed_distribution_matches_declared_revision_when_direct_url():
    distribution = importlib.metadata.distribution("skill-engineering")
    direct_url = distribution.read_text("direct_url.json")
    assert direct_url, "skill-engineering must retain PEP 610 direct URL metadata"
    payload = json.loads(direct_url)
    vcs = payload.get("vcs_info") or {}
    assert vcs.get("commit_id") == EXPECTED_REVISION
