from __future__ import annotations

import asyncio

from openspace.skill_engine.protocol import DiscoverSkillsTool, SkillDiscoveryService
from openspace.skill_engine.registry import SkillRegistry


def test_empty_local_discovery_exposes_explicit_cloud_continuation():
    tool = DiscoverSkillsTool(SkillDiscoveryService(SkillRegistry([])))

    result = asyncio.run(tool._arun("unmatched workflow"))

    resolution = result.metadata["skill_resolution"]
    assert resolution == {
        "status": "local_miss",
        "milestone": "LOCAL_MISS_CONTINUATION_AVAILABLE",
        "next_action": "cloud_skill_discovery",
        "query": "unmatched workflow",
    }
    attachment = result.additional_messages[0]["_meta"]["attachment"]
    assert attachment["type"] == "skill_discovery"
    assert attachment["signal"]["status"] == "local_miss"
    assert attachment["signal"]["query"] == "unmatched workflow"


def test_local_hit_does_not_claim_local_miss(tmp_path):
    skill = tmp_path / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo workflow helper\n---\nbody\n",
        encoding="utf-8",
    )
    registry = SkillRegistry([tmp_path])
    registry.discover()
    tool = DiscoverSkillsTool(SkillDiscoveryService(registry))

    result = asyncio.run(tool._arun("select:demo"))

    assert "skill_resolution" not in result.metadata
    assert result.additional_messages[0]["_meta"]["attachment"]["signal"] == {
        "query": "select:demo"
    }
