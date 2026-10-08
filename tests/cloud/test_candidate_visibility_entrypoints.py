from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openspace.entrypoints.mcp import server
from openspace.skill_engine.registry import SkillRegistry


def _write_skill(path: Path, name: str = "demo") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n\nbody\n",
        encoding="utf-8",
    )
    return path


class _Policy:
    def __init__(self, rejected: set[Path]):
        self.rejected = {path.resolve() for path in rejected}
        self.seen: list[Path] = []

    def inspect(self, path: Path):
        resolved = Path(path).resolve()
        self.seen.append(resolved)
        if resolved in self.rejected:
            return SimpleNamespace(allowed=False, code="CANDIDATE_NOT_INSTALLED")
        return SimpleNamespace(allowed=True, code="ORDINARY_LOCAL_SKILL")


class _Registry:
    def __init__(self):
        self.registered: list[Path] = []

    def discover_from_dirs(self, dirs, admission_callback=None):
        added = []
        for root in dirs:
            for skill in sorted(Path(root).iterdir()):
                if not (skill / "SKILL.md").exists():
                    continue
                if admission_callback is not None and not admission_callback(skill).allowed:
                    continue
                self.registered.append(skill.resolve())
                added.append(SimpleNamespace(skill_id=skill.name, path=skill / "SKILL.md"))
        return added

    def register_skill_dir(self, skill_dir, admission_callback=None):
        skill_dir = Path(skill_dir)
        if admission_callback is not None and not admission_callback(skill_dir).allowed:
            return None
        self.registered.append(skill_dir.resolve())
        return SimpleNamespace(skill_id=skill_dir.name, path=skill_dir / "SKILL.md")


class _Store:
    def __init__(self):
        self.records = []

    async def sync_from_registry(self, skills):
        self.records.extend(skills)
        return len(skills)


class _Runtime:
    def __init__(self):
        self.registry = _Registry()
        self.store = _Store()

    def get_skill_registry(self):
        return self.registry

    def get_skill_store(self):
        return self.store

    def get_trigger_engine(self):
        return SimpleNamespace()


def test_registry_discovery_applies_admission_before_visibility(tmp_path: Path):
    allowed = _write_skill(tmp_path / "allowed", "allowed")
    rejected = _write_skill(tmp_path / "rejected", "rejected")
    policy = _Policy({rejected})

    registry = SkillRegistry([tmp_path])
    skills = registry.discover(admission_callback=policy.inspect)

    assert [skill.name for skill in skills] == ["allowed"]
    assert rejected not in [skill.path.parent for skill in skills]
    assert policy.seen == [allowed.resolve(), rejected.resolve()]


def test_auto_register_skips_rejected_managed_path_without_store_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    allowed = _write_skill(tmp_path / "allowed", "allowed")
    rejected = _write_skill(tmp_path / "rejected", "rejected")
    runtime = _Runtime()
    policy = _Policy({rejected})

    async def get_runtime():
        return runtime

    monkeypatch.setattr(server, "_get_openspace", get_runtime)
    monkeypatch.setattr(server, "_visibility_policy_for_runtime", lambda _runtime: policy)

    count = asyncio.run(server._auto_register_skill_dirs([str(tmp_path)]))

    assert count == 1
    assert runtime.registry.registered == [allowed.resolve()]
    assert len(runtime.store.records) == 1
    assert rejected.resolve() in policy.seen


def test_fix_skill_rejection_creates_no_evidence_or_trigger_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    rejected = _write_skill(tmp_path / "rejected", "rejected")
    runtime = _Runtime()
    policy = _Policy({rejected})

    async def get_runtime():
        return runtime

    monkeypatch.setattr(server, "_get_openspace", get_runtime)
    monkeypatch.setattr(server, "_visibility_policy_for_runtime", lambda _runtime: policy)

    response = json.loads(asyncio.run(server.fix_skill(str(rejected), "repair")))

    assert response["status"] == "error"
    assert response["code"] == "SKILL_VISIBILITY_REJECTED"
    assert runtime.registry.registered == []
    assert runtime.store.records == []
