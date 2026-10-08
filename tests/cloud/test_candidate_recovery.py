from __future__ import annotations

import subprocess
from pathlib import Path

from openspace.cloud.candidate_lifecycle import (
    CandidateRepository,
    CandidateStatus,
    formal_candidate_path,
)


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
