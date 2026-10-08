from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from openspace.cloud.client import OpenSpaceClient
from openspace.cloud.config import CloudConfig
from openspace.cloud.local_mapping import CloudLocalMappingStore


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
def valid_bundle() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "demo/SKILL.md",
            "---\nname: demo\ndescription: Demo tool guide\n---\n\n# Demo\n",
        )
        archive.writestr("demo/references/example.txt", "example\n")
    return output.getvalue()


def _cloud_metadata(*, manifest_hash: str | None) -> dict[str, object]:
    return {
        "cloud_skill_id": "cloud-1",
        "title": "demo",
        "summary": "Demo tool guide",
        "authored_metadata": {
            "name": "demo",
            "description": "Demo tool guide",
        },
        "package_id": "package-1",
        "package_path": "technology/computing",
        "snapshot_version": "snapshot-1",
        "manifest_hash": manifest_hash,
    }


def test_import_skill_acquires_to_quarantine_without_binding_or_formal_files(
    tmp_path: Path,
    cloud_client: OpenSpaceClient,
    mapping_store: CloudLocalMappingStore,
    valid_bundle: bytes,
) -> None:
    install_root = tmp_path / "formal-skills"
    cloud_client.fetch_cloud_skill = lambda _: _cloud_metadata(
        manifest_hash="sha256:" + hashlib.sha256(valid_bundle).hexdigest()
    )
    cloud_client.download_skill_bundle = lambda *_args, **_kwargs: valid_bundle

    result = cloud_client.import_skill(
        "cloud-1",
        install_root,
        local_category="tool_guide",
        local_category_path="technology/computing",
    )

    assert result["status"] == "governance_required"
    assert result["registered"] is False
    assert "local_path" not in result
    assert Path(result["candidate_path"]).is_dir()
    assert not install_root.exists()
    assert mapping_store.get_binding_by_cloud("cloud-1") is None


@pytest.mark.parametrize(
    ("manifest_hash", "expected"),
    [
        (None, "UNPROVEN"),
        ("sha256:" + "0" * 64, "MISMATCH"),
    ],
)
def test_source_proof_never_upgrades_unknown_or_wrong_hash(
    manifest_hash: str | None,
    expected: str,
    cloud_client: OpenSpaceClient,
    valid_bundle: bytes,
    tmp_path: Path,
) -> None:
    cloud_client.fetch_cloud_skill = lambda _: _cloud_metadata(
        manifest_hash=manifest_hash
    )
    cloud_client.download_skill_bundle = lambda *_args, **_kwargs: valid_bundle

    result = cloud_client.import_skill("cloud-1", tmp_path / "formal")

    assert result["source_integrity_status"] == expected
    assert result["registered"] is False
    assert not (tmp_path / "formal").exists()
