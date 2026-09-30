from __future__ import annotations

import asyncio
import hashlib
import importlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from openspace.cloud.client import OpenSpaceClient
from openspace.cloud.config import CloudConfig
from openspace.cloud.local_mapping import CloudLocalMappingStore


class _EntryPointRegistry:
    def __init__(self) -> None:
        self._skills: list[object] = []

    def register_skill_dir(self, skill_dir: Path):
        meta = SimpleNamespace(skill_id="registered-bypass", path=skill_dir / "SKILL.md")
        self._skills.append(meta)
        return meta

    def list_skills(self) -> list[object]:
        return list(self._skills)


class _EntryPointStore:
    def __init__(self) -> None:
        self._records: dict[str, object] = {}

    async def sync_from_registry(self, skills) -> int:
        for skill in skills:
            self._records[skill.skill_id] = skill
        return len(skills)

    def load_all(self) -> dict[str, object]:
        return dict(self._records)


class _EntryPointRuntime:
    def __init__(self) -> None:
        self.registry = _EntryPointRegistry()
        self.store = _EntryPointStore()

    def get_skill_registry(self):
        return self.registry

    def get_skill_store(self):
        return self.store


class _EntryPointMappingStore:
    def close(self) -> None:
        pass


def _load_mcp_server_without_stdio_redirect(monkeypatch: pytest.MonkeyPatch):
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        module = importlib.import_module("openspace.entrypoints.mcp.server")
    finally:
        redirected_stderr = sys.stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        if redirected_stderr is not original_stderr:
            redirected_stderr.close()
    return module


def test_mcp_import_action_returns_candidate_without_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    server = _load_mcp_server_without_stdio_redirect(monkeypatch)
    runtime = _EntryPointRuntime()
    candidate_path = tmp_path / "quarantine" / "candidate-1" / "payload"
    candidate_path.mkdir(parents=True)

    class FakeClient:
        def import_skill(self, *_args, **_kwargs):
            return {
                "status": "governance_required",
                "registered": False,
                "candidate_id": "candidate-1",
                "candidate_path": str(candidate_path),
            }

    async def get_runtime():
        return runtime

    async def get_store(*, required=True):
        return runtime.store

    async def get_mapping_store():
        return _EntryPointMappingStore()

    monkeypatch.setattr(server, "_get_cloud_client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(server, "_get_openspace", get_runtime)
    monkeypatch.setattr(server, "_get_runtime_store", get_store)
    monkeypatch.setattr(server, "_get_cloud_mapping_store", get_mapping_store)

    response = json.loads(
        asyncio.run(
            server.cloud_import_skill(
                cloud_skill_id="cloud-1",
                target_dir=str(tmp_path / "formal"),
                local_category="tool_guide",
                local_category_path="technology/computing",
            )
        )
    )

    assert response["status"] == "governance_required"
    assert response["registered"] is False
    assert response["candidate_id"] == "candidate-1"
    assert runtime.registry.list_skills() == []
    assert runtime.store.load_all() == {}


def test_mcp_install_action_rejects_bare_pass_or_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _load_mcp_server_without_stdio_redirect(monkeypatch)

    response = json.loads(
        asyncio.run(
            server.cloud_browse_skills(
                action="install_candidate",
                candidate_id="candidate-1",
                governance_outcome={
                    "status": "PASS",
                    "completion_receipt": {"candidate_digest": "not-enough"},
                },
            )
        )
    )

    assert response["status"] == "error"
    assert response["code"] == "COMPLETE_GOVERNANCE_OUTCOME_REQUIRED"


@pytest.fixture
def mapping_store(tmp_path: Path) -> CloudLocalMappingStore:
    store = CloudLocalMappingStore(tmp_path / "state" / "openspace.db")
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def cloud_client(mapping_store: CloudLocalMappingStore) -> OpenSpaceClient:
    return OpenSpaceClient(
        CloudConfig(
            mode="live",
            base_url="https://open-space.cloud",
            api_key="test-key",
            telemetry_mode="off",
        ),
        mapping_store=mapping_store,
    )


@pytest.fixture
def package_bundle() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("outline.md", "# Package\n")
        archive.writestr(
            "skills/cloud-in-package/SKILL.md",
            "---\nname: bundled\ndescription: Bundled skill.\n---\n",
        )
        archive.writestr("skills/cloud-in-package/.skill_id", "remote-id\n")
        archive.writestr("skills/cloud-in-package/.cloud_skill.json", "{}\n")
    return output.getvalue()


def test_package_bundle_is_inspection_only_and_creates_no_skill_binding(
    tmp_path: Path,
    cloud_client: OpenSpaceClient,
    mapping_store: CloudLocalMappingStore,
    package_bundle: bytes,
) -> None:
    package_data = {
        "root_package_path": "technology/computing",
        "projection_hash": hashlib.sha256(b"projection").hexdigest(),
        "skills": [
            {
                "cloud_skill_id": "cloud-in-package",
                "package_id": "package-1",
                "package_path": "technology/computing",
            }
        ],
    }
    cloud_client.pull_package_with_projection_status = lambda *_args, **_kwargs: {
        "status": "success",
        "package": package_data,
    }
    cloud_client.download_package_bundle_with_projection_status = (
        lambda *_args, **_kwargs: {
            "status": "success",
            "bundle": package_bundle,
        }
    )

    result = cloud_client.import_package_bundle(
        "package-1",
        tmp_path / "ignored-formal-root",
    )

    artifact_path = Path(result["artifact_path"])
    assert result["imported_skills"] == []
    assert result["registered_skill_count"] == 0
    assert mapping_store.get_binding_by_cloud("cloud-in-package") is None
    assert artifact_path == mapping_store.db_path.parent / "cloud-packages" / "package-1"
    assert artifact_path.is_dir()
    assert not list(artifact_path.rglob(".skill_id"))
    assert not list(artifact_path.rglob(".cloud_skill.json"))
    assert not (tmp_path / "ignored-formal-root").exists()


@pytest.mark.parametrize(
    "skill_path",
    [
        Path("openspace/host_skills/skill-discovery/SKILL.md"),
        Path("openspace/host_skills/delegate-task/SKILL.md"),
    ],
)
def test_host_skill_examples_preserve_explicit_governance_boundary(
    skill_path: Path,
) -> None:
    instructions = skill_path.read_text(encoding="utf-8")

    assert 'action="import_skill"' in instructions
    assert 'action="install_candidate"' in instructions
    assert "governance_outcome" in instructions
    assert re.search(r"Codex\s+semantic\s+confirmation", instructions)
