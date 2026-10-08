from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from engine.serialization import outcome_to_data

from openspace.cloud.candidate_lifecycle import CandidateStatus
from openspace.cloud.candidate_visibility import CandidateVisibilityPolicy
from openspace.entrypoints.mcp import server
from openspace.skill_engine.protocol import (
    DiscoverSkillsTool,
    SkillDiscoveryService,
    SkillTool,
)
from openspace.skill_engine.registry import SkillRegistry
from openspace.skill_engine.store import SkillStore

from tests.cloud.test_candidate_governance_integration import RealLifecycle


def _attachment_content(result) -> str:
    attachment = result.additional_messages[0]["_meta"]["attachment"]
    return str(attachment["content"])


def test_candidate_install_is_reused_by_fresh_runtime_and_skill_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle = RealLifecycle(tmp_path)
    marker = "CANDIDATE_RUNTIME_REUSE_MARKER"
    skill_text = (
        "---\nname: demo\ndescription: Governed integration Skill.\n"
        "---\n\n# Demo\n\n"
        f"{marker}\n"
    )
    try:
        # Turn 0: an empty local registry exposes a continuation only.
        local_miss = asyncio.run(
            DiscoverSkillsTool(
                SkillDiscoveryService(SkillRegistry([]))
            )._arun("governed cloud workflow")
        )
        resolution = local_miss.metadata["skill_resolution"]
        milestones = {
            "LOCAL_MISS_CONTINUATION_AVAILABLE": resolution["milestone"]
            == "LOCAL_MISS_CONTINUATION_AVAILABLE",
            "CLOUD_DISCOVERY_EXECUTED": False,
            "CODEX_SELECTION_COMPLETED": False,
            "CANDIDATE_INSTALLED": False,
            "TASK_RESUMED_WITH_SKILL": False,
        }

        # The MCP Cloud search and client search method run; only HTTP is
        # substituted with a deterministic response.
        def cloud_transport(path: str, payload: dict, *, timeout: int) -> dict:
            assert path == "/skills/search"
            assert payload["query"] == "governed cloud workflow"
            assert timeout == 30
            return {
                "results": [
                    {
                        "cloud_skill_id": "cloud-integration",
                        "title": "demo",
                        "summary": "Governed integration Skill.",
                        "package_id": "package-integration",
                        "package_path": "technology/computing",
                    }
                ]
            }

        monkeypatch.setattr(lifecycle.client, "_post_v2_json", cloud_transport)
        monkeypatch.setattr(server, "_get_cloud_client", lambda: lifecycle.client)
        cloud_result = json.loads(
            asyncio.run(server.cloud_search_skills("governed cloud workflow"))
        )
        assert cloud_result["status"] == "success"
        assert cloud_result["count"] == 1
        milestones["CLOUD_DISCOVERY_EXECUTED"] = (
            cloud_result["skill_resolution"]["milestone"]
            == "CLOUD_DISCOVERY_EXECUTED"
        )
        selected_cloud_skill_id = str(cloud_result["results"][0]["cloud_skill_id"])
        milestones["CODEX_SELECTION_COMPLETED"] = (
            selected_cloud_skill_id == "cloud-integration"
        )

        acquired = lifecycle.acquire(
            cloud_skill_id=selected_cloud_skill_id,
            skill_name="demo",
            skill_text=skill_text,
        )
        assert acquired["status"] == "governance_required"
        before_install = SkillRegistry([lifecycle.install_root])
        assert before_install.discover(
            admission_callback=CandidateVisibilityPolicy(lifecycle.repository).inspect
        ) == []

        inspection = lifecycle.inspect_audit()
        validation = lifecycle.validate_audit(inspection)
        outcome = lifecycle.confirm_as_codex(validation)
        installed = asyncio.run(lifecycle.install(outcome_to_data(outcome)))
        assert installed.status is CandidateStatus.INSTALLED
        assert (
            lifecycle.repository.load_state(lifecycle.candidate_id).status
            is CandidateStatus.INSTALLED
        )
        milestones["CANDIDATE_INSTALLED"] = installed.installed

        # Restart the runtime primitives from persisted formal state.
        lifecycle.close()
        repository = lifecycle.repository
        fresh_registry = SkillRegistry([lifecycle.install_root])
        fresh_registry.discover(
            admission_callback=CandidateVisibilityPolicy(repository).inspect
        )
        fresh_store = SkillStore(lifecycle.db_path)
        try:
            asyncio.run(fresh_store.sync_from_registry(fresh_registry.list_skills()))
            discovery = SkillDiscoveryService(fresh_registry, store=fresh_store)
            hits = discovery.search("select:demo")
            assert len(hits) == 1
            assert hits[0].skill_id == installed.skill_id

            skill_tool = SkillTool(fresh_registry, skill_store=fresh_store)
            skill_result = asyncio.run(skill_tool._arun("demo"))
            assert (
                lifecycle.formal_path.joinpath("SKILL.md").read_text(encoding="utf-8")
                == skill_text
            )
            assert marker in _attachment_content(skill_result)
            milestones["TASK_RESUMED_WITH_SKILL"] = skill_result.is_success
        finally:
            fresh_store.close()

        assert milestones == {
            "LOCAL_MISS_CONTINUATION_AVAILABLE": True,
            "CLOUD_DISCOVERY_EXECUTED": True,
            "CODEX_SELECTION_COMPLETED": True,
            "CANDIDATE_INSTALLED": True,
            "TASK_RESUMED_WITH_SKILL": True,
        }
    finally:
        if not getattr(lifecycle.skill_store, "_closed", True):
            lifecycle.close()


def test_local_miss_continuation_does_not_claim_task_level_automatic_closure() -> None:
    registry = SkillRegistry([])
    result = asyncio.run(
        DiscoverSkillsTool(SkillDiscoveryService(registry))._arun(
            "cloud-only workflow"
        )
    )

    resolution = result.metadata["skill_resolution"]
    assert resolution["milestone"] == "LOCAL_MISS_CONTINUATION_AVAILABLE"
    assert resolution["next_action"] == "cloud_skill_discovery"
    assert result.metadata.get("task_resumed_with_skill") is not True
    assert result.metadata.get("automatic_task_replay") is not True
    assert registry.list_skills() == []
    assert (
        result.additional_messages[0]["_meta"]["attachment"]["type"]
        == "skill_discovery"
    )
