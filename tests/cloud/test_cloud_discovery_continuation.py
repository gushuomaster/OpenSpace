from __future__ import annotations

import asyncio
import json

import pytest

from openspace.entrypoints.mcp import server
from openspace.runtime import ExecutionResult


class _Registry:
    def list_skills(self):
        return []


class _Runtime:
    def __init__(self, result: ExecutionResult | None = None):
        self.result = result

    def get_skill_registry(self):
        return _Registry()

    def get_skill_store(self):
        return None

    async def execute(self, _request):
        return self.result


def test_local_search_zero_hits_returns_continuation_without_cloud_call(
    monkeypatch: pytest.MonkeyPatch,
):
    async def get_runtime():
        return _Runtime()

    async def local_search(**_kwargs):
        return []

    monkeypatch.setattr(server, "_get_openspace", get_runtime)
    monkeypatch.setattr("openspace.cloud.search.hybrid_search_skills", local_search)
    monkeypatch.setattr(
        server,
        "_cloud_search_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cloud called")),
    )

    payload = json.loads(asyncio.run(server.search_skills("unmatched")))

    assert payload["count"] == 0
    assert payload["skill_resolution"]["milestone"] == "LOCAL_MISS_CONTINUATION_AVAILABLE"
    assert payload["skill_resolution"]["next_action"] == "cloud_skill_discovery"


def test_execute_task_does_not_infer_cloud_need_from_empty_skills_used(
    monkeypatch: pytest.MonkeyPatch,
):
    runtime = _Runtime(
        ExecutionResult(text="done with existing tools", status="completed", skills_used=())
    )

    async def get_runtime():
        return runtime

    monkeypatch.setattr(server, "_get_openspace", get_runtime)
    monkeypatch.setattr(
        server,
        "_cloud_search_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cloud called")),
    )

    payload = json.loads(
        asyncio.run(server.execute_task("do it", search_scope="local"))
    )

    assert payload["status"] == "completed"
    assert payload["response"] == "done with existing tools"
    assert payload["skills_used"] == []
    assert "skill_resolution" not in payload
    assert "cloud_skill_candidates" not in payload
